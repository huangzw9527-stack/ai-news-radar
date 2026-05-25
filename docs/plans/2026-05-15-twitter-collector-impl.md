# Twitter/X 采集器实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 在不使用官方 API 的情况下，用 twscrape 为 AI News Radar 新增 X/Twitter 账号动态监控。

**Architecture:** 参照 WechatCollector 的子进程模式——主采集逻辑运行在独立子进程中（解决 Windows asyncio 限制），通过临时 JSON 文件交换数据；凭证管理在 FastAPI async 路由中直接 await；`interaction_count` 字段写入 DB 并在 scorer hotness 中使用。

**Tech Stack:** twscrape（无官方 API 的 X 抓取库）、asyncio、SQLite（DB 迁移）、React/Tailwind（前端配置页）

---

## Task 1: 安装依赖 & 更新 .gitignore

**Files:**
- Modify: `.gitignore`（新增 twitter accounts DB）
- Run: `pip install twscrape`

**Step 1: 安装 twscrape**

```bash
pip install twscrape
```

Expected: Successfully installed twscrape

**Step 2: 更新 .gitignore**

在 `.gitignore` 末尾追加：

```
data/twitter_accounts.db
```

**Step 3: 更新 config.yaml — 新增 twitter 节**

在 `config.yaml` 的 `sources:` 下，`wechat:` 节后面追加（注意缩进与 wechat 节对齐）：

```yaml
  twitter:
    enabled: true
    max_tweets_per_account: 10
    fetch_delay_min: 8
    fetch_delay_max: 20
    tweet_delay_min: 1
    tweet_delay_max: 3
    max_total_tweets: 150
    accounts:
      - handle: OpenAI
        display_name: OpenAI 官方
      - handle: AnthropicAI
        display_name: Anthropic 官方
      - handle: GoogleDeepMind
        display_name: Google DeepMind
      - handle: ylecun
        display_name: Yann LeCun
      - handle: karpathy
        display_name: Andrej Karpathy
      - handle: vista8
        display_name: 向阳乔木
      - handle: dotey
        display_name: 宝玉
      - handle: AYi_AInotes
        display_name: AYi
      - handle: servasyy_ai
        display_name: huangserva
      - handle: berryxia
        display_name: berryxia
      - handle: AlchainHust
        display_name: 花叔
```

**Step 4: Commit**

```bash
git add .gitignore config.yaml
git commit -m "feat(twitter): add twscrape dependency and config section"
```

---

## Task 2: DB 迁移 — 新增 interaction_count 字段

**Files:**
- Modify: `backend/db.py:27-43`（CREATE TABLE news 语句）
- Modify: `backend/db.py:62-102`（init 迁移代码块）
- Modify: `backend/db.py:104-114`（upsert_news）

**Step 1: 在 CREATE TABLE news 加字段**

在 `backend/db.py` 的 CREATE TABLE news 语句最后一个字段 `collected_at TEXT` 后面加：

```sql
interaction_count INTEGER DEFAULT 0
```

完整语句变为：
```sql
CREATE TABLE IF NOT EXISTS news (
    id           TEXT PRIMARY KEY,
    url          TEXT UNIQUE,
    title        TEXT,
    summary      TEXT,
    full_text    TEXT,
    source_name  TEXT,
    source_tier  INTEGER,
    institution  TEXT,
    indicator    TEXT,
    score        REAL DEFAULT 0,
    published_at TEXT,
    collected_at TEXT,
    interaction_count INTEGER DEFAULT 0
);
```

**Step 2: 在 init() 迁移块加 ALTER TABLE**

在 `backend/db.py` 的 `init()` 方法里，找到现有的 reports 列迁移代码（约第 82-86 行），**在其前面**加 news 表迁移：

```python
# news 表迁移（旧数据库兼容）
existing_news = {row[1] for row in conn.execute("PRAGMA table_info(news)").fetchall()}
if "interaction_count" not in existing_news:
    conn.execute("ALTER TABLE news ADD COLUMN interaction_count INTEGER DEFAULT 0")
```

**Step 3: 更新 upsert_news 支持新字段**

将 `upsert_news` 方法的 SQL 更新为：

```python
def upsert_news(self, news: Dict[str, Any]):
    conn = self._conn()
    conn.execute("""
        INSERT OR IGNORE INTO news
        (id,url,title,summary,full_text,source_name,source_tier,
         institution,indicator,score,published_at,collected_at,interaction_count)
        VALUES (:id,:url,:title,:summary,:full_text,:source_name,
                :source_tier,:institution,:indicator,:score,
                :published_at,:collected_at,:interaction_count)
    """, {**news, "interaction_count": news.get("interaction_count", 0)})
    conn.commit()
```

**Step 4: 写失败测试**

在 `tests/test_db.py` 末尾添加：

```python
def test_upsert_news_with_interaction_count():
    from backend.db import Database
    db = Database(":memory:")
    db.init()
    news = {
        "id": "tw_test_001",
        "url": "https://x.com/OpenAI/status/123",
        "title": "Test tweet",
        "summary": "",
        "full_text": "Test tweet full text",
        "source_name": "OpenAI 官方 (@OpenAI)",
        "source_tier": 1,
        "institution": "OpenAI",
        "indicator": "academic",
        "score": 0.0,
        "published_at": "2026-05-15T10:00:00+00:00",
        "collected_at": "2026-05-15T10:00:00+00:00",
        "interaction_count": 5000,
    }
    db.upsert_news(news)
    rows = db._conn().execute("SELECT interaction_count FROM news WHERE id='tw_test_001'").fetchall()
    assert rows[0][0] == 5000
```

**Step 5: 运行测试确认失败**

```bash
pytest tests/test_db.py::test_upsert_news_with_interaction_count -v
```

Expected: FAIL（字段不存在）

**Step 6: 实施改动（Step 1-3）后运行测试确认通过**

```bash
pytest tests/test_db.py::test_upsert_news_with_interaction_count -v
```

Expected: PASS

**Step 7: Commit**

```bash
git add backend/db.py tests/test_db.py
git commit -m "feat(db): add interaction_count column to news table"
```

---

## Task 3: twitter_auth.py — 账号池管理

**Files:**
- Create: `backend/collector/twitter_auth.py`

**Step 1: 创建 twitter_auth.py**

```python
"""X/Twitter 账号池管理（基于 twscrape AccountsPool）

账号数据持久化到 data/twitter_accounts.db（twscrape 自维护的 SQLite）。
add_account() 是 async 函数，供 FastAPI async 路由直接 await。
"""
import os

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
ACCOUNTS_DB_PATH = os.path.join(_PROJECT_ROOT, "data", "twitter_accounts.db")


def has_accounts() -> bool:
    return os.path.exists(ACCOUNTS_DB_PATH)


async def add_account(username: str, password: str, email: str, email_password: str = "") -> dict:
    """添加 X 账号并尝试登录。在 FastAPI async 路由中直接 await。"""
    from twscrape import AccountsPool
    os.makedirs(os.path.dirname(ACCOUNTS_DB_PATH), exist_ok=True)
    pool = AccountsPool(ACCOUNTS_DB_PATH)
    await pool.add_account(username, password, email, email_password or "")
    stats = await pool.login_all()
    logged_in = sum(1 for s in stats if s.get("status") == "logged_in") if stats else 0
    return {"logged_in": logged_in, "total": len(stats) if stats else 0}
```

**Step 2: 运行语法检查**

```bash
python -c "from backend.collector.twitter_auth import has_accounts, ACCOUNTS_DB_PATH; print('OK')"
```

Expected: OK

**Step 3: Commit**

```bash
git add backend/collector/twitter_auth.py
git commit -m "feat(twitter): add twitter_auth module for account pool management"
```

---

## Task 4: twitter.py — TwitterCollector（子进程采集）

**Files:**
- Create: `backend/collector/twitter.py`

**Step 1: 创建 twitter.py**

```python
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


def _normalize(raw: Dict, display_name: str, handle: str, date_window_days: int) -> Dict | None:
    """将子进程输出的原始推文转换为标准 news item，失败返回 None。"""
    url = raw.get("url", "")
    full_text = raw.get("rawContent", "") or raw.get("content", "")
    published = raw.get("date", "")

    if not url or not full_text:
        return None
    if not is_within_recent_days(published, days=date_window_days):
        return None
    if not is_ai_related(full_text[:300], ""):
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

    def collect_all(self, twitter_cfg: Dict[str, Any]) -> List[Dict]:
        from backend.collector.twitter_auth import ACCOUNTS_DB_PATH, has_accounts

        if not twitter_cfg.get("enabled", True):
            print("[Twitter] 已禁用，跳过", flush=True)
            return []
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

        try:
            print(f"[Twitter] 启动子进程采集 {len(accounts)} 个账号...", flush=True)
            result = subprocess.run(
                [sys.executable, "-u", "-c", _COLLECT_SCRIPT, input_path, output_path],
                cwd=_PROJECT_ROOT,
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
import os
import random
import sys
import time

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
            async for tweet in api.user_tweets(handle, limit=MAX_PER):
                raw = tweet.__dict__.copy() if hasattr(tweet, "__dict__") else {}
                # twscrape Tweet 对象直接取属性
                all_tweets.append({
                    "url": f"https://x.com/{handle}/status/{tweet.id}",
                    "rawContent": getattr(tweet, "rawContent", "") or "",
                    "date": getattr(tweet, "date", None) and tweet.date.isoformat() or "",
                    "retweetCount": getattr(tweet, "retweetCount", 0) or 0,
                    "likeCount": getattr(tweet, "likeCount", 0) or 0,
                    "replyCount": getattr(tweet, "replyCount", 0) or 0,
                    "_handle": handle,
                    "_display_name": display_name,
                })
                count += 1
                total += 1
                if total >= MAX_TOTAL:
                    break
                time.sleep(random.uniform(TWEET_MIN, TWEET_MAX))
        except Exception as e:
            print(f"[Twitter] @{handle} 采集失败: {e}", flush=True)

        print(f"[Twitter] @{handle}: {count} 条推文", flush=True)
        if total < MAX_TOTAL and accounts.index(acct) < len(accounts) - 1:
            delay = random.uniform(FETCH_MIN, FETCH_MAX)
            print(f"[Twitter] 等待 {delay:.1f}s...", flush=True)
            time.sleep(delay)

    return all_tweets


tweets = asyncio.run(collect())
with open(output_path, "w", encoding="utf-8") as f:
    json.dump(tweets, f, ensure_ascii=False, indent=2)
print(f"[Twitter] 子进程完成，共 {len(tweets)} 条原始推文", flush=True)
'''
```

**Step 2: 写 _normalize 单元测试**

创建 `tests/test_twitter_collector.py`：

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from backend.collector.twitter import _normalize

_BASE = {
    "url": "https://x.com/OpenAI/status/123",
    "rawContent": "OpenAI releases GPT-5 with major improvements in reasoning and coding ability. This is a significant advancement in AI.",
    "date": "2026-05-15T08:00:00+00:00",
    "retweetCount": 1000,
    "likeCount": 3000,
    "replyCount": 500,
}

def test_normalize_basic():
    item = _normalize(_BASE, "OpenAI 官方", "OpenAI", date_window_days=7)
    assert item is not None
    assert item["url"] == "https://x.com/OpenAI/status/123"
    assert item["source_name"] == "OpenAI 官方 (@OpenAI)"
    assert item["interaction_count"] == 4500
    assert item["source_tier"] == 2
    assert item["indicator"] == "twitter"
    assert len(item["title"]) <= 80

def test_normalize_filters_empty_url():
    raw = {**_BASE, "url": ""}
    assert _normalize(raw, "OpenAI 官方", "OpenAI", date_window_days=7) is None

def test_normalize_filters_empty_content():
    raw = {**_BASE, "rawContent": ""}
    assert _normalize(raw, "OpenAI 官方", "OpenAI", date_window_days=7) is None

def test_normalize_filters_old_tweet():
    raw = {**_BASE, "date": "2020-01-01T00:00:00+00:00"}
    assert _normalize(raw, "OpenAI 官方", "OpenAI", date_window_days=7) is None

def test_normalize_interaction_count_zero_on_missing():
    raw = {**_BASE}
    raw.pop("retweetCount")
    raw.pop("likeCount")
    raw.pop("replyCount")
    item = _normalize(raw, "OpenAI 官方", "OpenAI", date_window_days=7)
    assert item is not None
    assert item["interaction_count"] == 0
```

**Step 3: 运行测试确认通过**

```bash
pytest tests/test_twitter_collector.py -v
```

Expected: 5 passed

**Step 4: Commit**

```bash
git add backend/collector/twitter.py tests/test_twitter_collector.py
git commit -m "feat(twitter): add TwitterCollector with subprocess-based collection"
```

---

## Task 5: pipeline.py — 集成 Twitter 采集

**Files:**
- Modify: `backend/pipeline.py:1-36`（import + load_sources）
- Modify: `backend/pipeline.py:38-72`（Pipeline.__init__）
- Modify: `backend/pipeline.py:75-121`（Pipeline.run 采集阶段）

**Step 1: 更新 import**

在 `pipeline.py` 顶部的 import 块加：

```python
from backend.collector.twitter import TwitterCollector
```

**Step 2: 更新 Pipeline.__init__**

在 `__init__` 中 `self.wechat_collector = WechatCollector(...)` 之后加：

```python
twitter_cfg = config.get("sources", {}).get("twitter", {})
self.twitter_collector = TwitterCollector(date_window_days=date_window_days)
self.twitter_cfg = twitter_cfg
```

**Step 3: 在 run() 中新增 Twitter 采集段**

在 `pipeline.py` 的 run() 方法中，微信采集块结束后（约第 120 行 `emit(f"采集完成...")` 之前）插入：

```python
# 采集 Twitter/X 账号动态
if self.twitter_cfg.get("enabled", False):
    emit(f"采集 Twitter/X 账号动态...")
    try:
        twitter_items = self.twitter_collector.collect_all(self.twitter_cfg)
        emit(f"  → Twitter: {len(twitter_items)} 条")
        all_news.extend(twitter_items)
    except Exception as e:
        emit(f"  → Twitter 采集异常: {e}")
```

**Step 4: Commit**

```bash
git add backend/pipeline.py
git commit -m "feat(pipeline): integrate TwitterCollector into collection pipeline"
```

---

## Task 6: scorer.py — interaction_count 影响热度分

**Files:**
- Modify: `backend/scorer.py:114-137`（score_and_rank Step 5）

**Step 1: 更新最终得分计算**

在 `score_and_rank` 的 Step 5 块中，找到 `hotness` 计算行：

```python
hotness = min(25.0, float(item.get("report_count", 1)) * 5.0)
```

替换为：

```python
if item.get("source_type") == "twitter" or item.get("indicator") == "twitter":
    raw_interactions = float(item.get("interaction_count", 0) or 0)
    hotness = min(25.0, raw_interactions / 200.0)
else:
    hotness = min(25.0, float(item.get("report_count", 1)) * 5.0)
```

> 解释：200 互动 = 1 分，4000+ 互动达到满分 25 分，与现有 report_count 量级对齐。

**Step 2: Commit**

```bash
git add backend/scorer.py
git commit -m "feat(scorer): use interaction_count for Twitter hotness score"
```

---

## Task 7: main.py — Twitter 账号管理 API

**Files:**
- Modify: `backend/main.py`（在 wechat 路由块之后新增）

**Step 1: 新增两个路由**

在 `backend/main.py` 的 `/api/wechat/collect` 路由之后追加：

```python
@app.get("/api/twitter/status")
def twitter_status():
    """获取 Twitter 账号配置状态"""
    from backend.collector.twitter_auth import has_accounts, ACCOUNTS_DB_PATH
    if has_accounts():
        import os
        from datetime import datetime, timezone
        mtime = os.path.getmtime(ACCOUNTS_DB_PATH)
        saved_at = datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()
        return {"status": "configured", "saved_at": saved_at, "message": "账号已配置"}
    return {"status": "none", "message": "尚未配置 X 账号"}


@app.post("/api/twitter/add-account")
async def twitter_add_account(body: dict):
    """添加 X 账号并登录（需提供 username/password/email）"""
    username = body.get("username", "").strip()
    password = body.get("password", "").strip()
    email = body.get("email", "").strip()
    email_password = body.get("email_password", "").strip()

    if not username or not password or not email:
        return JSONResponse(
            {"status": "error", "message": "username / password / email 均为必填"},
            status_code=400,
        )
    try:
        from backend.collector.twitter_auth import add_account
        result = await add_account(username, password, email, email_password)
        return {"status": "ok", "message": f"账号已添加，登录成功 {result['logged_in']}/{result['total']} 个"}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse(
            {"status": "error", "message": f"添加失败: {e}"},
            status_code=500,
        )
```

**Step 2: 验证服务能启动（不报 import 错误）**

```bash
python -c "from backend.main import app; print('OK')"
```

Expected: OK

**Step 3: Commit**

```bash
git add backend/main.py
git commit -m "feat(api): add /api/twitter/status and /api/twitter/add-account endpoints"
```

---

## Task 8: ConfigPage.jsx — Twitter 账号管理 UI

**Files:**
- Modify: `frontend/src/pages/ConfigPage.jsx`（新增 TwitterSection 组件 + 在页面中引用）

**Step 1: 在 ConfigPage.jsx 中新增 TwitterSection 组件**

在文件中 `WechatSection` 组件定义结束之后，追加以下组件：

```jsx
/* ---- Twitter/X 账号管理 ---- */
function TwitterSection({ accounts, onChange }) {
  const [status, setStatus] = useState(null)
  const [form, setForm] = useState({ username: '', password: '', email: '', email_password: '' })
  const [adding, setAdding] = useState(false)
  const [msg, setMsg] = useState('')

  useEffect(() => {
    axios.get('/api/twitter/status').then(r => setStatus(r.data)).catch(() => {})
  }, [])

  const addAccount = async () => {
    if (!form.username || !form.password || !form.email) {
      setMsg('用户名、密码、邮箱均为必填')
      return
    }
    try {
      setMsg('登录中...')
      const r = await axios.post('/api/twitter/add-account', form)
      setMsg(r.data.message)
      setForm({ username: '', password: '', email: '', email_password: '' })
      setAdding(false)
      const s = await axios.get('/api/twitter/status')
      setStatus(s.data)
    } catch (e) {
      setMsg(e.response?.data?.message || '添加失败')
    }
  }

  return (
    <section className="bg-white rounded-xl border border-gray-100 p-5">
      <div className="flex items-center justify-between mb-4">
        <h3 className="font-medium text-gray-800">
          Twitter / X 账号监控
          <span className="ml-2 text-sm text-gray-400 font-normal">({accounts.length} 个账号)</span>
        </h3>
        <span className={`text-xs px-2 py-0.5 rounded-full ${status?.status === 'configured' ? 'bg-green-50 text-green-600' : 'bg-yellow-50 text-yellow-600'}`}>
          {status?.status === 'configured' ? '小号已配置' : '未配置小号'}
        </span>
      </div>

      {/* 监控账号列表 */}
      <div className="space-y-1.5 mb-3">
        {accounts.map((acct, i) => (
          <div key={i} className="flex items-center justify-between text-sm py-1.5 px-3 bg-gray-50 rounded-lg">
            <span className="text-gray-700">{acct.display_name} <span className="text-gray-400">@{acct.handle}</span></span>
            <button className="text-xs text-red-400 hover:text-red-600" onClick={() => onChange(accounts.filter((_, j) => j !== i))}>删除</button>
          </div>
        ))}
        {accounts.length === 0 && <p className="text-sm text-gray-400">暂无监控账号</p>}
      </div>

      {/* 添加监控账号 */}
      <div className="flex gap-2 mb-4">
        <input
          className="flex-1 border border-gray-200 rounded px-2 py-1.5 text-sm"
          placeholder="Handle（如 OpenAI）"
          id="tw-handle"
        />
        <input
          className="flex-1 border border-gray-200 rounded px-2 py-1.5 text-sm"
          placeholder="显示名称"
          id="tw-display"
        />
        <button
          className="text-sm text-blue-600 hover:text-blue-800 px-2"
          onClick={() => {
            const h = document.getElementById('tw-handle').value.trim()
            const d = document.getElementById('tw-display').value.trim()
            if (h) { onChange([...accounts, { handle: h, display_name: d || h }]); document.getElementById('tw-handle').value = ''; document.getElementById('tw-display').value = '' }
          }}
        >+ 添加</button>
      </div>

      {/* X 小号凭证 */}
      <div className="border-t border-gray-100 pt-3">
        <div className="flex items-center justify-between mb-2">
          <span className="text-sm text-gray-600">X 小号凭证（用于采集）</span>
          {!adding && (
            <button className="text-xs text-blue-600 hover:text-blue-800" onClick={() => setAdding(true)}>
              {status?.status === 'configured' ? '重新配置' : '+ 添加账号'}
            </button>
          )}
        </div>
        {adding && (
          <div className="space-y-2 mb-2">
            <div className="grid grid-cols-2 gap-2">
              <input className="border border-gray-200 rounded px-2 py-1.5 text-sm" placeholder="用户名 *" value={form.username} onChange={e => setForm({ ...form, username: e.target.value })} />
              <input className="border border-gray-200 rounded px-2 py-1.5 text-sm" placeholder="密码 *" type="password" value={form.password} onChange={e => setForm({ ...form, password: e.target.value })} />
              <input className="border border-gray-200 rounded px-2 py-1.5 text-sm" placeholder="注册邮箱 *" value={form.email} onChange={e => setForm({ ...form, email: e.target.value })} />
              <input className="border border-gray-200 rounded px-2 py-1.5 text-sm" placeholder="邮箱密码（可选）" type="password" value={form.email_password} onChange={e => setForm({ ...form, email_password: e.target.value })} />
            </div>
            <div className="flex gap-2">
              <button className="text-sm bg-blue-600 text-white px-3 py-1.5 rounded hover:bg-blue-700" onClick={addAccount}>登录</button>
              <button className="text-sm text-gray-500 hover:text-gray-700" onClick={() => { setAdding(false); setMsg('') }}>取消</button>
            </div>
          </div>
        )}
        {msg && <p className="text-xs text-gray-500 mt-1">{msg}</p>}
      </div>
    </section>
  )
}
```

**Step 2: 在 ConfigPage 主体中引用 TwitterSection**

找到 ConfigPage 主组件中渲染 `<WechatSection>` 的地方，在其后加：

```jsx
<TwitterSection
  accounts={cfg.sources?.twitter?.accounts || []}
  onChange={accounts => {
    const twitter = { ...(cfg.sources?.twitter || {}), accounts }
    setCfg({ ...cfg, sources: { ...cfg.sources, twitter } })
  }}
/>
```

**Step 3: 构建前端**

```bash
cd frontend && npm run build
```

Expected: 构建成功，无 error

**Step 4: Commit**

```bash
git add frontend/src/pages/ConfigPage.jsx frontend/dist
git commit -m "feat(frontend): add Twitter account management section to ConfigPage"
```

---

## Task 9: 端到端验证

**Step 1: 启动服务**

```bash
python -m uvicorn backend.main:app --reload
```

**Step 2: 验证 Twitter API 端点**

```bash
curl http://localhost:8000/api/twitter/status
```

Expected: `{"status": "none", "message": "尚未配置 X 账号"}`

**Step 3: 验证配置页显示 Twitter 区块**

打开 `http://localhost:8000`，进入配置页，确认显示「Twitter / X 账号监控」区块，账号列表与 config.yaml 中的 11 个账号一致。

**Step 4: 运行全量测试**

```bash
pytest tests/ -v --ignore=tests/test_analyzer.py -x
```

Expected: 无新增失败

**Step 5: Commit 收尾**

```bash
git add .
git commit -m "feat(twitter): complete Twitter/X account monitoring integration"
```
