"""X/Twitter 账号动态采集器（twscrape + 子进程，参照 WechatCollector 模式）

子进程隔离解决 Windows 上 asyncio 与 FastAPI event loop 的冲突。
数据通过临时 JSON 文件交换。
"""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from typing import Any, Dict, List

from backend.collector.filters import is_ai_related
from backend.date_filters import is_within_recent_days

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))


def _resolve_proxy(twitter_cfg: Dict, proxy_url: str = "") -> str:
    """决定 twscrape 子进程使用的代理 URL。

    use_proxy=False → 不走代理；否则依次取 twitter_cfg 显式 proxy、
    全局 proxy_url、环境变量 HTTPS_PROXY/HTTP_PROXY。
    normalize_proxy_config 会剥除 twitter.proxy 键，故须由调用方传入 proxy_url。
    """
    if not twitter_cfg.get("use_proxy", True):
        return ""
    explicit = (twitter_cfg.get("proxy") or "").strip()
    if explicit:
        return explicit
    if (proxy_url or "").strip():
        return proxy_url.strip()
    return (os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY") or "").strip()


def _normalize(raw: Dict, display_name: str, handle: str, date_window_days: int) -> Dict | None:
    """将子进程输出的原始推文转换为标准 news item，失败返回 None。"""
    url = raw.get("url", "")
    full_text = raw.get("rawContent", "") or raw.get("content", "")
    published = raw.get("date", "")

    if not url or not full_text:
        return None
    if not is_within_recent_days(published, days=date_window_days):
        return None
    # 精选 AI 账号也会发非 AI 内容（生活/闲聊），无话题配置时下游不再过滤，
    # 故在采集层做关键词预筛，避免噪声进入报告。
    if not is_ai_related(full_text):
        return None

    title = full_text[:80].replace("\n", " ")
    interaction_count = (
        int(raw.get("retweetCount", 0) or 0)
        + int(raw.get("likeCount", 0) or 0)
        + int(raw.get("replyCount", 0) or 0)
    )
    news_id = hashlib.md5(url.encode()).hexdigest()

    return {
        "id": news_id,
        "url": url,
        "title": title,
        "summary": full_text[:500],
        "full_text": full_text,
        "source_name": f"{display_name} (@{handle})",
        "source_tier": 2,
        "institution": display_name,
        "indicator": "twitter",
        "score": 0.0,
        "published_at": published,
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "interaction_count": interaction_count,
    }


class TwitterCollector:
    def __init__(self, date_window_days: int = 3):
        self.date_window_days = date_window_days

    def collect_all(self, twitter_cfg: Dict[str, Any], proxy_url: str = "") -> List[Dict]:
        from backend.collector.twitter_auth import (
            ACCOUNTS_DB_PATH, has_accounts, has_browser_session, BROWSER_SESSION_PATH,
            twscrape_available, TWSCRAPE_MISSING_MSG,
        )

        if not twitter_cfg.get("enabled", False):
            print("[Twitter] 已禁用，跳过", flush=True)
            return []

        if not twscrape_available():
            print(f"[Twitter] {TWSCRAPE_MISSING_MSG}", flush=True)
            return []

        # 若 twscrape DB 不存在但有浏览器 session，尝试先注入
        if not has_accounts() and has_browser_session():
            print("[Twitter] 检测到浏览器登录凭证，尝试注入 twscrape 账号池...", flush=True)
            import asyncio as _asyncio
            from backend.collector.twitter_auth import add_account_from_session
            loop = _asyncio.new_event_loop()
            try:
                loop.run_until_complete(add_account_from_session())
                print("[Twitter] 注入成功", flush=True)
            except Exception as e:
                print(f"[Twitter] 注入失败: {e}", flush=True)
            finally:
                loop.close()

        if not has_accounts():
            print("[Twitter] 未配置账号，跳过。请通过配置页添加 X 小号", flush=True)
            return []

        accounts = twitter_cfg.get("accounts", [])
        if not accounts:
            print("[Twitter] 账号列表为空，跳过", flush=True)
            return []

        input_data = {
            "accounts_db": ACCOUNTS_DB_PATH,
            "accounts": accounts,
            "max_tweets_per_account": twitter_cfg.get("max_tweets_per_account", 10),
            "fetch_delay_min": twitter_cfg.get("fetch_delay_min", 8),
            "fetch_delay_max": twitter_cfg.get("fetch_delay_max", 20),
            "tweet_delay_min": twitter_cfg.get("tweet_delay_min", 1),
            "tweet_delay_max": twitter_cfg.get("tweet_delay_max", 3),
            "max_total_tweets": twitter_cfg.get("max_total_tweets", 150),
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f_in:
            json.dump(input_data, f_in, ensure_ascii=False)
            input_path = f_in.name
        output_path = input_path.replace(".json", "_out.json")

        proxy = _resolve_proxy(twitter_cfg, proxy_url)
        sub_env = os.environ.copy()
        if proxy:
            sub_env["TWS_PROXY"] = proxy

        try:
            print(f"[Twitter] 启动子进程采集 {len(accounts)} 个账号"
                  + (f"（代理 {proxy}）" if proxy else "（无代理）") + "...", flush=True)
            result = subprocess.run(
                [sys.executable, "-u", "-c", _COLLECT_SCRIPT, input_path, output_path],
                cwd=_PROJECT_ROOT,
                env=sub_env,
                timeout=600,
            )
            if result.returncode != 0:
                print("[Twitter] 子进程采集失败", flush=True)
                return []
            if not os.path.exists(output_path):
                print("[Twitter] 子进程未产出结果文件", flush=True)
                return []
            with open(output_path, encoding="utf-8") as f:
                raw_tweets = json.load(f)
        except subprocess.TimeoutExpired:
            print("[Twitter] 子进程采集超时", flush=True)
            return []
        except Exception as e:
            print(f"[Twitter] 子进程采集异常: {e}", flush=True)
            return []
        finally:
            for p in (input_path, output_path):
                try:
                    os.unlink(p)
                except OSError:
                    pass

        items = []
        for raw in raw_tweets:
            item = _normalize(
                raw,
                display_name=raw.get("_display_name", raw.get("_handle", "")),
                handle=raw.get("_handle", ""),
                date_window_days=self.date_window_days,
            )
            if item:
                items.append(item)

        print(f"[Twitter] 共获取 {len(items)} 条 AI 相关推文", flush=True)
        return items


_COLLECT_SCRIPT = r'''
import asyncio
import json
import random
import sys

input_path = sys.argv[1]
output_path = sys.argv[2]

with open(input_path, encoding="utf-8") as f:
    cfg = json.load(f)

ACCOUNTS_DB = cfg["accounts_db"]
accounts = cfg["accounts"]
MAX_PER = cfg["max_tweets_per_account"]
FETCH_MIN = cfg["fetch_delay_min"]
FETCH_MAX = cfg["fetch_delay_max"]
TWEET_MIN = cfg["tweet_delay_min"]
TWEET_MAX = cfg["tweet_delay_max"]
MAX_TOTAL = cfg["max_total_tweets"]


async def collect():
    try:
        from twscrape import API, AccountsPool
    except ImportError:
        print("[Twitter] twscrape 未安装", flush=True)
        return []

    # Monkey-patch 跳过 x-client-transaction-id（twscrape v0.17 解析失败导致 IndexError，issue #248）
    try:
        from twscrape.queue_client import Ctx
        async def _patched_req(self, method, url, params=None):
            return await self.clt.request(method, url, params=params)
        Ctx.req = _patched_req
        print("[Twitter:subproc] 已绕过 x-client-transaction-id 生成", flush=True)
    except Exception as e:
        print(f"[Twitter:subproc] monkey-patch 失败: {e}", flush=True)

    # 诊断：打印 DB 内账号状态
    import sqlite3
    try:
        conn = sqlite3.connect(ACCOUNTS_DB)
        cols = [r[1] for r in conn.execute("PRAGMA table_info(accounts)").fetchall()]
        print(f"[Twitter:subproc] DB={ACCOUNTS_DB}", flush=True)
        print(f"[Twitter:subproc] accounts 字段: {cols}", flush=True)
        rows = conn.execute("SELECT username, active, length(cookies), length(headers), error_msg FROM accounts").fetchall()
        for r in rows:
            print(f"[Twitter:subproc] 账号: username={r[0]}, active={r[1]}, cookies_len={r[2]}, headers_len={r[3]}, err={r[4]}", flush=True)
        # 再次强制激活（subprocess 启动时刻保证 active=1）
        conn.execute("UPDATE accounts SET active=1, locks='{}', error_msg=NULL")
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[Twitter:subproc] 诊断失败: {e}", flush=True)

    pool = AccountsPool(ACCOUNTS_DB)
    api = API(pool)

    random.shuffle(accounts)
    all_tweets = []
    total = 0

    for acct in accounts:
        if total >= MAX_TOTAL:
            break
        handle = acct.get("handle", "")
        display_name = acct.get("display_name", handle)
        if not handle:
            continue

        print(f"[Twitter] 采集 @{handle}...", flush=True)
        count = 0
        try:
            # user_tweets 需要数字 uid，先通过 handle 查询用户信息
            user = await api.user_by_login(handle)
            if user is None:
                print(f"[Twitter] @{handle} 未找到用户", flush=True)
                continue
            async for tweet in api.user_tweets(user.id, limit=MAX_PER):
                # 若是转推，用原 tweet 的内容/作者/URL；引用推文（quote）保留转发者作为作者
                src = getattr(tweet, "retweetedTweet", None) or tweet
                src_user = getattr(src, "user", None)
                real_handle = src_user.username if src_user else handle
                real_display = src_user.displayname if src_user else display_name
                all_tweets.append({
                    "url": f"https://x.com/{real_handle}/status/{src.id}",
                    "rawContent": getattr(src, "rawContent", "") or "",
                    "date": getattr(src, "date", None) and src.date.isoformat() or "",
                    "retweetCount": getattr(src, "retweetCount", 0) or 0,
                    "likeCount": getattr(src, "likeCount", 0) or 0,
                    "replyCount": getattr(src, "replyCount", 0) or 0,
                    "_handle": real_handle,
                    "_display_name": real_display,
                    "_via_handle": handle if src is not tweet else "",
                })
                count += 1
                total += 1
                if total >= MAX_TOTAL:
                    break
                await asyncio.sleep(random.uniform(TWEET_MIN, TWEET_MAX))
        except Exception as e:
            import traceback
            print(f"[Twitter] @{handle} 采集失败: {type(e).__name__}: {e!r}", flush=True)
            traceback.print_exc()

        print(f"[Twitter] @{handle}: {count} 条推文", flush=True)
        if total < MAX_TOTAL and acct is not accounts[-1]:
            delay = random.uniform(FETCH_MIN, FETCH_MAX)
            print(f"[Twitter] 等待 {delay:.1f}s...", flush=True)
            await asyncio.sleep(delay)

    return all_tweets


tweets = asyncio.run(collect())
with open(output_path, "w", encoding="utf-8") as f:
    json.dump(tweets, f, ensure_ascii=False, indent=2)
print(f"[Twitter] 子进程完成，共 {len(tweets)} 条原始推文", flush=True)
'''
