"""微信公众号文章采集器（Playwright + 微信后台 API）

Playwright 的 sync API 在 Windows 上无法在 FastAPI 线程池中运行（asyncio 限制），
因此整个采集逻辑在独立子进程中执行，通过临时 JSON 文件交换数据。
"""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from typing import Any, Dict, List

from backend.date_filters import is_within_recent_days

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))

FAKEIDS_PATH = os.path.join(_PROJECT_ROOT, "data", "wechat_fakeids.json")


class WechatCollector:
    def __init__(self, max_per_source: int = 5, date_window_days: int = 3,
                 proxy_url: str = None):
        self.max_per_source = max_per_source
        self.date_window_days = date_window_days
        self.proxy_url = proxy_url

    def collect_all(self, sources: List[Dict[str, Any]]) -> List[Dict]:
        """在子进程中采集所有微信公众号源。

        Returns:
            标准 news item 列表（已过滤）
        """
        from backend.collector.wechat_auth import load_session, SESSION_PATH

        session = load_session()
        if not session:
            print("[Wechat] 无有效 session，跳过微信采集。请通过配置页扫码登录", flush=True)
            return []

        # 准备输入数据
        # 微信为国内站，默认不走代理；仅当某源显式开启 use_proxy 时启用
        proxy_server = (
            self.proxy_url
            if (self.proxy_url and any(s.get("use_proxy", False) for s in sources))
            else ""
        )
        input_data = {
            "session_path": SESSION_PATH,
            "fakeids_path": FAKEIDS_PATH,
            "max_per_source": self.max_per_source,
            "sources": sources,
            "proxy_server": proxy_server,
        }

        # 用临时文件传递数据
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f_in:
            json.dump(input_data, f_in, ensure_ascii=False)
            input_path = f_in.name

        output_path = input_path.replace(".json", "_out.json")

        try:
            print(f"[Wechat] 启动子进程采集 {len(sources)} 个公众号...", flush=True)
            result = subprocess.run(
                [sys.executable, "-u", "-c", _COLLECT_SCRIPT, input_path, output_path],
                cwd=_PROJECT_ROOT,
                timeout=300,
            )

            if result.returncode != 0:
                print("[Wechat] 子进程采集失败", flush=True)
                return []

            # 读取输出
            if not os.path.exists(output_path):
                print("[Wechat] 子进程未产出结果文件", flush=True)
                return []

            with open(output_path, encoding="utf-8") as f:
                raw_articles = json.load(f)

        except subprocess.TimeoutExpired:
            print("[Wechat] 子进程采集超时", flush=True)
            return []
        except Exception as e:
            print(f"[Wechat] 子进程采集异常: {e}", flush=True)
            return []
        finally:
            # 清理临时文件
            for p in (input_path, output_path):
                try:
                    os.unlink(p)
                except OSError:
                    pass

        # 在主进程中做日期过滤
        items = []
        for article in raw_articles:
            source = article.get("_source", {})
            title = article.get("title", "")
            url = article.get("url", "")
            digest = article.get("digest", "")
            ts = article.get("update_time", 0)

            if not title or not url:
                continue

            published = ""
            if ts:
                try:
                    published = datetime.fromtimestamp(int(ts), tz=timezone.utc).isoformat()
                except (ValueError, TypeError, OSError):
                    pass

            if not is_within_recent_days(published, days=self.date_window_days):
                continue

            news_id = hashlib.md5(url.encode()).hexdigest()
            items.append({
                "id": news_id,
                "url": url,
                "title": title[:200],
                "summary": digest[:500] if digest else "",
                "full_text": "",
                "source_name": source.get("name", ""),
                "source_tier": source.get("tier", 3),
                "institution": source.get("institution", ""),
                "indicator": source.get("indicator", ""),
                "score": 0.0,
                "published_at": published,
                "collected_at": datetime.now(timezone.utc).isoformat(),
            })

        if items:
            print(f"[Wechat] 共获取 {len(items)} 条昨日 AI 相关文章", flush=True)
        else:
            print("[Wechat] 未找到昨日 AI 相关文章", flush=True)
        return items


# 子进程采集脚本：启动浏览器 → 验证 session → 对每个源查 fakeid + 拉文章 → 输出 JSON
_COLLECT_SCRIPT = '''
import json, os, re, sys, time, random

input_path = sys.argv[1]
output_path = sys.argv[2]

with open(input_path, encoding="utf-8") as f:
    config = json.load(f)

SESSION_PATH = config["session_path"]
FAKEIDS_PATH = config["fakeids_path"]
MAX_PER_SOURCE = config["max_per_source"]
sources = config["sources"]
PROXY = config.get("proxy_server", "")

# --- fakeid 缓存 ---
def load_fakeids():
    if not os.path.exists(FAKEIDS_PATH):
        return {}
    try:
        with open(FAKEIDS_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_fakeids(data):
    os.makedirs(os.path.dirname(FAKEIDS_PATH), exist_ok=True)
    with open(FAKEIDS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# --- 启动 Playwright ---
try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("[Wechat] playwright 未安装", flush=True)
    sys.exit(1)

all_articles = []

with sync_playwright() as p:
    browser = p.chromium.launch(
        headless=True,
        proxy=({"server": PROXY} if PROXY else None),
        args=[
            "--disable-blink-features=AutomationControlled",
            "--disable-features=AutomationControlled",
            "--disable-gpu",
            "--no-first-run",
        ],
    )
    context = browser.new_context(storage_state=SESSION_PATH)
    page = context.new_page()

    try:
        # 验证 session
        page.goto("https://mp.weixin.qq.com/", wait_until="domcontentloaded")
        time.sleep(3)

        token = page.evaluate(
            "() => window.location.href.match(/token=(\\\\d+)/)?.[1] || ''"
        )
        if not token:
            print("[Wechat] session 已失效，请重新扫码登录", flush=True)
            sys.exit(1)

        print(f"[Wechat] session 有效，token={token}", flush=True)

        fakeids = load_fakeids()

        for source in sources:
            nickname = source.get("nickname", "")
            if not nickname:
                continue

            # 获取 fakeid
            fakeid = None
            if nickname in fakeids:
                fakeid = fakeids[nickname]["fakeid"]
            else:
                try:
                    result = page.evaluate("""
                        async ([token, nickname]) => {
                            const url = `/cgi-bin/searchbiz?action=search_biz&token=${token}&lang=zh_CN&f=json&ajax=1&query=${encodeURIComponent(nickname)}&begin=0&count=5`;
                            const resp = await fetch(url, {credentials: 'include'});
                            return await resp.json();
                        }
                    """, [token, nickname])
                    biz_list = result.get("list", [])
                    for biz in biz_list:
                        if biz.get("nickname") == nickname:
                            fakeid = biz.get("fakeid")
                            break
                    if not fakeid and biz_list:
                        fakeid = biz_list[0].get("fakeid")
                    if fakeid:
                        fakeids[nickname] = {"fakeid": fakeid}
                        save_fakeids(fakeids)
                        print(f"[Wechat] {nickname}: fakeid={fakeid}", flush=True)
                    else:
                        print(f"[Wechat] {nickname}: 未找到公众号", flush=True)
                except Exception as e:
                    print(f"[Wechat] {nickname}: searchbiz 失败: {e}", flush=True)

            if not fakeid:
                continue

            # 拉文章列表
            try:
                result = page.evaluate("""
                    async ([token, fakeid, count]) => {
                        const url = `/cgi-bin/appmsgpublish?sub=list&search_field=null&begin=0&count=${count}&query=&fakeid=${fakeid}&type=101_1&free_publish_type=1&sub_action=list_ex&token=${token}&lang=zh_CN&f=json&ajax=1`;
                        const resp = await fetch(url, {credentials: 'include'});
                        return await resp.json();
                    }
                """, [token, fakeid, MAX_PER_SOURCE])
            except Exception as e:
                print(f"[Wechat] {nickname}: appmsgpublish 失败: {e}", flush=True)
                continue

            # publish_page 可能是 JSON 字符串（微信 API 特性）
            publish_page = result.get("publish_page", {})
            if isinstance(publish_page, str):
                try:
                    publish_page = json.loads(publish_page)
                except (json.JSONDecodeError, TypeError):
                    publish_page = {}
            publish_list = publish_page.get("publish_list", []) if isinstance(publish_page, dict) else []

            count = 0
            for publish in publish_list:
                # publish 可能是 JSON 字符串或 dict
                if isinstance(publish, str):
                    try:
                        publish = json.loads(publish)
                    except (json.JSONDecodeError, TypeError):
                        continue
                if not isinstance(publish, dict):
                    continue

                info = publish.get("publish_info", {})
                if isinstance(info, str):
                    try:
                        info = json.loads(info)
                    except (json.JSONDecodeError, TypeError):
                        continue
                if not isinstance(info, dict):
                    continue

                appmsg_list = info.get("appmsgex", [])
                for article in appmsg_list:
                    all_articles.append({
                        "title": article.get("title", ""),
                        "url": article.get("link", ""),
                        "digest": article.get("digest", ""),
                        "update_time": article.get("update_time", 0),
                        "_source": source,
                    })
                    count += 1

            print(f"[Wechat] {nickname}: 获取 {count} 篇文章", flush=True)

            # 随机延迟
            time.sleep(random.uniform(3, 8))

    except SystemExit:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"[Wechat] 采集异常: {e}", flush=True)
    finally:
        browser.close()

# 输出结果
with open(output_path, "w", encoding="utf-8") as f:
    json.dump(all_articles, f, ensure_ascii=False, indent=2)
print(f"[Wechat] 子进程完成，共 {len(all_articles)} 篇原始文章", flush=True)
'''
