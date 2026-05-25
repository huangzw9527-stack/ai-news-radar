# 开发日志

按日期倒序记录每天的开发工作。

---

## 2026-05-22

### X/Twitter 采集健壮性完善
- `backend/requirements.txt` 补声明 `twscrape==0.17.0`，`beautifulsoup4` 升 `4.12.3 → 4.14.3`（twscrape 要求 `>=4.13.0`）
- 新增 `twscrape_available()` / `TWSCRAPE_MISSING_MSG`：twscrape 缺失时 `collect_all` 与 `/api/twitter/{status,add-account,login,collect}` 统一返回可操作提示，取代原先「注入失败 → 未配置账号」的误导日志
- 代理解析集中进 `collect_all(twitter_cfg, proxy_url=...)`，新增纯函数 `_resolve_proxy`，修复 `/api/twitter/collect` 测试接口漏注入代理的问题
- `start.bat` 启动前探测关键依赖，缺失则自动 `pip install -r backend/requirements.txt`
- 新增 `tests/test_twitter_robustness.py`（12 项）：覆盖 twscrape 缺失降级、代理解析、端点提示

---

## 2026-03-25

### 微信公众号采集器重构为 Playwright 方案
- 参考 [feedgrab](https://github.com/iBigQiang/feedgrab) 项目，去掉 selenium/webdriver-manager/wechatarticles 三个依赖
- 改用 Playwright storage_state 管理登录 session（`data/wechat_session.json`）
- 直接调用微信后台 searchbiz + appmsgpublish API（浏览器内 page.evaluate）
- fakeid 缓存到 `data/wechat_fakeids.json`，避免重复搜索
- Pipeline 中 wechat 源串行采集，共享浏览器实例（start/stop 生命周期）
- 后端 API：`GET /api/wechat/status`、`POST /api/wechat/login`
- 前端配置页：session 状态显示 + 扫码登录按钮

---

## 2026-03-23

### 新增 AIBase 信源
- 在 `sources.yaml` 添加 AIBase基地（`https://www.aibase.com/zh/news`），type: scrape，selector: `a[href*='/news/']`
- 在 `scraper.py` 的 `_JS_REQUIRED_DOMAINS` 添加 `aibase.com`（Nuxt.js 站点，需 Playwright 渲染）

### 新增报告下载功能
- 在 ReportPage 添加「下载」按钮，点击生成独立 HTML 文件
- HTML 自包含所有样式，适配移动端（H5）
- 仅包含当天报告内容（战略建议 + 新闻卡片），不含侧边栏/历史/配置

---

## 2026-03-17

### 批量新增信源
- 新增国内垂直媒体：新智元、AI科技评论（雷锋网）
- 新增海外科技媒体：The Verge AI、Google AI Blog
- 新增开发者社区：Hacker News、Product Hunt
- 新增 AI 周报：Last Week in AI、Import AI、Platformer

---

## 2026-03-11

### 项目初始化
- 完成架构设计文档和实施计划
- 搭建 FastAPI 后端 + React 前端基础框架
- 实现采集、去重、排名、LLM 分析完整 Pipeline
- 实现 WebSocket 实时进度推送
- 配置 32+ AI 相关信源
