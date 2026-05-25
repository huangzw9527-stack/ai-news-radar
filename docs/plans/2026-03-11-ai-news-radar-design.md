# AI一线研究新闻收集系统 — 设计方案

日期：2026-03
项目名：ai-news-radar

---

## 一、目标

从全球10家核心AI机构的指定信源中，自动采集、评分、筛选出最有价值的 **Top 10 AI新闻及领袖言论**，并通过 LLM 挖掘对公司的**业务机会与战略启示**，以 Web 仪表板形式呈现。

---

## 二、整体架构

```
┌─────────────────────────────────────────────────────┐
│                   Web Dashboard                      │
│  [手动触发] [历史报告] [新闻列表] [业务机会] [配置]   │
└──────────────────────┬──────────────────────────────┘
                       │ HTTP API
┌──────────────────────▼──────────────────────────────┐
│              FastAPI 后端服务                         │
│  ┌─────────────┐  ┌──────────┐  ┌────────────────┐  │
│  │  Scheduler  │  │  Router  │  │  LLM Provider  │  │
│  │ (APScheduler│  │ (API端点)│  │(Claude/GPT配置)│  │
│  └─────────────┘  └──────────┘  └────────────────┘  │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│               采集 & 分析 Pipeline                    │
│  ┌──────────┐  ┌──────────┐  ┌────────────────────┐ │
│  │ Collector│→ │  Ranker  │→ │  LLM Analyzer      │ │
│  │RSS+Scrape│  │ 权重评分 │  │ Top10+机会挖掘  │ │
│  └──────────┘  └──────────┘  └────────────────────┘ │
└──────────────────────┬──────────────────────────────┘
                       │
              ┌────────▼────────┐
              │  SQLite 数据库   │
              │ news / reports  │
              └─────────────────┘
```

---

## 三、信源体系

### 权重维度

| 维度 | 权重 | 说明 |
|------|------|------|
| 学术引领力 | 37 | 顶会顶刊、论文、技术突破 |
| 产业转化力 | 32 | API收入、开源生态、政企落地 |
| 资本与生态力 | 12 | 融资、估值、产学研、人才 |
| Agent化转型 | 10 | 企业IT Agent化、组织转型 |
| 前沿战略力 | 9 | AI安全、下一代技术路线 |

### 信源等级

- **一级核心信源**（满分采信）：官方博客、论文库、财报、顶会顶刊、专利局、权威数据平台、中标公告
- **二级辅助信源**（打0.6折）：领导社交媒体（X/LinkedIn/知乎/微博）、权威科技媒体、行业白皮书

### 覆盖机构

OpenAI、DeepMind、Anthropic、Microsoft Research、字节跳动、阿里达摩院、智谱AI、北京智源研究院、DeepSeek、商汤科技

---

## 四、采集模块（Collector）

### 三层采集策略

**层1 — RSS/API（优先）**
- arXiv API → 论文
- Hugging Face RSS → 模型发布
- GitHub API → 开源动态
- 各机构官方博客 RSS
- 国内机构通过 RSSHub 代理

**层2 — 轻量爬虫（RSS覆盖不到时）**
- Playwright → 动态页面（财报、中标公告）
- Requests + BeautifulSoup → 静态页面
- 复用 social-monitor → 微博、知乎、X 二级信源

**层3 — 元数据自动标注**
```python
{
  "source_tier": 1 | 2,
  "institution": "OpenAI",
  "indicator": "academic",
  "weight": 37,
}
```

### 采集限制
- 每个信源最多取最新 **10条**
- 采集后立即进行双层去重

---

## 五、去重策略（双层）

### 第一层：URL 哈希去重
```python
id = md5(url)  # 同一URL不重复入库
```

### 第二层：语义去重
```python
from sentence_transformers import SentenceTransformer
model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
# 支持中英文，模型体积约120MB，本地运行无需API

def semantic_dedup(news_list, threshold=0.85):
    embeddings = model.encode([n.title + n.summary for n in news_list])
    # 两两余弦相似度 > threshold 视为同一事件
    # 保留：评分最高 > 一级信源 > 发布时间最早
```

`threshold` 可在 `config.yaml` 中调整（默认0.85）。

---

## 六、评分模块（Ranker）

```python
WEIGHTS = {
    "academic":  37,
    "industry":  32,
    "capital":   12,
    "agent":     10,
    "frontier":   9,
}

def score(news):
    base      = WEIGHTS[news.indicator]
    tier_mult = 1.0 if news.source_tier == 1 else 0.6
    recency   = decay(news.published_at)   # 48h内1.0，逐步衰减
    return base * tier_mult * recency
```

取分数 **Top 30** 进入 LLM 分析（控制 token 成本）。

---

## 七、LLM 分析模块（Analyzer）

### Step 1：精选 Top 10
```
输入：Top30 新闻标题 + 摘要 + 评分
任务：选出最有价值的10条，输出编号 + 理由
```

### Step 2：公司业务机会挖掘
```
输入：Top10 全文 + 公司背景
任务：
  1. 每条新闻 → 对公司的业务机会/战略启示（1-2句）
  2. 全局综合 → 本期最重要的3个战略信号
输出：结构化 JSON
```

### LLM Provider 配置
```yaml
llm:
  provider: claude        # claude | openai | ollama
  model: claude-sonnet-4-6
  api_key: ${ANTHROPIC_API_KEY}
```

---

## 八、Web 仪表板

技术栈：React + TailwindCSS + FastAPI

### 页面结构
```
├── 首页/报告页
│   ├── Top10 新闻卡片（含原文链接跳转）
│   ├── 业务机会面板
│   └── 3大战略信号高亮区
│
├── 历史报告页
│   └── 按日期列表，点击查看历史完整报告
│
├── 采集控制页
│   ├── [立即采集分析] 手动触发按钮
│   ├── 采集进度实时显示（WebSocket）
│   └── 定时任务配置（频率、时间）
│
└── 配置页
    ├── LLM Provider 切换
    ├── 信源开关（单独禁用某个信源）
    └── 每源抓取数量上限 / 语义去重阈值
```

### 新闻卡片字段
- 标题（可点击跳转原文链接）
- 来源机构 + 信源等级标签
- 维度标签（学术/产业/资本/Agent/前沿）
- 发布时间 + 评分
- 摘要
- 公司业务机会（1-2句）

---

## 九、数据库设计（SQLite）

```sql
CREATE TABLE news (
    id           TEXT PRIMARY KEY,   -- URL MD5哈希
    url          TEXT UNIQUE,
    title        TEXT,
    summary      TEXT,
    full_text    TEXT,
    source_name  TEXT,
    source_tier  INTEGER,
    institution  TEXT,
    indicator    TEXT,
    score        REAL,
    published_at DATETIME,
    collected_at DATETIME
);

CREATE TABLE reports (
    id            TEXT PRIMARY KEY,
    created_at    DATETIME,
    trigger       TEXT,              -- "scheduled" | "manual"
    top10_ids     TEXT,              -- JSON数组
    opportunities TEXT,             -- JSON：每条新闻的公司机会
    signals       TEXT,             -- JSON：3大战略信号
    llm_provider  TEXT,
    llm_model     TEXT
);
```

---

## 十、项目目录结构

```
ai-news-radar/
├── backend/
│   ├── main.py              # FastAPI入口
│   ├── scheduler.py         # APScheduler定时任务
│   ├── collector/
│   │   ├── rss.py           # RSS/API采集
│   │   ├── scraper.py       # Playwright爬虫
│   │   └── sources.yaml     # 信源配置表
│   ├── ranker.py            # 权重评分
│   ├── analyzer.py          # LLM分析
│   ├── deduplicator.py      # 语义去重
│   ├── llm/
│   │   ├── base.py          # Provider抽象基类
│   │   ├── claude.py
│   │   ├── openai.py
│   │   └── ollama.py
│   └── db.py                # SQLite操作
├── frontend/
│   ├── src/
│   │   ├── pages/           # 首页/历史/控制/配置
│   │   └── components/      # 新闻卡片等组件
│   └── package.json
├── config.yaml              # 全局配置
├── docs/
│   └── plans/
│       └── 2026-03-11-ai-news-radar-design.md
└── requirements.txt
```

---

## 十一、技术选型汇总

| 模块 | 技术 |
|------|------|
| 后端框架 | Python + FastAPI |
| RSS采集 | feedparser |
| 网页爬虫 | Playwright + BeautifulSoup |
| 语义去重 | sentence-transformers（本地） |
| 权重评分 | 自定义算法 |
| LLM分析 | Claude / OpenAI / Ollama（可配置） |
| 前端 | React + TailwindCSS |
| 数据库 | SQLite |
| 定时任务 | APScheduler |
| 部署 | 本地 Windows，后续可上云 |
