# 微信公众号采集器 Playwright 重构方案

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将微信公众号采集器从 Selenium + wechatarticles 方案重构为纯 Playwright 方案，去掉 3 个新依赖，直接调用微信后台 API，与项目技术栈统一。

**Architecture:** 基于项目已有的 Playwright，用 `storage_state` 管理登录 session，在浏览器内通过 `page.evaluate(fetch(...))` 调用微信公众号后台 `searchbiz` / `appmsgpublish` API 获取文章列表。

**参考项目:** [feedgrab](https://github.com/iBigQiang/feedgrab) 的 `fetchers/mpweixin_account.py`

---

## 整体设计

### 与旧方案对比

| 维度 | 旧方案（Selenium） | 新方案（Playwright） |
|---|---|---|
| 浏览器引擎 | Selenium + ChromeDriver | Playwright（项目已有） |
| 反检测 | 2 个 flag | 多个反自动化 flag |
| 凭证存储 | 手动提取 token+cookie → JSON | Playwright storage_state 整体保存 |
| 文章列表 API | wechatarticles 第三方库 | 直接调用微信后台 searchbiz + appmsgpublish |
| 新增依赖 | selenium, webdriver-manager, wechatarticles | 无（Playwright 已有） |

### 数据流

```
登录:
  POST /api/wechat/login → Playwright 有头浏览器 → 用户扫码
  → storage_state 保存到 data/wechat_session.json

采集:
  Pipeline.run()
  → WechatCollector.start()       # 启动浏览器，加载 session，验证有效性
  → 对每个 wechat 源:
      → searchbiz 查 fakeid（命中缓存则跳过）
      → appmsgpublish 拉文章列表
      → 过滤昨日 + AI 相关 → 标准 news item
      → 随机延迟 3-8s
  → WechatCollector.stop()        # 关闭浏览器
```

### 凭证管理

- Session 文件：`data/wechat_session.json`（Playwright storage_state 格式）
- 有效期检测：加载 session 后访问 mp.weixin.qq.com，检查是否重定向到登录页（比固定 TTL 更准确）
- Token 提取：从登录成功后的 URL 参数 `token=` 中获取
- 登录触发：`POST /api/wechat/login`（前端按钮）

### fakeid 缓存

- 文件：`data/wechat_fakeids.json`
- 格式：`{nickname: {fakeid, updated_at}}`
- 首次采集通过 searchbiz API 查询并缓存，后续直接使用

### 反检测

```python
"--disable-blink-features=AutomationControlled",
"--disable-features=AutomationControlled",
"--disable-infobars",
"--no-first-run",
```

### Pipeline 集成

- RSS/scrape 源：并行采集（现有逻辑不变）
- wechat 源：串行采集，共享浏览器实例
- 两者之间可并行执行

---

## Task 1: 清理旧依赖

**Files:**
- Modify: `backend/requirements.txt`

**Step 1: 移除 selenium/webdriver-manager/wechatarticles**

从 `backend/requirements.txt` 中删除：
```
selenium==4.25.0
webdriver-manager==4.0.2
wechatarticles==0.6.8
```

**Step 2: 卸载旧依赖**

Run: `pip uninstall -y selenium webdriver-manager wechatarticles`

**Step 3: Commit**

```bash
git add backend/requirements.txt
git commit -m "deps: remove selenium/webdriver-manager/wechatarticles, will use Playwright instead"
```

---

## Task 2: 重写凭证管理模块

**Files:**
- Rewrite: `backend/collector/wechat_auth.py`

**Step 1: 重写为 Playwright 版本**

```python
"""微信公众号后台凭证管理（Playwright 扫码登录 + storage_state 缓存）"""
import json
import os
import re

SESSION_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "data", "wechat_session.json",
)


def has_session() -> bool:
    """检查是否存在 session 文件。"""
    return os.path.exists(SESSION_PATH)


def _get_chromium_args() -> list[str]:
    """反检测启动参数。"""
    return [
        "--disable-blink-features=AutomationControlled",
        "--disable-features=AutomationControlled",
        "--disable-infobars",
        "--no-first-run",
    ]


def login_and_save_session() -> dict | None:
    """启动 Playwright 有头浏览器，扫码登录微信公众号后台，保存 storage_state。

    Returns:
        {"token": str, "session_path": str} 或 None
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[WechatAuth] playwright 未安装", flush=True)
        return None

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=_get_chromium_args(),
        )
        context = browser.new_context()
        page = context.new_page()

        try:
            page.goto("https://mp.weixin.qq.com/")
            print("[WechatAuth] 请在浏览器中扫码登录微信公众号后台...", flush=True)

            # 等待登录成功（URL 出现 token=），最长 120 秒
            page.wait_for_url("**/cgi-bin/home*", timeout=120_000)
            print("[WechatAuth] 登录成功，保存 session...", flush=True)

            # 提取 token
            token = _extract_token(page.url)
            if not token:
                print("[WechatAuth] 未能提取 token", flush=True)
                return None

            # 保存 storage_state
            os.makedirs(os.path.dirname(SESSION_PATH), exist_ok=True)
            state = context.storage_state()
            # 在 state 中附加 token metadata
            state["_wechat_token"] = token
            with open(SESSION_PATH, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False, indent=2)

            print("[WechatAuth] session 已保存", flush=True)
            return {"token": token, "session_path": SESSION_PATH}

        except Exception as e:
            print(f"[WechatAuth] 登录失败: {e}", flush=True)
            return None
        finally:
            browser.close()


def load_session() -> dict | None:
    """加载 session 文件，返回 {token, session_path} 或 None。"""
    if not has_session():
        return None
    try:
        with open(SESSION_PATH, encoding="utf-8") as f:
            state = json.load(f)
        token = state.get("_wechat_token", "")
        if not token:
            return None
        return {"token": token, "session_path": SESSION_PATH}
    except Exception:
        return None


def _extract_token(url: str) -> str:
    """从 URL 中提取 token 参数。"""
    m = re.search(r"token=(\d+)", url)
    return m.group(1) if m else ""
```

**Step 2: 验证模块可导入**

Run: `cd D:/AI/ClaudeProject/ai-news-radar && python -c "from backend.collector.wechat_auth import has_session, load_session; print('OK')"`
Expected: `OK`

**Step 3: Commit**

```bash
git add backend/collector/wechat_auth.py
git commit -m "refactor: rewrite wechat_auth to use Playwright storage_state"
```

---

## Task 3: 重写微信采集器

**Files:**
- Rewrite: `backend/collector/wechat.py`

**Step 1: 创建 fakeid 缓存管理**

在 wechat.py 顶部定义：

```python
FAKEIDS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "data", "wechat_fakeids.json",
)

def _load_fakeids() -> dict:
    if not os.path.exists(FAKEIDS_PATH):
        return {}
    try:
        with open(FAKEIDS_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _save_fakeids(data: dict):
    os.makedirs(os.path.dirname(FAKEIDS_PATH), exist_ok=True)
    with open(FAKEIDS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
```

**Step 2: 实现 WechatCollector**

```python
"""微信公众号文章采集器（Playwright + 微信后台 API）"""
import hashlib
import json
import os
import random
import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, List

from backend.collector.filters import is_ai_related
from backend.date_filters import is_yesterday

FAKEIDS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "data", "wechat_fakeids.json",
)


def _load_fakeids() -> dict:
    if not os.path.exists(FAKEIDS_PATH):
        return {}
    try:
        with open(FAKEIDS_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_fakeids(data: dict):
    os.makedirs(os.path.dirname(FAKEIDS_PATH), exist_ok=True)
    with open(FAKEIDS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


class WechatCollector:
    def __init__(self, max_per_source: int = 5):
        self.max_per_source = max_per_source
        self._browser = None
        self._context = None
        self._page = None
        self._token = None

    def start(self) -> bool:
        """启动 Playwright 浏览器，加载 session，验证有效性。

        Returns:
            True 如果 session 有效，False 如果失效或无 session。
        """
        from backend.collector.wechat_auth import load_session, SESSION_PATH

        session = load_session()
        if not session:
            print("[Wechat] 无有效 session，跳过微信采集。请通过配置页扫码登录", flush=True)
            return False

        try:
            from playwright.sync_api import sync_playwright
            self._pw = sync_playwright().start()
            self._browser = self._pw.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--disable-features=AutomationControlled",
                    "--disable-infobars",
                    "--no-first-run",
                    "--disable-gpu",
                ],
            )
            self._context = self._browser.new_context(storage_state=SESSION_PATH)
            self._page = self._context.new_page()

            # 验证 session 有效性：访问后台，检查是否重定向到登录页
            self._page.goto("https://mp.weixin.qq.com/", wait_until="domcontentloaded")
            time.sleep(2)
            current_url = self._page.url

            # 提取 token（可能与登录时不同，微信会刷新 token）
            token_match = re.search(r"token=(\d+)", current_url)
            if token_match:
                self._token = token_match.group(1)
                print(f"[Wechat] session 有效，token={self._token}", flush=True)
                return True
            else:
                print("[Wechat] session 已失效（被重定向到登录页），请重新扫码", flush=True)
                self.stop()
                return False

        except Exception as e:
            print(f"[Wechat] 启动浏览器失败: {e}", flush=True)
            self.stop()
            return False

    def stop(self):
        """关闭浏览器，释放资源。"""
        try:
            if self._browser:
                self._browser.close()
            if hasattr(self, '_pw') and self._pw:
                self._pw.stop()
        except Exception:
            pass
        self._browser = None
        self._context = None
        self._page = None
        self._token = None

    def collect(self, source: Dict[str, Any]) -> List[Dict]:
        """采集单个公众号昨天的文章。"""
        nickname = source.get("nickname", "")
        if not nickname:
            print(f"[Wechat] {source['name']}: 缺少 nickname 字段", flush=True)
            return []

        if not self._page or not self._token:
            print("[Wechat] 浏览器未启动或 token 无效", flush=True)
            return []

        # 获取 fakeid（优先缓存）
        fakeid = self._get_fakeid(nickname)
        if not fakeid:
            return []

        # 拉取文章列表
        articles = self._fetch_articles(fakeid, nickname)
        if not articles:
            return []

        # 过滤 + 转换为标准 news item
        items = self._parse_articles(articles, source)

        # 随机延迟
        time.sleep(random.uniform(3, 8))
        return items

    def _get_fakeid(self, nickname: str) -> str | None:
        """获取公众号 fakeid，优先从缓存读取。"""
        cache = _load_fakeids()
        if nickname in cache:
            return cache[nickname]["fakeid"]

        # 调用 searchbiz API
        try:
            result = self._page.evaluate("""
                async ([token, nickname]) => {
                    const url = `/cgi-bin/searchbiz?action=search_biz&token=${token}&lang=zh_CN&f=json&ajax=1&query=${encodeURIComponent(nickname)}&begin=0&count=5`;
                    const resp = await fetch(url, {credentials: 'include'});
                    return await resp.json();
                }
            """, [self._token, nickname])
        except Exception as e:
            print(f"[Wechat] {nickname}: searchbiz 失败: {e}", flush=True)
            return None

        # 从结果中找精确匹配
        biz_list = result.get("list", [])
        fakeid = None
        for biz in biz_list:
            if biz.get("nickname") == nickname:
                fakeid = biz.get("fakeid")
                break
        # 如果无精确匹配，取第一个
        if not fakeid and biz_list:
            fakeid = biz_list[0].get("fakeid")
            print(f"[Wechat] {nickname}: 未找到精确匹配，使用第一个结果", flush=True)

        if not fakeid:
            print(f"[Wechat] {nickname}: 未找到对应公众号", flush=True)
            return None

        # 缓存
        cache[nickname] = {"fakeid": fakeid, "updated_at": datetime.now(timezone.utc).isoformat()}
        _save_fakeids(cache)
        print(f"[Wechat] {nickname}: fakeid={fakeid}（已缓存）", flush=True)
        return fakeid

    def _fetch_articles(self, fakeid: str, nickname: str) -> list:
        """调用 appmsgpublish API 获取文章列表。"""
        try:
            result = self._page.evaluate("""
                async ([token, fakeid, count]) => {
                    const url = `/cgi-bin/appmsgpublish?sub=list&search_field=null&begin=0&count=${count}&query=&fakeid=${fakeid}&type=101_1&free_publish_type=1&sub_action=list_ex&token=${token}&lang=zh_CN&f=json&ajax=1`;
                    const resp = await fetch(url, {credentials: 'include'});
                    return await resp.json();
                }
            """, [self._token, fakeid, self.max_per_source])
        except Exception as e:
            print(f"[Wechat] {nickname}: appmsgpublish 失败: {e}", flush=True)
            return []

        # 解析返回结构
        publish_page = result.get("publish_page", {})
        publish_list = publish_page.get("publish_list", [])

        articles = []
        for publish in publish_list:
            info = publish.get("publish_info", {})
            info_str = info if isinstance(info, str) else json.dumps(info)
            # publish_info 可能是 JSON 字符串
            try:
                if isinstance(info, str):
                    info = json.loads(info)
            except (json.JSONDecodeError, TypeError):
                pass

            appmsg_list = info.get("appmsgex", []) if isinstance(info, dict) else []
            for article in appmsg_list:
                articles.append({
                    "title": article.get("title", ""),
                    "url": article.get("link", ""),
                    "digest": article.get("digest", ""),
                    "update_time": article.get("update_time", 0),
                })
        return articles

    def _parse_articles(self, articles: list, source: Dict) -> List[Dict]:
        """过滤并转换为标准 news item。"""
        items = []
        for article in articles:
            title = article.get("title", "")
            url = article.get("url", "")
            if not title or not url:
                continue

            # 解析时间
            ts = article.get("update_time", 0)
            published = ""
            if ts:
                try:
                    published = datetime.fromtimestamp(int(ts), tz=timezone.utc).isoformat()
                except (ValueError, TypeError, OSError):
                    pass

            # 只要昨天的
            if not is_yesterday(published):
                continue

            # AI 相关性预筛
            digest = article.get("digest", "")
            if not is_ai_related(title, digest):
                continue

            news_id = hashlib.md5(url.encode()).hexdigest()
            items.append({
                "id": news_id,
                "url": url,
                "title": title[:200],
                "summary": digest[:500] if digest else "",
                "full_text": "",
                "source_name": source["name"],
                "source_tier": source["tier"],
                "institution": source["institution"],
                "indicator": source["indicator"],
                "score": 0.0,
                "published_at": published,
                "collected_at": datetime.now(timezone.utc).isoformat(),
            })

        if items:
            print(f"[Wechat] {source['name']}: 获取 {len(items)} 条昨日文章", flush=True)
        return items
```

**Step 3: 验证模块可导入**

Run: `cd D:/AI/ClaudeProject/ai-news-radar && python -c "from backend.collector.wechat import WechatCollector; print('OK')"`
Expected: `OK`

**Step 4: Commit**

```bash
git add backend/collector/wechat.py
git commit -m "refactor: rewrite WechatCollector to use Playwright + direct WeChat API"
```

---

## Task 4: 调整 Pipeline 集成

**Files:**
- Modify: `backend/pipeline.py`

**Step 1: 修改 Pipeline.__init__**

WechatCollector 初始化方式不变：

```python
from backend.collector.wechat import WechatCollector
self.wechat_collector = WechatCollector(
    max_per_source=config["collection"]["max_per_source"],
)
```

**Step 2: 修改 Pipeline.run 采集阶段**

将 wechat 源从线程池中拆出，改为串行采集：

```python
# 分离 wechat 源
wechat_sources = [s for s in sources if s["type"] == "wechat"]
other_sources = [s for s in sources if s["type"] != "wechat"]

# 并行采集 rss/scrape
with ThreadPoolExecutor(...) as executor:
    for source in other_sources:
        if source["type"] == "rss":
            future = executor.submit(self.rss_collector.collect, source)
        elif source["type"] == "scrape":
            future = executor.submit(self.web_scraper.collect, source)
        # ... 收集结果

# 串行采集 wechat（共享浏览器）
if wechat_sources:
    if self.wechat_collector.start():
        try:
            for source in wechat_sources:
                items = self.wechat_collector.collect(source)
                all_items.extend(items)
        finally:
            self.wechat_collector.stop()
```

**Step 3: 验证 Pipeline 可正常初始化**

Run: `cd D:/AI/ClaudeProject/ai-news-radar && python -c "from backend.pipeline import Pipeline; print('OK')"`
Expected: `OK`

**Step 4: Commit**

```bash
git add backend/pipeline.py
git commit -m "refactor: pipeline wechat sources use serial collection with shared browser"
```

---

## Task 5: 更新后端 API

**Files:**
- Modify: `backend/main.py`

**Step 1: 更新 /api/wechat/status**

```python
@app.get("/api/wechat/status")
def wechat_status():
    from backend.collector.wechat_auth import has_session, SESSION_PATH
    if has_session():
        import os
        mtime = os.path.getmtime(SESSION_PATH)
        from datetime import datetime, timezone
        saved_at = datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()
        return {"status": "saved", "saved_at": saved_at, "message": "session 已保存（有效性需采集时验证）"}
    return {"status": "none", "message": "尚未登录，请扫码授权"}
```

注意：不再区分 valid/expired——因为真正的有效性只有在采集时通过浏览器访问才能确认。状态改为 saved/none。

**Step 2: 更新 /api/wechat/login**

```python
@app.post("/api/wechat/login")
def wechat_login():
    from backend.collector.wechat_auth import login_and_save_session
    result = login_and_save_session()
    if result:
        return {"status": "ok", "message": "登录成功，session 已保存"}
    return JSONResponse(
        {"status": "error", "message": "登录失败或超时，请重试"},
        status_code=400,
    )
```

**Step 3: 移除 BackgroundTasks import（如果不再使用）**

检查 main.py 中 BackgroundTasks 是否还有其他用途，如无则移除。

**Step 4: Commit**

```bash
git add backend/main.py
git commit -m "refactor: update wechat API endpoints for Playwright session"
```

---

## Task 6: 更新前端配置页

**Files:**
- Modify: `frontend/src/pages/ConfigPage.jsx`

**Step 1: 调整凭证状态显示**

状态只有两种：`saved`（已保存，显示黄色）和 `none`（未登录，显示灰色）。不再有 expired 状态。

```jsx
<span className={`inline-block w-2.5 h-2.5 rounded-full ${
  wechatStatus?.status === 'saved' ? 'bg-yellow-500' : 'bg-gray-300'
}`} />
<span className="text-sm text-gray-600">
  {wechatStatus?.status === 'saved'
    ? `已保存 session（${wechatStatus.saved_at?.slice(0, 16) || ''}）`
    : '尚未登录'}
</span>
```

**Step 2: 构建前端**

Run: `cd D:/AI/ClaudeProject/ai-news-radar/frontend && npm run build`

**Step 3: Commit**

```bash
git add frontend/src/pages/ConfigPage.jsx
git commit -m "feat: update config page wechat status for Playwright session"
```

---

## Task 7: 更新文档

**Files:**
- Modify: `CLAUDE.md`
- Modify: `docs/devlog.md`

**Step 1: 更新 CLAUDE.md 开发约定**

替换微信公众号采集相关说明为：

```markdown
- **微信公众号采集**：`type: wechat` 信源需在 `sources.yaml` 中配置 `nickname` 字段；首次使用需通过前端配置页「扫码登录」或调用 `POST /api/wechat/login`；基于 Playwright + 微信后台 API（searchbiz/appmsgpublish），session 缓存于 `data/wechat_session.json`，fakeid 缓存于 `data/wechat_fakeids.json`
```

**Step 2: 更新 devlog.md**

在最新记录后追加：

```markdown
### 微信公众号采集器重构为 Playwright 方案 (2026-03-25)
- 参考 feedgrab 项目，去掉 selenium/webdriver-manager/wechatarticles 三个依赖
- 改用 Playwright storage_state 管理登录 session
- 直接调用微信后台 searchbiz + appmsgpublish API（浏览器内 page.evaluate）
- fakeid 缓存到 data/wechat_fakeids.json，避免重复搜索
- Pipeline 中 wechat 源串行采集，共享浏览器实例
```

**Step 3: Commit**

```bash
git add CLAUDE.md docs/devlog.md
git commit -m "docs: update documentation for Playwright-based WeChat collector"
```

---

## Task 8: 验证

**Step 1: 验证导入链**

Run: `cd D:/AI/ClaudeProject/ai-news-radar && python -c "from backend.pipeline import Pipeline; from backend.collector.wechat import WechatCollector; from backend.collector.wechat_auth import login_and_save_session; print('ALL OK')"`

**Step 2: 验证旧依赖已清除**

Run: `python -c "import selenium" 2>&1` — 应报 ImportError
Run: `python -c "import wechatarticles" 2>&1` — 应报 ImportError

**Step 3: 启动后端验证 API**

Run: `cd D:/AI/ClaudeProject/ai-news-radar && timeout 5 python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000` 或手动验证

---

## 风险与注意事项

1. **Playwright headless 采集**：微信后台 API 在 headless 浏览器中调用，理论上与有头浏览器行为一致，但如微信加强检测可能需要切换为有头模式
2. **appmsgpublish API 参数**：微信后台接口无官方文档，参数格式可能随微信更新变化
3. **fakeid 缓存**：公众号改名后 fakeid 不变，但 nickname 变了会导致缓存失效，需要手动清理 `data/wechat_fakeids.json`
