# 微信公众号采集器 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 在 AI News Radar 中新增微信公众号文章采集能力，支持用户配置监控的公众号列表，每天自动抓取昨天的文章并接入现有分析 Pipeline。

**Architecture:** 新增 `wechat.py` 采集器模块，使用 Selenium 自动化微信公众号后台获取 token/cookie，再通过 `wechatarticles` 库按公众号名称拉取文章列表。凭证缓存到本地文件，过期后提示重新扫码。公众号列表存储在 `sources.yaml` 中作为 `type: wechat` 的信源，与 rss/scrape 平级。前端配置页新增公众号管理区。

**Tech Stack:** selenium, webdriver-manager, wechatarticles, Chrome/ChromeDriver

---

## 整体设计

### 数据流

```
sources.yaml (type: wechat)
        ↓
WechatCollector.collect(source)
        ↓
检查凭证 → 过期则提示扫码（首次自动弹出浏览器）
        ↓
wechatarticles.get_urls(nickname, begin, count)
        ↓
过滤昨天的文章 → 标准 news item dict
        ↓
接入 Pipeline（去重 → 排名 → LLM 分析）
```

### sources.yaml 新增格式

```yaml
# === 微信公众号 ===
- name: 机器之心（公众号）
  institution: 机器之心
  tier: 2
  indicator: industry
  type: wechat
  nickname: 机器之心        # 公众号名称，用于搜索
```

### 凭证管理

- 凭证文件：`data/wechat_credentials.json`（token + cookies + 过期时间）
- 凭证有效期：约 4-6 小时（微信后台 session 限制）
- 过期策略：采集前检查，过期则跳过并 emit 提示信息
- 手动刷新：新增 API `POST /api/wechat/login` 触发浏览器扫码

### 反爬策略

- 每个公众号请求间随机延迟 5-15 秒
- 单次采集最多处理 10 个公众号
- 每个公众号最多拉取 5 篇文章

---

## Task 1: 安装依赖

**Files:**
- Modify: `backend/requirements.txt`

**Step 1: 添加依赖**

在 `backend/requirements.txt` 末尾追加：

```
selenium==4.25.0
webdriver-manager==4.0.2
wechatarticles==0.6.8
```

**Step 2: 安装**

Run: `cd D:/AI/ClaudeProject/ai-news-radar && pip install selenium webdriver-manager wechatarticles`

**Step 3: 验证安装**

Run: `python -c "from selenium import webdriver; from wechatarticles import OfficialWeChat; print('OK')"`
Expected: `OK`

**Step 4: Commit**

```bash
git add backend/requirements.txt
git commit -m "deps: add selenium, webdriver-manager, wechatarticles for WeChat collector"
```

---

## Task 2: 实现凭证管理模块

**Files:**
- Create: `backend/collector/wechat_auth.py`
- Test: 手动验证

**Step 1: 创建凭证管理器**

```python
"""微信公众号后台凭证管理（Selenium 扫码登录 + 凭证缓存）"""
import json
import os
import time
from datetime import datetime, timezone

CREDENTIALS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "data", "wechat_credentials.json",
)
# 凭证有效期 4 小时（微信 session 通常 4-6h）
CREDENTIAL_TTL = 4 * 3600


def _load_cached():
    """加载缓存的凭证，过期则返回 None。"""
    if not os.path.exists(CREDENTIALS_PATH):
        return None
    try:
        with open(CREDENTIALS_PATH, encoding="utf-8") as f:
            data = json.load(f)
        if time.time() - data.get("saved_at", 0) > CREDENTIAL_TTL:
            print("[WechatAuth] 凭证已过期", flush=True)
            return None
        if not data.get("token") or not data.get("cookie"):
            return None
        return data
    except Exception:
        return None


def _save_cache(token: str, cookie: str):
    os.makedirs(os.path.dirname(CREDENTIALS_PATH), exist_ok=True)
    with open(CREDENTIALS_PATH, "w", encoding="utf-8") as f:
        json.dump({
            "token": token,
            "cookie": cookie,
            "saved_at": time.time(),
            "saved_at_human": datetime.now(timezone.utc).isoformat(),
        }, f, ensure_ascii=False, indent=2)
    print("[WechatAuth] 凭证已缓存", flush=True)


def login_and_get_credentials(headless: bool = False) -> dict | None:
    """启动浏览器，扫码登录微信公众号后台，提取 token 和 cookie。

    Returns:
        {"token": str, "cookie": str} 或 None（登录失败/超时）
    """
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.service import Service
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        from webdriver_manager.chrome import ChromeDriverManager
    except ImportError as e:
        print(f"[WechatAuth] 缺少依赖: {e}", flush=True)
        return None

    options = Options()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])

    driver = None
    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        driver.get("https://mp.weixin.qq.com/")
        print("[WechatAuth] 请在浏览器中扫码登录微信公众号后台...", flush=True)

        # 等待登录成功（URL 变为后台首页），最长等待 120 秒
        WebDriverWait(driver, 120).until(
            EC.url_contains("cgi-bin/home")
        )
        print("[WechatAuth] 登录成功，提取凭证...", flush=True)

        # 提取 token（从 URL 参数）
        current_url = driver.current_url
        token = ""
        if "token=" in current_url:
            token = current_url.split("token=")[1].split("&")[0]

        # 如果 URL 中没有 token，从 localStorage 尝试
        if not token:
            token = driver.execute_script(
                "return localStorage.getItem('token') || ''"
            )

        # 提取 cookies
        cookies = driver.get_cookies()
        cookie_str = "; ".join(f"{c['name']}={c['value']}" for c in cookies)

        if not token:
            print("[WechatAuth] 未能提取 token", flush=True)
            return None

        _save_cache(token, cookie_str)
        return {"token": token, "cookie": cookie_str}

    except Exception as e:
        print(f"[WechatAuth] 登录失败: {e}", flush=True)
        return None
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass


def get_credentials() -> dict | None:
    """获取有效凭证（优先缓存，无缓存则返回 None）。"""
    return _load_cached()
```

**Step 2: 验证模块可导入**

Run: `cd D:/AI/ClaudeProject/ai-news-radar && python -c "from backend.collector.wechat_auth import get_credentials; print('OK')"`
Expected: `OK`

**Step 3: Commit**

```bash
git add backend/collector/wechat_auth.py
git commit -m "feat: add WeChat MP credential manager with QR code login"
```

---

## Task 3: 实现微信公众号采集器

**Files:**
- Create: `backend/collector/wechat.py`

**Step 1: 创建采集器**

```python
"""微信公众号文章采集器"""
import hashlib
import random
import time
from datetime import datetime, timezone
from typing import Any, Dict, List

from backend.collector.filters import is_ai_related
from backend.date_filters import is_yesterday


class WechatCollector:
    def __init__(self, max_per_source: int = 5):
        self.max_per_source = max_per_source

    def collect(self, source: Dict[str, Any]) -> List[Dict]:
        """采集单个公众号昨天的文章。

        source 需包含:
            - nickname: 公众号名称
            - name / institution / tier / indicator: 标准信源字段
        """
        nickname = source.get("nickname", "")
        if not nickname:
            print(f"[Wechat] {source['name']}: 缺少 nickname 字段", flush=True)
            return []

        # 获取凭证
        from backend.collector.wechat_auth import get_credentials
        creds = get_credentials()
        if not creds:
            print(f"[Wechat] 凭证无效或已过期，跳过微信采集。请通过 POST /api/wechat/login 重新扫码", flush=True)
            return []

        try:
            from wechatarticles import OfficialWeChat
        except ImportError:
            print("[Wechat] wechatarticles 未安装，跳过", flush=True)
            return []

        try:
            ow = OfficialWeChat(token=creds["token"], cookie=creds["cookie"])
            # 获取文章列表（一次取最多 5 篇）
            articles_data = ow.get_urls(
                nickname=nickname,
                begin=0,
                count=self.max_per_source,
            )
        except Exception as e:
            err_msg = str(e)
            if "invalid token" in err_msg.lower() or "invalid cookie" in err_msg.lower() or "freq" in err_msg.lower():
                print(f"[Wechat] {nickname}: 凭证失效或频率限制: {e}", flush=True)
            else:
                print(f"[Wechat] {nickname}: 获取文章列表失败: {e}", flush=True)
            return []

        # wechatarticles 返回格式: {"title": [...], "url": [...], "date": [...]}
        # 或者可能是 list of dict，需要兼容
        items = self._parse_articles(articles_data, source)

        # 随机延迟，避免请求过于频繁
        delay = random.uniform(5, 15)
        time.sleep(delay)

        return items

    def _parse_articles(self, data, source: Dict) -> List[Dict]:
        """解析 wechatarticles 返回的数据为标准 news item。"""
        items = []

        if not data:
            return items

        # 兼容两种返回格式
        titles, urls, dates = [], [], []
        if isinstance(data, dict):
            titles = data.get("title", [])
            urls = data.get("url", [])
            dates = data.get("date", [])
        elif isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    titles.append(item.get("title", ""))
                    urls.append(item.get("url", ""))
                    dates.append(item.get("date", ""))

        for i in range(len(titles)):
            title = titles[i] if i < len(titles) else ""
            url = urls[i] if i < len(urls) else ""
            pub_ts = dates[i] if i < len(dates) else ""

            if not title or not url:
                continue

            # 解析发布时间（微信返回 Unix 时间戳）
            published = self._parse_timestamp(pub_ts)

            # 只要昨天的文章
            if not is_yesterday(published):
                continue

            # AI 相关性预筛
            if not is_ai_related(title, ""):
                continue

            news_id = hashlib.md5(url.encode()).hexdigest()
            items.append({
                "id": news_id,
                "url": url,
                "title": title[:200],
                "summary": "",  # 微信列表不含摘要，后续由 enricher 补充
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

    @staticmethod
    def _parse_timestamp(value) -> str:
        """将微信返回的时间戳（Unix 秒/字符串）转为 ISO 格式。"""
        if not value:
            return ""
        try:
            if isinstance(value, (int, float)):
                ts = int(value)
            else:
                ts = int(str(value).strip())
            return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
        except (ValueError, TypeError, OSError):
            return str(value)
```

**Step 2: 验证模块可导入**

Run: `cd D:/AI/ClaudeProject/ai-news-radar && python -c "from backend.collector.wechat import WechatCollector; print('OK')"`
Expected: `OK`

**Step 3: Commit**

```bash
git add backend/collector/wechat.py
git commit -m "feat: add WeChat MP article collector"
```

---

## Task 4: 集成到 Pipeline

**Files:**
- Modify: `backend/pipeline.py`

**Step 1: 在 Pipeline.__init__ 中初始化 WechatCollector**

在 `self.web_scraper = ...` 之后添加：

```python
from backend.collector.wechat import WechatCollector
self.wechat_collector = WechatCollector(
    max_per_source=config["collection"]["max_per_source"],
)
```

**Step 2: 在 Pipeline.run 的采集循环中添加 wechat 分支**

将 `pipeline.py` 采集循环中的 type 判断从：

```python
if source["type"] == "rss":
    future = executor.submit(self.rss_collector.collect, source)
elif source["type"] == "scrape":
    future = executor.submit(self.web_scraper.collect, source)
else:
    future = None
```

改为：

```python
if source["type"] == "rss":
    future = executor.submit(self.rss_collector.collect, source)
elif source["type"] == "scrape":
    future = executor.submit(self.web_scraper.collect, source)
elif source["type"] == "wechat":
    future = executor.submit(self.wechat_collector.collect, source)
else:
    future = None
```

**Step 3: 验证 Pipeline 可正常初始化**

Run: `cd D:/AI/ClaudeProject/ai-news-radar && python -c "from backend.pipeline import Pipeline; print('OK')"`
Expected: `OK`

**Step 4: Commit**

```bash
git add backend/pipeline.py
git commit -m "feat: integrate WeChat collector into Pipeline"
```

---

## Task 5: 添加示例公众号信源

**Files:**
- Modify: `backend/collector/sources.yaml`

**Step 1: 在 sources.yaml 末尾添加微信公众号区块**

```yaml

  # === 微信公众号 (2026-03-23) ===
  # 需要先通过 POST /api/wechat/login 扫码授权

  - name: 量子位（公众号）
    institution: 量子位
    tier: 2
    indicator: industry
    type: wechat
    nickname: 量子位

  - name: 机器之心（公众号）
    institution: 机器之心
    tier: 2
    indicator: industry
    type: wechat
    nickname: 机器之心

  - name: 新智元（公众号）
    institution: 新智元
    tier: 2
    indicator: industry
    type: wechat
    nickname: 新智元
```

**Step 2: 验证 YAML 可正常解析**

Run: `cd D:/AI/ClaudeProject/ai-news-radar && python -c "from backend.pipeline import load_sources; sources = load_sources(); wc = [s for s in sources if s.get('type') == 'wechat']; print(f'{len(wc)} wechat sources'); [print(f'  - {s[\"nickname\"]}') for s in wc]"`

Expected:
```
3 wechat sources
  - 量子位
  - 机器之心
  - 新智元
```

**Step 3: Commit**

```bash
git add backend/collector/sources.yaml
git commit -m "feat: add sample WeChat MP sources to sources.yaml"
```

---

## Task 6: 新增后端 API（扫码登录 + 凭证状态）

**Files:**
- Modify: `backend/main.py`

**Step 1: 在 `/api/sources` 路由之后添加微信相关 API**

```python
@app.get("/api/wechat/status")
def wechat_status():
    """获取微信凭证状态"""
    from backend.collector.wechat_auth import get_credentials, CREDENTIALS_PATH
    import os, json
    creds = get_credentials()
    if creds:
        # 读取保存时间
        try:
            with open(CREDENTIALS_PATH, encoding="utf-8") as f:
                data = json.load(f)
            saved_at = data.get("saved_at_human", "")
        except Exception:
            saved_at = ""
        return {"status": "valid", "saved_at": saved_at}
    elif os.path.exists(CREDENTIALS_PATH):
        return {"status": "expired", "message": "凭证已过期，请重新扫码"}
    else:
        return {"status": "none", "message": "尚未登录，请扫码授权"}


@app.post("/api/wechat/login")
def wechat_login(background_tasks: BackgroundTasks):
    """触发微信公众号扫码登录（后台弹出浏览器）"""
    from backend.collector.wechat_auth import login_and_get_credentials
    # 同步执行（需要等待用户扫码），不适合放后台
    result = login_and_get_credentials(headless=False)
    if result:
        return {"status": "ok", "message": "登录成功，凭证已缓存"}
    return JSONResponse(
        {"status": "error", "message": "登录失败或超时，请重试"},
        status_code=400,
    )
```

**注意**: `wechat_login` 是同步阻塞的（需要等待用户扫码），请求会持续 ~2 分钟。前端调用时需设置较长的 timeout。

**Step 2: 验证 API 可注册**

Run: `cd D:/AI/ClaudeProject/ai-news-radar && python -c "from backend.main import app; routes = [r.path for r in app.routes]; print('/api/wechat/status' in routes, '/api/wechat/login' in routes)"`
Expected: `True True`

**Step 3: Commit**

```bash
git add backend/main.py
git commit -m "feat: add WeChat login and status API endpoints"
```

---

## Task 7: 前端配置页 - 添加微信公众号管理

**Files:**
- Modify: `frontend/src/pages/ConfigPage.jsx`

**Step 1: 在「定时任务」section 之后、保存按钮之前，添加微信公众号管理区**

新增一个 section，包含：
- 凭证状态指示（绿色/红色/灰色 badge）
- 「扫码登录」按钮
- 已配置的微信公众号列表（从 `/api/sources` 获取 type=wechat 的）
- 说明文字：新增/删除公众号需编辑 `sources.yaml`

需要添加的 state:
```jsx
const [wechatStatus, setWechatStatus] = useState(null)
const [wechatLogging, setWechatLogging] = useState(false)
const [wechatSources, setWechatSources] = useState([])
```

useEffect 中额外请求:
```jsx
axios.get('/api/wechat/status').then(r => setWechatStatus(r.data)).catch(() => {})
axios.get('/api/sources').then(r => {
  setWechatSources(r.data.filter(s => s.type === 'wechat'))
}).catch(() => {})
```

登录函数:
```jsx
const loginWechat = async () => {
  setWechatLogging(true)
  try {
    const res = await axios.post('/api/wechat/login', {}, { timeout: 180000 })
    setWechatStatus({ status: 'valid', saved_at: new Date().toISOString() })
    alert(res.data.message)
  } catch (e) {
    alert('登录失败: ' + (e.response?.data?.message || e.message))
  } finally {
    setWechatLogging(false)
  }
}
```

JSX section:
```jsx
{/* 微信公众号 */}
<section className="bg-white rounded-xl border border-gray-100 p-5">
  <h3 className="font-medium text-gray-800 mb-4">微信公众号监控</h3>

  {/* 凭证状态 */}
  <div className="flex items-center gap-3 mb-4">
    <span className={`inline-block w-2.5 h-2.5 rounded-full ${
      wechatStatus?.status === 'valid' ? 'bg-green-500' :
      wechatStatus?.status === 'expired' ? 'bg-red-400' : 'bg-gray-300'
    }`} />
    <span className="text-sm text-gray-600">
      {wechatStatus?.status === 'valid'
        ? `凭证有效（${wechatStatus.saved_at?.slice(0, 16) || ''}）`
        : wechatStatus?.status === 'expired'
        ? '凭证已过期'
        : '尚未登录'}
    </span>
    <button
      onClick={loginWechat}
      disabled={wechatLogging}
      className="ml-auto bg-green-600 text-white px-4 py-1.5 rounded-lg text-sm font-medium hover:bg-green-700 disabled:opacity-50 transition-colors"
    >
      {wechatLogging ? '等待扫码...' : '扫码登录'}
    </button>
  </div>

  {/* 已配置公众号列表 */}
  {wechatSources.length > 0 ? (
    <div className="space-y-2">
      <p className="text-xs text-gray-500 mb-2">已配置的公众号：</p>
      {wechatSources.map((s, i) => (
        <div key={i} className="flex items-center gap-2 text-sm text-gray-700 bg-gray-50 rounded-lg px-3 py-2">
          <span className="font-medium">{s.nickname}</span>
          <span className="text-gray-400">·</span>
          <span className="text-gray-500">{s.institution}</span>
        </div>
      ))}
    </div>
  ) : (
    <p className="text-sm text-gray-400">暂无配置的公众号</p>
  )}
  <p className="text-xs text-gray-400 mt-3">
    增减公众号请编辑 backend/collector/sources.yaml，type 设为 wechat
  </p>
</section>
```

**Step 2: 构建前端**

Run: `cd D:/AI/ClaudeProject/ai-news-radar/frontend && npm run build`

**Step 3: Commit**

```bash
git add frontend/src/pages/ConfigPage.jsx
git commit -m "feat: add WeChat MP management section to config page"
```

---

## Task 8: 更新项目文档

**Files:**
- Modify: `CLAUDE.md`
- Modify: `docs/devlog.md`

**Step 1: 在 CLAUDE.md 的「开发约定」部分追加**

```markdown
- **微信公众号采集**：`type: wechat` 信源需在 `sources.yaml` 中配置 `nickname` 字段；首次使用需通过前端配置页「扫码登录」或调用 `POST /api/wechat/login`；凭证缓存于 `data/wechat_credentials.json`（约 4 小时有效）
```

**Step 2: 在 devlog.md 顶部追加当天记录**

```markdown
### 新增微信公众号采集器
- 新增 `wechat_auth.py`：Selenium 扫码登录 + 凭证缓存（4h TTL）
- 新增 `wechat.py`：基于 wechatarticles 库的公众号文章采集器
- Pipeline 集成：`type: wechat` 与 rss/scrape 平级处理
- 后端 API：`GET /api/wechat/status`、`POST /api/wechat/login`
- 前端配置页：凭证状态显示 + 扫码登录按钮 + 公众号列表
- 示例信源：量子位、机器之心、新智元
```

**Step 3: Commit**

```bash
git add CLAUDE.md docs/devlog.md
git commit -m "docs: add WeChat MP collector documentation"
```

---

## Task 9: 端到端验证

**Step 1: 启动后端**

Run: `cd D:/AI/ClaudeProject/ai-news-radar && python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload`

**Step 2: 验证 API**

```bash
# 检查凭证状态
curl http://127.0.0.1:8000/api/wechat/status

# 检查信源列表包含 wechat 类型
curl -s http://127.0.0.1:8000/api/sources | python -c "import sys,json; sources=json.load(sys.stdin); wc=[s for s in sources if s.get('type')=='wechat']; print(f'{len(wc)} wechat sources')"
```

**Step 3: 访问前端**

打开 `http://localhost:8000`，进入配置页，确认：
- 能看到「微信公众号监控」区域
- 凭证状态显示为「尚未登录」
- 已配置公众号列表显示 3 个

**Step 4: 扫码登录测试（可选）**

点击「扫码登录」按钮 → Chrome 弹出 → 扫码 → 返回「登录成功」→ 状态变绿

**Step 5: 采集测试（可选，需先扫码）**

点击「立即采集」→ 观察控制台日志中出现 `[Wechat]` 相关输出

---

## 风险与注意事项

1. **凭证有效期短**：微信后台 session 约 4-6 小时过期，定时任务（每天 8:00）前需确保凭证有效。可在 7:50 手动扫码，或后续改为自动提醒。
2. **反爬限制**：微信对频繁请求敏感，采集器已内置 5-15 秒随机延迟。不要短时间多次运行。
3. **wechatarticles 库稳定性**：该库依赖微信公众号后台接口，微信更新可能导致失效，需关注上游更新。
4. **文章正文**：列表接口只返回标题和 URL，正文需要 enricher 回源抓取（已有机制）。
5. **公众号需要自有**：Selenium 登录需要你有一个微信公众号的管理权限。
