# Scoring / Sources / Briefing Redesign Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 重构评分模型（信源分+内容分+热度分×时间衰减）、替换全量30个信源、将 Top10 卡片报告改为三段式每日简报。

**Architecture:** 变更贯穿9个文件：config.yaml（信源/分类）→ filters.py（内置关键词）→ deduplicator.py（report_count）→ scorer.py（新公式）→ analyzer.py（新分类+三段简报）→ db.py（briefing列）→ pipeline.py（存储新格式）→ main.py（API响应）→ 前端（ReportPage+App）。

**Tech Stack:** Python/FastAPI 后端，React 19/Tailwind CSS 4 前端，SQLite via db.py。

---

### Task 1: config.yaml — 替换信源、更新分类、移除废弃字段

**Files:**
- Modify: `config.yaml`

**Step 1: 重写 config.yaml**

保留字段：`llm`, `collection`, `dedup`, `scheduler`, `database`, `topics`
移除字段：`keywords`, `strategic_advice`
更新 `categories` 为新 6 个；全量替换 `sources`。

将 config.yaml 改为以下内容（llm/collection/dedup/scheduler/database/topics 保持原值不变，只更新下列部分）：

```yaml
categories:
- 模型发布
- 产品动态
- 产业商业
- 研究论文
- 实操技巧
- 观点深度

sources:
  websites:
  # ── S 级 (tier: 1) ──────────────────────────────
  - name: OpenAI Blog
    institution: OpenAI
    tier: 1
    indicator: academic
    type: rss
    url: https://openai.com/blog/rss.xml
  - name: Anthropic News
    institution: Anthropic
    tier: 1
    indicator: academic
    type: rss
    url: https://www.anthropic.com/rss.xml
  - name: Google DeepMind Blog
    institution: DeepMind
    tier: 1
    indicator: academic
    type: rss
    url: https://deepmind.google/blog/rss.xml
  - name: Meta AI Blog
    institution: Meta
    tier: 1
    indicator: academic
    type: rss
    url: https://engineering.fb.com/feed/
  - name: Google AI Blog
    institution: Google
    tier: 1
    indicator: academic
    type: rss
    url: https://blog.google/technology/ai/rss/
  - name: arXiv cs.AI
    institution: arXiv
    tier: 1
    indicator: academic
    type: rss
    url: https://rss.arxiv.org/rss/cs.AI
  - name: arXiv cs.CL
    institution: arXiv
    tier: 1
    indicator: academic
    type: rss
    url: https://rss.arxiv.org/rss/cs.CL
  - name: Hugging Face Blog
    institution: Hugging Face
    tier: 1
    indicator: academic
    type: rss
    url: https://huggingface.co/blog/feed.xml
  - name: 智谱AI官方
    institution: 智谱AI
    tier: 1
    indicator: academic
    type: scrape
    url: https://www.zhipuai.cn/zh/research
    selector: article, .news-item, .post-item
  - name: DeepSeek官网
    institution: DeepSeek
    tier: 1
    indicator: academic
    type: scrape
    url: https://www.deepseek.com/
    selector: article
  # ── A 级 (tier: 2) ──────────────────────────────
  - name: TechCrunch AI
    institution: TechCrunch
    tier: 2
    indicator: industry
    type: rss
    url: https://techcrunch.com/category/artificial-intelligence/feed/
  - name: MIT Technology Review
    institution: MIT Tech Review
    tier: 2
    indicator: frontier
    type: rss
    url: https://www.technologyreview.com/feed/
  - name: The Verge AI
    institution: The Verge
    tier: 2
    indicator: frontier
    type: rss
    url: https://www.theverge.com/ai-artificial-intelligence/rss/index.xml
  - name: Wired AI
    institution: Wired
    tier: 2
    indicator: frontier
    type: rss
    url: https://www.wired.com/feed/tag/artificial-intelligence/latest/rss
  - name: 量子位
    institution: 量子位
    tier: 2
    indicator: industry
    type: rss
    url: https://www.qbitai.com/feed
  - name: 机器之心
    institution: 机器之心
    tier: 2
    indicator: industry
    type: rss
    url: https://news.google.com/rss/search?q=site:jiqizhixin.com+AI&hl=zh-CN&gl=CN&ceid=CN:zh-Hans
  - name: 晚点LatePost
    institution: 晚点LatePost
    tier: 2
    indicator: industry
    type: rss
    url: https://news.google.com/rss/search?q=site:latepost.com+AI&hl=zh-CN&gl=CN&ceid=CN:zh-Hans
  - name: The Batch DeepLearning.AI
    institution: DeepLearning.AI
    tier: 2
    indicator: frontier
    type: scrape
    url: https://www.deeplearning.ai/the-batch/
    selector: article, .post-card, .batch-item
  - name: InfoQ
    institution: InfoQ
    tier: 2
    indicator: industry
    type: rss
    url: https://www.infoq.cn/feed
  - name: 36氪AI频道
    institution: 36氪
    tier: 2
    indicator: industry
    type: rss
    url: https://36kr.com/feed
  # ── B 级 (tier: 3) ──────────────────────────────
  - name: Hacker News
    institution: Y Combinator
    tier: 3
    indicator: frontier
    type: rss
    url: https://hnrss.org/frontpage
  - name: Reddit MachineLearning
    institution: Reddit
    tier: 3
    indicator: frontier
    type: rss
    url: https://www.reddit.com/r/MachineLearning/.rss
  - name: Reddit LocalLLaMA
    institution: Reddit
    tier: 3
    indicator: frontier
    type: rss
    url: https://www.reddit.com/r/LocalLLaMA/.rss
  - name: Ben's Bites
    institution: Ben's Bites
    tier: 3
    indicator: frontier
    type: rss
    url: https://news.bensbites.com/feed
  - name: TLDR AI
    institution: TLDR
    tier: 3
    indicator: frontier
    type: rss
    url: https://tldr.tech/ai/rss
  - name: Last Week in AI
    institution: Last Week in AI
    tier: 3
    indicator: frontier
    type: rss
    url: https://lastweekin.ai/feed
  - name: LangChain Blog
    institution: LangChain
    tier: 3
    indicator: agent
    type: rss
    url: https://blog.langchain.dev/rss/
  - name: 新智元
    institution: 新智元
    tier: 3
    indicator: industry
    type: rss
    url: https://www.xinzhiyuan.com/feed
  - name: 钛媒体
    institution: 钛媒体
    tier: 3
    indicator: industry
    type: rss
    url: https://www.tmtpost.com/rss.xml
  - name: AIBase
    institution: AIBase
    tier: 3
    indicator: industry
    type: scrape
    url: https://www.aibase.com/zh/news
    selector: a[href*='/news/']
  wechat:
  - name: 量子位（公众号）
    institution: 量子位
    nickname: 量子位
    tier: 2
    indicator: industry
  - name: 机器之心（公众号）
    institution: 机器之心
    nickname: 机器之心
    tier: 2
    indicator: industry
```

**Step 2: 验证 YAML 合法**

```powershell
python -c "import yaml; cfg=yaml.safe_load(open('config.yaml',encoding='utf-8')); print(len(cfg['sources']['websites']),'个信源')"
```
期望输出：`30 个信源`

**Step 3: Commit**

```powershell
git add config.yaml
git commit -m "feat(config): replace all sources with 30-source tier list, update categories"
```

---

### Task 2: filters.py — 内置基础关键词，移除 config 依赖

**Files:**
- Modify: `backend/collector/filters.py`

**Step 1: 用内置列表替换 get_all_keywords()**

将文件顶部的注释更新，添加 `_BASE_KEYWORDS` 常量，修改 `get_all_keywords()`：

```python
"""采集阶段的 AI 相关性预筛。

关键词从内置列表 + topics[].keywords 动态合并，不再依赖 config.keywords。
"""

import re
from typing import List

_cached_re = None
_cached_keywords = None

_BASE_KEYWORDS = [
    "AI", "人工智能", "artificial intelligence",
    "机器学习", "machine learning", "深度学习", "deep learning",
    "大模型", "大语言模型", "LLM", "语言模型",
    "GPT", "ChatGPT", "Claude", "Gemini", "Llama",
    "DeepSeek", "Qwen", "通义", "文心", "Kimi", "MiniMax",
    "开源模型", "基座模型", "foundation model",
    "智能体", "Agent", "RAG", "Copilot",
    "AIGC", "生成式", "多模态", "multimodal",
    "GPU", "TPU", "芯片", "算力", "推理", "微调", "fine-tun",
    "AI治理", "AI安全", "AI监管", "AI伦理",
    "融资", "估值", "并购",
]


def _build_regex(keywords: List[str]) -> re.Pattern:
    patterns = []
    for kw in keywords:
        kw = kw.strip()
        if not kw:
            continue
        if re.match(r'^[a-zA-Z]+$', kw) and len(kw) <= 4:
            patterns.append(rf'\b{re.escape(kw)}\b')
        else:
            patterns.append(re.escape(kw))
    if not patterns:
        return re.compile(r'(?!)')
    return re.compile("|".join(patterns), re.IGNORECASE)


def get_all_keywords(config: dict) -> List[str]:
    """从内置列表 + topics 关键词合并（去重保序）。"""
    topic_kws = []
    for topic in config.get("topics", []):
        topic_kws.extend(topic.get("keywords", []))
    seen = set()
    result = []
    for kw in _BASE_KEYWORDS + topic_kws:
        kw_lower = kw.strip().lower()
        if kw_lower and kw_lower not in seen:
            seen.add(kw_lower)
            result.append(kw.strip())
    return result


def is_ai_related(title: str, summary: str = "", keywords: List[str] = None) -> bool:
    global _cached_re, _cached_keywords
    if keywords is not None:
        if keywords != _cached_keywords:
            _cached_re = _build_regex(keywords)
            _cached_keywords = keywords
        regex = _cached_re
    elif _cached_re is not None:
        regex = _cached_re
    else:
        return True
    text = f"{title} {summary}"
    return bool(regex.search(text))
```

**Step 2: Commit**

```powershell
git add backend/collector/filters.py
git commit -m "refactor(filters): inline base keywords, remove config.keywords dependency"
```

---

### Task 3: deduplicator.py — 添加 report_count 字段

**Files:**
- Modify: `backend/deduplicator.py`

**Step 1: 在 deduplicate() 里追踪合并计数**

在 `kept_indices = []` 和 `removed = set()` 之后添加：
```python
duplicate_counts: Dict[int, int] = {}
```

在内层循环 `removed.add(other_idx)` 之后添加：
```python
duplicate_counts[orig_idx] = duplicate_counts.get(orig_idx, 0) + 1
```

返回前将 `report_count` 写入每个保留项：
```python
result = [unique[i] for i in sorted(kept_indices)]
for i in sorted(kept_indices):
    unique[i]["report_count"] = duplicate_counts.get(i, 0) + 1
return result
```

同时处理 `len(unique) <= 1` 的 early return：
```python
if len(unique) <= 1:
    for n in unique:
        n["report_count"] = 1
    return unique
```

完整修改后的 `deduplicate()` 方法签名和逻辑保持不变，只增加 report_count 追踪。

**Step 2: Commit**

```powershell
git add backend/deduplicator.py
git commit -m "feat(dedup): add report_count field to track same-event coverage count"
```

---

### Task 4: scorer.py — 新评分公式

**Files:**
- Modify: `backend/scorer.py`

**Step 1: 替换常量和衰减函数**

删除旧常量：`INCREMENT_SCORES`, `_TIER_FACTORS`, `_DEFAULT_TIER_FACTOR`

添加新常量：
```python
_SOURCE_SCORES: Dict[int, float] = {1: 27.0, 2: 20.0, 3: 10.0}
_DEFAULT_SOURCE_SCORE = 15.0
_HALF_LIFE_HOURS: Dict[str, float] = {
    "模型发布": 48.0, "产品动态": 48.0,
    "产业商业": 168.0, "观点深度": 168.0,
    "研究论文": 336.0, "实操技巧": 336.0,
}
_DEFAULT_HALF_LIFE = 72.0
```

将 `_freshness()` 函数替换为 `_time_decay()`：
```python
def _time_decay(published_at, main_category: str = "") -> float:
    hours = _hours_since(published_at)
    if hours == float("inf"):
        return 0.1
    half_life = _HALF_LIFE_HOURS.get(main_category, _DEFAULT_HALF_LIFE)
    return math.exp(-math.log(2) * hours / half_life)
```

**Step 2: 更新 score_and_rank() 的 Step 5 公式**

将原来的：
```python
item["score"] = (rel * 0.5 + inc * 0.5) * fresh * _tier_factor(item.get("source_tier"))
```
替换为：
```python
try:
    tier_int = int(item.get("source_tier") or 0)
except (TypeError, ValueError):
    tier_int = 0
source_score = _SOURCE_SCORES.get(tier_int, _DEFAULT_SOURCE_SCORE)
content_score = (
    float(item.get("llm_substantiality", 10)) +
    float(item.get("llm_density", 10)) +
    float(item.get("llm_originality", 10))
)
hotness = min(25.0, float(item.get("report_count", 1)) * 5.0)
decay = _time_decay(
    item.get("published_at") or item.get("collected_at"),
    item.get("main_category", ""),
)
item["score"] = (source_score + content_score + hotness) * decay
```

**Step 3: 更新 _score_batch() 的 LLM prompt**

在 example dict 里，每个条目添加 `content` 和 `main_category` 字段：
```python
example = {
    str(i + 1): {
        "relevance": 80,
        "content": {"substantiality": 12, "density": 10, "originality": 13},
        "main_category": "模型发布",
    }
    for i in range(len(batch))
}
```

在 prompt 文本里追加两条新要求（紧接在业务关联性说明后）：
```
3. content（内容质量，各项 0-15）：
   - substantiality（实质性）：硬事件（发布/融资/开源/数据/benchmark）满分15；纯观点/预测≤8
   - density（信息密度）：含具体数字/benchmark/产品名/可验证信息越多越高
   - originality（原创度）：首发原创15；编译/翻译12；纯转载9
4. main_category：从[模型发布, 产品动态, 产业商业, 研究论文, 实操技巧, 观点深度]选一个
```

在 `_score_batch()` 解析结果处添加提取：
```python
content = s.get("content", {})
if isinstance(content, dict):
    item["llm_substantiality"] = int(float(content.get("substantiality", 10)))
    item["llm_density"] = int(float(content.get("density", 10)))
    item["llm_originality"] = int(float(content.get("originality", 10)))
else:
    item["llm_substantiality"] = 10
    item["llm_density"] = 10
    item["llm_originality"] = 10
item["main_category"] = s.get("main_category", "")
```

**Step 4: Commit**

```powershell
git add backend/scorer.py
git commit -m "feat(scorer): new scoring formula — source+content+hotness x time_decay"
```

---

### Task 5: analyzer.py — 新分类体系 + aux_tags + 三段式简报

**Files:**
- Modify: `backend/analyzer.py`

**Step 1: 更新 __init__，移除 strategic_advice_modules**

```python
def __init__(
    self,
    llm: BaseLLMProvider,
    topics: List[Dict] = None,
    categories: List[str] = None,
):
    self.llm = llm
    self.topics = topics or []
    self.categories = categories or []
    self._topics_text = self._build_topics_text()
    self._categories_text = "、".join(self.categories) if self.categories else "模型发布、产品动态、产业商业、研究论文、实操技巧、观点深度"
```

**Step 2: 更新 _analyze_batch() 的输出字段**

将 prompt 中的11个字段改为以下8个：
- `title`: 中文标题（已是中文则不变）
- `summary`: 约200字通俗摘要
- `brief`: 60字以内的极简摘要，用于列表展示
- `why_matters`: 一句话说清楚为什么值得关注（面向非技术决策者）
- `main_category`: 从 `{categories_json}` 中选1个最匹配的
- `aux_tags`: 3个以内辅助标签（自由发挥，不限候选词，可以是厂商名/模态/技术方向等）
- `concept`: 核心概念，60字以内
- `principle`: 技术原理或运行机制，80字以内

移除字段：`keywords`, `categories`, `value`, `opportunity`, `impact`, `action`, `practice`

更新 example_json 和 prompt 文本、`_extract()` 函数对应字段。

**Step 3: 更新 _extract() 函数**

```python
def _extract(k_str, v):
    if v.get("title"): all_titles[k_str] = v["title"]
    if v.get("summary"): all_summaries[k_str] = v["summary"]
    if v.get("brief"): all_briefs[k_str] = v["brief"]
    if v.get("why_matters"): all_why_matters[k_str] = v["why_matters"]
    if v.get("main_category"): all_main_categories[k_str] = v["main_category"]
    if v.get("aux_tags"): all_aux_tags[k_str] = v["aux_tags"]
    if v.get("concept"): all_concepts[k_str] = v["concept"]
    if v.get("principle"): all_principles[k_str] = v["principle"]
```

更新 `_analyze_news_items()` 返回值和变量名对应。

**Step 4: 实现 _generate_briefing()**

```python
_CAT_LIMITS = {
    "模型发布": 3, "产品动态": 3,
    "产业商业": 2, "研究论文": 2,
    "实操技巧": 2, "观点深度": 2,
}

def _generate_briefing(
    self,
    news_list: List[Dict],
    summaries: Dict,
    briefs: Dict,
    why_matters: Dict,
    main_categories: Dict,
) -> Dict:
    # 头条要闻：前3条
    headlines = []
    for i, item in enumerate(news_list[:3]):
        k = str(i + 1)
        headlines.append({
            "title": item.get("title_cn") or item["title"],
            "url": item.get("url", ""),
            "source_name": item.get("source_name", ""),
            "published_at": item.get("published_at", ""),
            "summary": summaries.get(k, ""),
            "why_matters": why_matters.get(k, ""),
            "main_category": main_categories.get(k, ""),
        })

    # 分类精选：第4条起，按类别限额分配
    categorized = []
    cat_counts: Dict[str, int] = {}
    offset = len(headlines)
    for i, item in enumerate(news_list[offset:offset + 15], offset + 1):
        k = str(i)
        cat = main_categories.get(k, "")
        limit = _CAT_LIMITS.get(cat, 2)
        if cat_counts.get(cat, 0) >= limit:
            continue
        categorized.append({
            "title": item.get("title_cn") or item["title"],
            "url": item.get("url", ""),
            "source_name": item.get("source_name", ""),
            "published_at": item.get("published_at", ""),
            "brief": briefs.get(k, summaries.get(k, "")[:80]),
            "main_category": cat,
        })
        cat_counts[cat] = cat_counts.get(cat, 0) + 1
        if len(categorized) >= 12:
            break

    # 一句话扫描：剩余条目最多5条
    used_count = len(headlines) + len(categorized)
    scan = []
    for item in news_list[used_count:used_count + 5]:
        scan.append({
            "title": item.get("title_cn") or item["title"],
            "url": item.get("url", ""),
            "source_name": item.get("source_name", ""),
        })

    return {"headlines": headlines, "categorized": categorized, "scan": scan}
```

**Step 5: 更新 analyze() 返回值**

```python
def analyze(self, news_list: List[Dict]) -> Dict[str, Any]:
    if not news_list:
        return {"top10": [], "briefing": {"headlines": [], "categorized": [], "scan": []}}

    top10 = news_list[:TOP_N]

    (titles, summaries, briefs, why_matters, main_categories,
     aux_tags, concepts, principles) = self._analyze_news_items(top10)

    for i, item in enumerate(top10):
        cn_title = titles.get(str(i + 1), "")
        if cn_title:
            item["title_cn"] = cn_title

    briefing = self._generate_briefing(top10, summaries, briefs, why_matters, main_categories)

    return {
        "top10": top10,
        "briefing": briefing,
        "summaries": summaries,
        "main_categories": main_categories,
        "aux_tags": aux_tags,
        "concepts": concepts,
        "principles": principles,
    }
```

**Step 6: Commit**

```powershell
git add backend/analyzer.py
git commit -m "feat(analyzer): new categories, aux_tags, three-tier briefing output"
```

---

### Task 6: db.py + pipeline.py — 保存 briefing 字段

**Files:**
- Modify: `backend/db.py`
- Modify: `backend/pipeline.py`

**Step 1: 在 db.py 的 _migrate() 中添加 briefing 列迁移**

在 `_migrate()` 的 existing 判断循环中，将 `"briefing"` 加入迁移列表：
```python
for col in ["summaries", "keywords", "value_insights", "titles_cn", "categories",
            "impacts", "actions", "concepts", "principles", "practices", "briefing",
            "main_categories", "aux_tags"]:
    if col not in existing:
        conn.execute(f"ALTER TABLE reports ADD COLUMN {col} TEXT")
```

同时在 `CREATE TABLE IF NOT EXISTS reports` 语句中添加 `briefing TEXT` 列（新库初始化用）。

**Step 2: 更新 pipeline.py 里 report dict**

将现有 report dict 替换为：
```python
report = {
    "id": report_id,
    "created_at": datetime.now(timezone.utc).isoformat(),
    "trigger": trigger,
    "top10_ids": json.dumps([n["id"] for n in analysis["top10"]]),
    "briefing": json.dumps(analysis.get("briefing", {}), ensure_ascii=False),
    "summaries": json.dumps(analysis.get("summaries", {}), ensure_ascii=False),
    "main_categories": json.dumps(analysis.get("main_categories", {}), ensure_ascii=False),
    "aux_tags": json.dumps(analysis.get("aux_tags", {}), ensure_ascii=False),
    "titles_cn": json.dumps(
        {str(i+1): n.get("title_cn", "") for i, n in enumerate(analysis["top10"])},
        ensure_ascii=False,
    ),
    "concepts": json.dumps(analysis.get("concepts", {}), ensure_ascii=False),
    "principles": json.dumps(analysis.get("principles", {}), ensure_ascii=False),
    "llm_provider": self.config["llm"]["provider"],
    "llm_model": self.config["llm"]["model"],
}
```

同时移除 `Analyzer` 初始化时 `strategic_advice_modules` 参数：
```python
self.analyzer = Analyzer(
    llm=llm,
    topics=config.get("topics", []),
    categories=config.get("categories", []),
)
```

**Step 3: Commit**

```powershell
git add backend/db.py backend/pipeline.py
git commit -m "feat(pipeline): save briefing to reports table, remove legacy signal fields"
```

---

### Task 7: main.py — 更新 API 响应格式

**Files:**
- Modify: `backend/main.py`

**Step 1: 更新 GET /api/reports/{id} 端点**

将现有的复杂字段重组逻辑替换为：
```python
@app.get("/api/reports/{report_id}")
def get_report(report_id: str):
    report = db.get_report_by_id(report_id)
    if not report:
        return JSONResponse({"error": "Report not found"}, status_code=404)

    raw_briefing = report.get("briefing") or "{}"
    if isinstance(raw_briefing, str):
        briefing = json.loads(raw_briefing)
    else:
        briefing = raw_briefing

    return {
        "id": report["id"],
        "created_at": report["created_at"],
        "trigger": report["trigger"],
        "llm_provider": report.get("llm_provider", ""),
        "llm_model": report.get("llm_model", ""),
        "briefing": briefing,
    }
```

**Step 2: 更新 /api/analyze 端点**

将 `run_analyze()` 函数里的 `Ranker` 引用改为 `Scorer`：
```python
from backend.scorer import Scorer
# ...
scorer = Scorer(llm=create_llm_provider(cfg["llm"]), topics=cfg.get("topics", []), db=db)
top_items = scorer.score_and_rank(recent_news, top_n=10)
score_map = {n["id"]: n["score"] for n in top_items}
db.update_scores(score_map)
```

同时更新 analyzer 初始化（移除 strategic_advice_modules）和 report 保存（同 Task 6 格式）。

**Step 3: 移除 _normalize_signals() 函数**（不再使用）

**Step 4: 更新 list endpoint 轮询兼容**

`GET /api/reports` 返回的列表里 `briefing` 是字符串。前端轮询时检查 `briefing` 是否有内容，需要更新 App.jsx（Task 8 处理）。

**Step 5: Commit**

```powershell
git add backend/main.py
git commit -m "feat(api): update report response to briefing format, use Scorer in analyze"
```

---

### Task 8: ReportPage.jsx — 三段式简报布局

**Files:**
- Modify: `frontend/src/pages/ReportPage.jsx`

**Step 1: 用三段式布局完整替换现有文件**

```jsx
import { useMemo } from 'react'

function SectionHeader({ title, count }) {
  return (
    <div className="flex items-end justify-between border-b border-[var(--color-outline-variant)]/60 pb-2 mb-4">
      <h2 className="font-display text-[18px] font-semibold text-[var(--color-on-surface)]">{title}</h2>
      <span className="text-xs text-[var(--color-outline)]">{count} 条</span>
    </div>
  )
}

function HeadlineCard({ item, rank }) {
  return (
    <div className="bg-[var(--color-surface-low)] border border-[var(--color-outline-variant)]/40 rounded-lg p-5">
      <div className="flex items-center gap-2 mb-3">
        <span className="w-6 h-6 bg-[var(--color-primary)] text-white text-xs font-bold rounded flex items-center justify-center shrink-0">
          {rank}
        </span>
        {item.main_category && (
          <span className="text-xs px-2 py-0.5 bg-[var(--color-primary-soft)] text-[var(--color-primary)] rounded-full font-medium">
            {item.main_category}
          </span>
        )}
      </div>
      <a
        href={item.url} target="_blank" rel="noopener noreferrer"
        className="font-semibold text-[15px] text-[var(--color-on-surface)] hover:text-[var(--color-primary)] leading-snug block mb-2"
      >
        {item.title}
      </a>
      {item.summary && (
        <p className="text-sm text-[var(--color-on-surface-variant)] leading-relaxed mb-3 bg-[var(--color-background)] rounded px-3 py-2">
          {item.summary}
        </p>
      )}
      {item.why_matters && (
        <div className="flex items-start gap-2 bg-[var(--color-primary-soft)]/30 rounded px-3 py-2">
          <span className="material-symbols-outlined text-[var(--color-primary)] shrink-0 mt-0.5" style={{ fontSize: 14 }}>
            lightbulb
          </span>
          <p className="text-xs text-[var(--color-primary)] leading-relaxed">{item.why_matters}</p>
        </div>
      )}
      <p className="text-xs text-[var(--color-outline)] mt-2">
        {item.source_name}{item.published_at && ` · ${item.published_at.slice(0, 10)}`}
      </p>
    </div>
  )
}

function CategorizedItem({ item }) {
  return (
    <div className="border-l-2 border-[var(--color-outline-variant)]/60 pl-3 py-1.5">
      <a
        href={item.url} target="_blank" rel="noopener noreferrer"
        className="text-sm font-medium text-[var(--color-on-surface)] hover:text-[var(--color-primary)] block leading-snug mb-0.5"
      >
        {item.title}
      </a>
      {item.brief && (
        <p className="text-xs text-[var(--color-on-surface-variant)] leading-relaxed">{item.brief}</p>
      )}
      <p className="text-xs text-[var(--color-outline)]">
        {item.source_name}{item.published_at && ` · ${item.published_at.slice(0, 10)}`}
      </p>
    </div>
  )
}

function ScanItem({ item }) {
  return (
    <div className="flex items-center gap-2 py-1">
      <span className="w-1.5 h-1.5 rounded-full bg-[var(--color-outline)] shrink-0" />
      <a
        href={item.url} target="_blank" rel="noopener noreferrer"
        className="text-sm text-[var(--color-on-surface-variant)] hover:text-[var(--color-primary)] flex-1 min-w-0 truncate"
      >
        {item.title}
      </a>
      <span className="text-xs text-[var(--color-outline)] shrink-0">{item.source_name}</span>
    </div>
  )
}

export function ReportPage({ current, collecting, progress, loading, generatingId }) {
  const briefing = current?.briefing || {}
  const headlines = briefing.headlines || []
  const categorized = briefing.categorized || []
  const scan = briefing.scan || []
  const hasBriefing = headlines.length > 0 || categorized.length > 0
  const isGenerating = current?.id === generatingId

  const grouped = useMemo(() => {
    const map = {}
    for (const item of categorized) {
      const cat = item.main_category || '其他'
      if (!map[cat]) map[cat] = []
      map[cat].push(item)
    }
    return map
  }, [categorized])

  return (
    <main className="flex-1 overflow-y-auto">
      <div className="max-w-[900px] mx-auto px-10 py-8">
        {collecting && (
          <div className="mb-6 bg-[var(--color-primary-soft)]/40 border border-[var(--color-primary-soft-strong)]/60 rounded-lg p-5">
            <div className="flex items-center gap-2 mb-3">
              <span className="inline-block w-4 h-4 border-2 border-[var(--color-primary)] border-t-transparent rounded-full animate-spin" />
              <p className="text-sm font-medium text-[var(--color-primary)]">报告生成中，请稍候…</p>
            </div>
            <div className="space-y-1 max-h-32 overflow-y-auto">
              {progress.map((msg, i) => (
                <p key={i} className="text-xs text-[var(--color-primary)]/80 font-mono">{msg}</p>
              ))}
              {progress.length === 0 && (
                <p className="text-xs text-[var(--color-primary)]/60">等待进度信息…</p>
              )}
            </div>
          </div>
        )}

        {!collecting && hasBriefing && (
          <>
            {headlines.length > 0 && (
              <section className="mb-8">
                <SectionHeader title="头条要闻" count={headlines.length} />
                <div className="space-y-4">
                  {headlines.map((item, i) => <HeadlineCard key={i} item={item} rank={i + 1} />)}
                </div>
              </section>
            )}

            {categorized.length > 0 && (
              <section className="mb-8">
                <SectionHeader title="分类精选" count={categorized.length} />
                {Object.entries(grouped).map(([cat, items]) => (
                  <div key={cat} className="mb-5">
                    <p className="text-xs font-semibold uppercase tracking-widest text-[var(--color-primary)] mb-3">{cat}</p>
                    <div className="space-y-3">
                      {items.map((item, i) => <CategorizedItem key={i} item={item} />)}
                    </div>
                  </div>
                ))}
              </section>
            )}

            {scan.length > 0 && (
              <section className="mb-8">
                <SectionHeader title="一句话扫描" count={scan.length} />
                <div className="space-y-0.5">
                  {scan.map((item, i) => <ScanItem key={i} item={item} />)}
                </div>
              </section>
            )}
          </>
        )}

        {!collecting && !loading && !isGenerating && !hasBriefing && (
          <div className="flex flex-col items-center justify-center py-24 text-[var(--color-outline)]">
            <span className="material-symbols-outlined mb-3" style={{ fontSize: 40 }}>radar</span>
            <p className="text-base mb-1">暂无报告</p>
            <p className="text-sm">点击侧边栏「采集新闻」开始</p>
          </div>
        )}

        {!collecting && loading && (
          <div className="flex items-center justify-center py-20">
            <p className="text-[var(--color-outline)] text-sm">加载中…</p>
          </div>
        )}
      </div>
    </main>
  )
}
```

**Step 2: Commit**

```powershell
git add frontend/src/pages/ReportPage.jsx
git commit -m "feat(frontend): three-tier briefing layout (headlines/categorized/scan)"
```

---

### Task 9: App.jsx — 更新数据流和下载 HTML

**Files:**
- Modify: `frontend/src/App.jsx`

**Step 1: 移除 signalsSections，更新 hasReport**

删除 `signalsSections` 的 `useMemo` 和 `downloadReport` 函数中对 `signalsSections` 的引用。

更新：
```jsx
const hasReport = !!(current?.briefing?.headlines?.length || current?.briefing?.categorized?.length)
```

**Step 2: 更新轮询检测逻辑**

将 `onGenerationComplete` 中的：
```jsx
try { return JSON.parse(rep.top10_ids || '[]').length > 0 } catch { return false }
```
改为：
```jsx
try {
  const b = typeof rep.briefing === 'string' ? JSON.parse(rep.briefing) : (rep.briefing || {})
  return (b.headlines?.length || 0) + (b.categorized?.length || 0) > 0
} catch { return false }
```

在 `useEffect` 初始加载中也作同样的修改。

**Step 3: 更新 downloadReport() 生成三段式 HTML**

将下载 HTML 内容改为三段式布局：
- 头条要闻：带 why_matters 的大卡片
- 分类精选：按分类分组的紧凑列表
- 一句话扫描：极简列表

```jsx
const downloadReport = useCallback(() => {
  const briefing = current?.briefing
  if (!briefing) return
  const { headlines = [], categorized = [], scan = [] } = briefing
  if (!headlines.length && !categorized.length) return

  const reportDate = formatTime(current.created_at)

  const headlinesHTML = headlines.map((item, i) => `
    <div class="headline-card">
      <div class="tags">
        <span class="rank">${i + 1}</span>
        ${item.main_category ? `<span class="cat-tag">${item.main_category}</span>` : ''}
      </div>
      <a class="title" href="${item.url}" target="_blank">${item.title} <span style="color:#6860ef">↗</span></a>
      ${item.summary ? `<div class="summary">${item.summary}</div>` : ''}
      ${item.why_matters ? `<div class="why-matters">💡 ${item.why_matters}</div>` : ''}
      <div class="meta">${item.source_name}${item.published_at ? ' · ' + item.published_at.slice(0,10) : ''}</div>
    </div>`).join('')

  // Group categorized by main_category
  const groups = {}
  for (const item of categorized) {
    const cat = item.main_category || '其他'
    if (!groups[cat]) groups[cat] = []
    groups[cat].push(item)
  }
  const categorizedHTML = Object.entries(groups).map(([cat, items]) => `
    <div class="cat-group">
      <p class="cat-header">${cat}</p>
      ${items.map(item => `
        <div class="cat-item">
          <a class="cat-title" href="${item.url}" target="_blank">${item.title}</a>
          ${item.brief ? `<p class="cat-brief">${item.brief}</p>` : ''}
          <p class="meta">${item.source_name}${item.published_at ? ' · ' + item.published_at.slice(0,10) : ''}</p>
        </div>`).join('')}
    </div>`).join('')

  const scanHTML = scan.map(item => `
    <div class="scan-item">
      · <a href="${item.url}" target="_blank">${item.title}</a>
      <span class="scan-source">${item.source_name}</span>
    </div>`).join('')

  const html = `<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>AI News Radar · ${reportDate.date}</title>
<style>
  * { margin:0; padding:0; box-sizing:border-box; }
  body { font-family:'PingFang SC','Microsoft YaHei',sans-serif; background:#f7f9fb; color:#191c1e; line-height:1.6; }
  .container { max-width:820px; margin:0 auto; padding:24px 16px; }
  .header { background:#1a146b; padding:24px; color:#fff; border-radius:12px; margin-bottom:24px; }
  .header h1 { font-size:20px; font-weight:700; }
  .header p { font-size:12px; opacity:0.8; margin-top:4px; }
  h2 { font-size:16px; font-weight:700; border-bottom:2px solid #1a146b; padding-bottom:6px; margin-bottom:16px; color:#191c1e; }
  section { margin-bottom:28px; }
  .headline-card { background:#fff; border-radius:8px; border:1px solid #eceef0; padding:16px; margin-bottom:12px; }
  .tags { display:flex; align-items:center; gap:6px; margin-bottom:8px; }
  .rank { width:22px; height:22px; background:#1a146b; color:#fff; font-size:11px; border-radius:4px; display:inline-flex; align-items:center; justify-content:center; font-weight:700; }
  .cat-tag { font-size:11px; padding:2px 8px; border-radius:12px; background:#e3dfff; color:#4e45d5; font-weight:600; }
  a.title { display:block; font-size:15px; font-weight:700; color:#191c1e; text-decoration:none; margin-bottom:8px; }
  .summary { background:#f7f9fb; border-radius:6px; padding:10px 12px; font-size:13px; color:#474651; margin-bottom:8px; }
  .why-matters { background:#ede9fe; border-radius:6px; padding:8px 12px; font-size:12px; color:#4e45d5; margin-bottom:8px; }
  .meta { font-size:11px; color:#777682; }
  .cat-group { margin-bottom:16px; }
  .cat-header { font-size:11px; font-weight:700; color:#1a146b; text-transform:uppercase; letter-spacing:0.1em; margin-bottom:8px; }
  .cat-item { border-left:2px solid #e3dfff; padding-left:10px; margin-bottom:10px; }
  a.cat-title { font-size:14px; font-weight:600; color:#191c1e; text-decoration:none; display:block; margin-bottom:2px; }
  .cat-brief { font-size:12px; color:#474651; }
  .scan-item { font-size:13px; color:#474651; padding:4px 0; display:flex; gap:8px; align-items:baseline; }
  .scan-item a { color:#1a146b; text-decoration:none; flex:1; }
  .scan-source { font-size:11px; color:#777682; white-space:nowrap; }
  .footer { text-align:center; padding:20px 0; font-size:11px; color:#777682; }
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>AI News Radar · 每日简报</h1>
    <p>${reportDate.date} ${reportDate.time}</p>
  </div>
  ${headlines.length ? `<section><h2>头条要闻</h2>${headlinesHTML}</section>` : ''}
  ${categorized.length ? `<section><h2>分类精选</h2>${categorizedHTML}</section>` : ''}
  ${scan.length ? `<section><h2>一句话扫描</h2>${scanHTML}</section>` : ''}
  <div class="footer">AI News Radar · 由 AI 自动生成</div>
</div>
</body>
</html>`

  const blob = new Blob([html], { type: 'text/html;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `AI-News-Radar-${reportDate.date}.html`
  a.click()
  URL.revokeObjectURL(url)
}, [current])
```

**Step 4: 更新 ReportPage props（移除 signalsSections）**

```jsx
<Route
  path="/"
  element={
    <ReportPage
      current={current}
      collecting={collecting}
      progress={progress}
      loading={loading}
      generatingId={GENERATING_ID}
    />
  }
/>
```

**Step 5: Commit**

```powershell
git add frontend/src/App.jsx
git commit -m "feat(frontend): update App.jsx for briefing-based data flow and download HTML"
```

---

### Task 10: 前端构建 + 验证

**Files:**
- Run: `cd frontend && npm run build`

**Step 1: 构建前端**

```powershell
cd frontend; npm run build
```
期望：Build 成功，无 TypeScript / lint 错误，`frontend/dist/` 更新。

**Step 2: 验证后端启动不报错**

```powershell
cd ..; python -c "from backend.analyzer import Analyzer; from backend.scorer import Scorer; print('imports OK')"
```
期望：`imports OK`

**Step 3: 验证 config.yaml 加载**

```powershell
python -c "from backend.pipeline import load_config, load_sources; cfg=load_config(); print(len(load_sources()),'个信源,',len(cfg['categories']),'个分类')"
```
期望：`32 个信源, 6 个分类`（30 website + 2 wechat）

**Step 4: Commit 构建产物**

```powershell
git add frontend/dist/
git commit -m "build: update frontend dist for three-tier briefing redesign"
```
