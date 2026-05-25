# 踩坑记录

开发过程中遇到的问题及解决方案。

---

## 2026-05-22 | twscrape 未安装导致 X 采集静默失败

**现象**：X/Twitter 一条都采不到，日志只有两行且具误导性：
```
[Twitter] 注入失败: No module named 'twscrape'
[Twitter] 未配置账号，跳过
```
「未配置账号」是假象——账号其实配了，真正原因是 `twscrape` 没装。

**根因**：
1. `twscrape` 被代码引用但从未写进 `backend/requirements.txt`，新环境 `pip install -r` 装不到它。
2. 缺失时报错分散：`collect_all` 在注入环节 catch 到 `ImportError` 打印「注入失败」后继续执行，走到 `has_accounts()` 为假再打印「未配置账号」，掩盖了真实原因。

**解决**：
- `backend/requirements.txt` 补 `twscrape==0.17.0`；它依赖 `beautifulsoup4>=4.13.0`，故 `beautifulsoup4` 同步 `4.12.3 → 4.14.3`（旧 pin 与之冲突）。
- 新增 `twscrape_available()`，`collect_all` 与 4 个 `/api/twitter/*` 端点在 twscrape 缺失时统一返回一条可操作提示（指明 `pip install -r backend/requirements.txt`），不再走误导链路。
- `start.bat` 启动前用 `importlib.util.find_spec` 探测关键模块，缺失则自动 `pip install`。

**附带修复**：`/api/twitter/collect` 测试接口漏注入代理。`normalize_proxy_config` 会剥除 `twitter.proxy` 键，pipeline 在 `__init__` 里手动补回，但该端点没补，导致单独测试采集时 `TWS_PROXY` 为空。改为把代理解析集中进 `collect_all(twitter_cfg, proxy_url=...)`（`_resolve_proxy`：use_proxy 关→空；否则 显式 proxy → 全局 proxy_url → 环境变量 `HTTPS_PROXY/HTTP_PROXY`）。

---

## 2026-05-15 | start.bat 里 `set VAR=val && cmd` 把环境变量末尾带了空格

**现象**：pipeline 跑到去重阶段加载 sentence-transformers 时报：
```
urllib3.exceptions.LocationParseError: Failed to parse: http://127.0.0.1:10809
requests.exceptions.InvalidURL: Failed to parse: http://127.0.0.1:10809
```
错误源自 urllib3 的 `_HOST_PORT_RE.match()` 返回 None。

**根因**：cmd 的 `set` 语法在链式命令里有陷阱：
```bat
set HTTPS_PROXY=http://127.0.0.1:10809 && next_cmd
```
**`&&` 前的空格被算入 value**，实际 `HTTPS_PROXY = "http://127.0.0.1:10809 "`（末尾带空格）。urllib3 的 host:port 正则 `^(host)(?::port)?$` 严格匹配，无法容忍末尾空格 → `LocationParseError`。httpx 容忍这个空格所以 Twitter 子进程没出问题，但 sentence-transformers→transformers→huggingface_hub 走 requests/urllib3 触发了它。

**解决**：所有 set 用 cmd 标准引号语法 `set "VAR=val"`，引号内剥离两端空格：
```bat
set "HTTPS_PROXY=http://127.0.0.1:10809" && set "HTTP_PROXY=http://127.0.0.1:10809" && ...
```

**排查要点**：
- 直接 `python -c "import requests; requests.get(...)"` 测试代理时不会复现，因为是单独 PowerShell session
- 在 cmd 里用 `set FOO=bar && python -c "import os; print(repr(os.environ['FOO']))"` 才能看到尾空格 `'bar '`
- httpx 与 requests/urllib3 对 proxy URL 解析严格度不一致，httpx 容忍空格

**触发条件**：仅 Windows cmd 的 `set X=Y && Z` 语法触发。PowerShell `$env:X="Y"` 不会，因为引号定义边界。

---

## 2026-05-15 | 国外信源在国内需要代理，国内源要白名单

**现象**：Twitter / Anthropic / Meta / HuggingFace / Reddit / HN 直连均 `ConnectTimeout`。

**根因**：被 GFW 拦截。Python 的 httpx/requests 不会自动用系统代理。

**解决**：`start.bat` 设全局 `HTTP_PROXY/HTTPS_PROXY=http://127.0.0.1:10809`（V2Ray），并配 `NO_PROXY` 白名单包含所有国内域名（量子位/36氪/InfoQ/钛媒体等）+ LLM API（api.minimaxi.com）+ 微信（mp.weixin.qq.com）+ 本地回环，避免国内源也绕代理。

**Twitter 单独走 `TWS_PROXY` env**（twscrape 原生支持，account.py:53-59），不依赖 HTTPS_PROXY。

**附带发现**：多个国外 RSS 地址已漂移，需定期复查：
- OpenAI: `/blog/rss.xml` → `/news/rss.xml`（307 重定向但终点更稳）
- Anthropic: 完全取消官方 RSS，改 scrape `/news` 页 + `a[href*="/news/"]` selector
- The Verge: `/{cat}/rss/index.xml` → `/rss/{cat}/index.xml`
- Wired: 标签 `artificial-intelligence` → `ai`
- TLDR: `/ai/rss` → `/api/rss/ai`
- LangChain: blog.langchain.dev 死链 → `changelog.langchain.com/feed.xml`
- Ben's Bites: news.bensbites.com 死链 → `bensbites.com/feed`
- 新智元: xinzhiyuan.com 整个域死链，迁微信公众号采集

---

## 2026-04-27 | 跨信源相似新闻未被语义去重

**现象**：同一事件被不同公众号/媒体报道，标题措辞略有差异，URL 不同。原 0.85 阈值（基于 title+summary 的 cosine）漏判，最终报告里出现两条几乎相同的新闻。

**根因**：
1. 不同信源摘要长度悬殊（量子位 500 字 vs 机器之心 37 字），混入摘要会稀释 cosine。
2. `paraphrase-multilingual-MiniLM-L12-v2` 模型对中文短标题区分度有限，真实重复对仅得 0.76。
3. 单纯降阈值会误删格式相似但内容不同的新闻（如 "FSD V12" vs "FSD V13"）。

**解决**：`backend/deduplicator.py` 改为
- 仅用标题做嵌入，避免摘要长度噪声
- 双阈值判定：sim ≥ 0.85 直接判同；0.70 ≤ sim < 0.85 时要求标题至少共享 2 个区分性 Latin/数字 token（命名实体/型号词）
- 对没有共同英文实体的相似格式新闻（OpenAI vs Anthropic）有保护

**残留问题**：版本号微差的同公司新闻（如 Claude 4.5/4.6）仍可能被误删，因模型本身将其判为 0.98 相似。根治需更换嵌入模型（如 BAAI/bge-m3）。

---

## 2026-03-23 | useCallback 依赖 TDZ 导致白屏

**现象**：前端构建成功，但页面完全空白，无任何渲染。

**原因**：`downloadReport` 使用 `useCallback`，依赖数组中引用了 `signalsData`，但 `signalsData` 用 `const + useMemo` 在后面声明。`const` 变量在声明前处于暂时性死区（Temporal Dead Zone），访问直接抛 `ReferenceError`。

```jsx
// 错误顺序（signalsData 还未声明）
const downloadReport = useCallback(() => { ... }, [current, signalsData])
const signalsData = useMemo(() => { ... }, [current?.signals])
```

**解决**：将 `signalsData` 的 `useMemo` 移到 `downloadReport` 的 `useCallback` 之前。

**教训**：
- React Hooks 的依赖数组在调用时立即求值，`const` 在声明前不可访问
- Vite 构建不会报这类运行时错误，需要检查浏览器 Console
- 构建成功 ≠ 运行正常

---

## 2026-03-17 | 前端修改后页面不更新

**现象**：修改了前端代码，后端重启后页面没有变化。

**原因**：后端直接托管 `frontend/dist/` 静态文件，修改源码后需要重新构建。

**解决**：每次修改前端后执行 `cd frontend && npm run build`，然后重启后端或硬刷新浏览器（Ctrl+Shift+R）。

---

## 2026-03-11 | 需要 JS 渲染的站点抓取为空

**现象**：部分站点（智谱AI、DeepSeek 等）抓取结果为空。

**原因**：这些站点使用 SPA 框架，静态 requests 获取的 HTML 不含实际内容。

**解决**：在 `scraper.py` 的 `_JS_REQUIRED_DOMAINS` 中添加对应域名，系统自动切换为 Playwright 渲染。
