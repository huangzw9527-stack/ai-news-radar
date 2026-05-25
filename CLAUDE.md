# AI News Radar

AI 新闻自动采集、分析与报告系统，面向公司的 AI 动态监测需求。

## 技术栈

| 层 | 技术 |
|---|------|
| 后端 | Python + FastAPI + Uvicorn |
| 前端 | React 19 + Tailwind CSS 4 + Vite 7 |
| 数据库 | SQLite |
| 采集 | feedparser (RSS) + Playwright + BeautifulSoup (网页抓取) |
| 去重 | sentence-transformers (paraphrase-multilingual-MiniLM-L12-v2) |
| LLM | 可切换 Claude / OpenAI / Ollama，当前使用 MiniMax-M2.5 |
| 调度 | APScheduler，默认每天 8:00 |

## 项目结构

```
ai-news-radar/
├── backend/
│   ├── main.py              # FastAPI 入口，API 路由 + 静态文件托管
│   ├── pipeline.py           # 主流程：采集 → 去重 → 排名 → LLM 分析 → 报告
│   ├── scheduler.py          # APScheduler 定时任务
│   ├── analyzer.py           # LLM 分析（评分 + 摘要 + 战略建议）
│   ├── scorer.py             # 时效拦截 + 话题语义过滤 + LLM 评分排名（取 Top 30）
│   ├── deduplicator.py       # URL + 语义去重
│   ├── config_utils.py       # 配置纯函数工具（如剔除空白话题）
│   ├── db.py                 # SQLite 操作（news / reports 表）
│   ├── date_filters.py       # 日期过滤
│   ├── collector/
│   │   ├── rss.py            # RSS 采集器
│   │   ├── scraper.py        # 网页抓取器（自动判断静态/JS 渲染）
│   │   ├── enricher.py       # 内容增强
│   │   ├── filters.py        # AI 相关性关键词过滤（从 config.yaml 动态加载）
│   │   ├── wechat.py         # 微信公众号采集器（Playwright + 微信后台 API）
│   │   └── wechat_auth.py    # 微信公众号凭证管理（Playwright storage_state）
│   └── llm/                  # LLM 提供者抽象层
│       ├── base.py / factory.py
│       ├── claude.py / openai_provider.py / ollama.py
├── frontend/
│   ├── src/
│   │   ├── App.jsx           # 路由 + 顶部导航
│   │   ├── pages/
│   │   │   ├── ReportPage.jsx  # 报告展示（侧边栏 + 战略建议 + 新闻卡片）
│   │   │   └── ConfigPage.jsx  # 配置页
│   │   └── components/
│   │       └── NewsCard.jsx    # 新闻卡片组件
│   └── dist/                 # 构建产物（后端直接托管）
├── config.yaml               # 全局配置（话题 / 关键词 / 类别 / 信源 / LLM / 采集 / 调度）
├── docs/plans/               # 设计文档
└── start.bat                 # Windows 启动脚本
```

## 关键流程

1. **采集**：并行读取 sources.yaml 中所有信源（RSS / 网页），线程池执行，120s 超时；微信公众号源串行采集（共享 Playwright 浏览器实例）
2. **去重**：URL 哈希 + 语义相似度 (cosine > 0.85)
3. **评分排名**（`scorer.py`）：时效拦截（72h）→ 配置话题时按 embedding 语义过滤 → LLM 评分（内容质量 + 话题关联度）→ 综合排序，取 Top 30
4. **LLM 分析**：对 Top 30 做业务关联度评分，选 Top 10 生成摘要 + 战略建议
5. **报告**：存入 SQLite，前端 WebSocket 实时推送进度

## 开发约定

- **前端构建**：修改前端代码后需 `cd frontend && npm run build`，后端托管 `dist/` 静态文件
- **信源配置**：通过前端配置页或编辑 `config.yaml` 的 `sources.websites` / `sources.wechat`，type 为 `scrape` 的需要指定 CSS `selector`
- **JS 渲染站点**：在 `backend/collector/scraper.py` 的 `_JS_REQUIRED_DOMAINS` 集合中添加域名
- **LLM 配置**：通过 `config.yaml` 或前端配置页切换，支持 OpenAI 兼容接口
- **微信公众号采集**：在 `config.yaml` 的 `sources.wechat` 中配置 `nickname` 字段；首次使用需通过前端配置页「扫码登录」或调用 `POST /api/wechat/login`；基于 Playwright + 微信后台 API（searchbiz/appmsgpublish），session 缓存于 `data/wechat_session.json`，fakeid 缓存于 `data/wechat_fakeids.json`
- **用户语言**：界面和输出均为中文

## 相关文档

- 架构设计：`docs/plans/2026-03-11-ai-news-radar-design.md`
- 实施计划：`docs/plans/2026-03-11-implementation-plan.md`
- 开发日志：`docs/devlog.md`
- 踩坑记录：`docs/pitfalls.md`
