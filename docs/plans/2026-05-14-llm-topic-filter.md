# LLM 话题过滤重设计 实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 用 LLM 关联性分数替代关键词过滤，实现话题驱动的新闻筛选；移除全局关键词过滤，仅对 36氪/钛媒体/InfoQ 保留基础 AI 关键词预筛；简报不限制 10 条，按 LLM 关联性动态决定条数。

**Architecture:**
- 采集层：仅 36氪/钛媒体/InfoQ 三个综合媒体信源做关键词预筛（`source.keyword_filter: true`），其余直通。
- 评分层：`llm_relevance`（原已计算但未使用）作为乘法因子纳入最终得分；低于阈值（<30）的直接过滤。
- 分析层：Scorer 返回所有相关条目（不截断），Pipeline 取前 20 条做深度 LLM 分析，其余直接追加到简报扫描层。

**Tech Stack:** Python, FastAPI, SQLite, feedparser, BeautifulSoup, sentence-transformers, LLM (OpenAI-compatible)

---

### Task 1: config.yaml — 信源标记 + 采集上限

**Files:**
- Modify: `config.yaml`

**Step 1: 给三个综合媒体信源加 `keyword_filter: true`**

在 config.yaml 中找到以下三个信源，各加一行 `keyword_filter: true`：

```yaml
  - name: InfoQ
    institution: InfoQ
    tier: 2
    indicator: industry
    type: rss
    url: https://www.infoq.cn/feed
    keyword_filter: true          # ← 新增

  - name: 36氪AI频道
    institution: 36氪
    tier: 2
    indicator: industry
    type: rss
    url: https://36kr.com/feed
    keyword_filter: true          # ← 新增

  - name: 钛媒体
    institution: 钛媒体
    tier: 3
    indicator: industry
    type: rss
    url: https://www.tmtpost.com/rss.xml
    keyword_filter: true          # ← 新增
```

**Step 2: 采集查询上限改 300**

```yaml
collection:
  date_window_days: 3
  max_per_source: 5
  timeout_seconds: 30
  db_limit: 300                   # ← 新增（原 limit=200 硬编码在 pipeline.py）
```

**Step 3: 验证 YAML 格式正确**

```bash
python -c "import yaml; yaml.safe_load(open('config.yaml', encoding='utf-8'))"
```

Expected: 无报错

---

### Task 2: filters.py — 模块加载时初始化缓存

**Files:**
- Modify: `backend/collector/filters.py`

**目标：** `is_ai_related(title, summary)` 不传 keywords 时默认用 `_BASE_KEYWORDS`（当前行为是 `return True`，会让所有内容通过）。同时移除 `get_all_keywords()`，该函数不再被调用。

**Step 1: 修改 filters.py**

将文件改为：

```python
"""采集阶段的 AI 相关性预筛（仅用于标记了 keyword_filter 的信源）。"""

import re
from typing import List

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


# 模块加载时即用 _BASE_KEYWORDS 初始化，不再需要外部预热
_BASE_RE = _build_regex(_BASE_KEYWORDS)


def is_ai_related(title: str, summary: str = "") -> bool:
    """判断标题/摘要是否包含基础 AI 关键词。仅供 keyword_filter=true 的信源调用。"""
    return bool(_BASE_RE.search(f"{title} {summary}"))
```

**Step 2: 验证导入正常**

```bash
python -c "from backend.collector.filters import is_ai_related; print(is_ai_related('GPT-4 发布'))"
```

Expected: `True`

---

### Task 3: rss.py + scraper.py — 按信源标记决定是否过滤

**Files:**
- Modify: `backend/collector/rss.py`
- Modify: `backend/collector/scraper.py`

**rss.py Step 1: 改 collect() 中的过滤逻辑**

将 `rss.py` 中：
```python
# AI 相关性预筛：跳过明显与 AI 无关的新闻
if not is_ai_related(title, summary):
    skipped += 1
    continue
```

改为：
```python
# 仅对标记了 keyword_filter 的综合媒体信源做关键词预筛
if source.get('keyword_filter', False) and not is_ai_related(title, summary):
    skipped += 1
    continue
```

同时更新导入（`is_ai_related` 签名简化了，不再需要 `keywords` 参数）：
```python
from backend.collector.filters import is_ai_related
```

**scraper.py Step 2: 改 _extract_from_elements() 中的过滤逻辑**

将 `scraper.py:159` 处：
```python
if not is_ai_related(title, summary):
    skipped += 1
    continue
```

改为：
```python
if source.get('keyword_filter', False) and not is_ai_related(title, summary):
    skipped += 1
    continue
```

同时更新导入：
```python
from backend.collector.filters import is_ai_related
```

**Step 3: 验证语法正确**

```bash
python -c "from backend.collector.rss import RSSCollector; from backend.collector.scraper import WebScraper; print('OK')"
```

Expected: `OK`

---

### Task 4: scorer.py — LLM 关联性分数纳入排序，移除 top_n

**Files:**
- Modify: `backend/scorer.py`

**改动说明：**
- 移除 `score_and_rank()` 的 `top_n` 参数
- 新增 `_MIN_RELEVANCE = 30` 常量
- 最终得分公式加入 `relevance_factor`（乘数）
- 有话题配置时，`llm_relevance < 30` 的条目直接过滤掉
- 移除末尾的同源限制循环（改在 pipeline 层处理）

**Step 1: 修改常量区（文件顶部）**

在 `_SOURCE_CAP = 2` 这行后面新增：
```python
_MIN_RELEVANCE = 30          # LLM 关联性低于此值直接过滤
```

**Step 2: 修改 `score_and_rank()` 签名**

```python
def score_and_rank(self, news_list: List[Dict]) -> List[Dict]:
```
（移除 `top_n: int = 10` 参数）

**Step 3: 修改 Step 5（最终得分 + 排序）**

将现有 Step 5 代码块整体替换：

```python
        # Step 5: 最终得分 + 排序
        for item in candidates:
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
            # 有话题配置时，relevance 作为乘法因子（0→0.2 到 100→1.0）
            if self.topics:
                relevance = float(item.get("llm_relevance", 50))
                relevance_factor = 0.2 + 0.8 * (relevance / 100.0)
            else:
                relevance_factor = 1.0
            item["score"] = (source_score + content_score + hotness) * decay * relevance_factor

        # 有话题配置时过滤低关联性条目
        if self.topics:
            before = len(candidates)
            candidates = [n for n in candidates if n.get("llm_relevance", 0) >= _MIN_RELEVANCE]
            filtered = before - len(candidates)
            if filtered:
                print(f"[Scorer] 关联性过滤: 移除 {filtered} 条 relevance<{_MIN_RELEVANCE} 的新闻", flush=True)

        candidates.sort(key=lambda x: x["score"], reverse=True)
        return candidates
```

（注意：**删除**原来末尾的「同源限制」循环，该逻辑移至 pipeline。）

**Step 4: 验证导入**

```bash
python -c "from backend.scorer import Scorer; print('OK')"
```

Expected: `OK`

---

### Task 5: analyzer.py — 接收 scan_extras，移除 TOP_N 截断

**Files:**
- Modify: `backend/analyzer.py`

**Step 1: 修改常量**

```python
TOP_N = 10
```
改为：
```python
_DEEP_ANALYZE_N = 20   # 深度分析条数上限（由 pipeline 控制传入，这里仅作文档说明）
```

**Step 2: 修改 `analyze()` 签名和开头**

```python
def analyze(self, news_list: List[Dict], scan_extras: List[Dict] = None) -> Dict:
    if not news_list:
        return {"news": [], "briefing": {"headlines": [], "categorized": [], "scan": []}}

    print(f"[Analyzer] 接收预排序新闻 {len(news_list)} 条，进入分析", flush=True)
```

同时**删除**：
```python
top10 = news_list[:TOP_N]
print(f"[Analyzer] 接收预排序新闻 {len(top10)} 条，进入分析", flush=True)
```

**Step 3: 将 analyze() 中所有 `top10` 变量改为 `news_list`**

共 4 处：
- `self._analyze_news_items(top10)` → `self._analyze_news_items(news_list)`
- `for i, item in enumerate(top10):` → `for i, item in enumerate(news_list):`
- `briefing = self._generate_briefing(top10, ...)` → `self._generate_briefing(news_list, ...)`

**Step 4: 在 `analyze()` 返回前追加 scan_extras 到扫描层**

在 `return {...}` 之前插入：

```python
        # 追加未深度分析的条目到扫描层（直接用原始数据，无需 LLM）
        for item in (scan_extras or []):
            briefing["scan"].append({
                "title": item.get("title_cn") or item["title"],
                "url": item.get("url", ""),
                "source_name": item.get("source_name", ""),
            })
```

**Step 5: 修改返回值，将 `top10` key 改为 `news`**

```python
        return {
            "news": news_list,    # 原来是 "top10": top10
            "briefing": briefing,
            "summaries": summaries,
            "main_categories": main_categories,
            "aux_tags": aux_tags,
            "concepts": concepts,
            "principles": principles,
        }
```

**Step 6: 验证导入**

```bash
python -c "from backend.analyzer import Analyzer; print('OK')"
```

Expected: `OK`

---

### Task 6: pipeline.py — 串联所有变更

**Files:**
- Modify: `backend/pipeline.py`

**Step 1: 更新导入**

移除：
```python
from backend.collector.filters import get_all_keywords, is_ai_related
```

改为（仅保留）：
```python
# filters 导入已不需要（关键词预筛已在 rss.py/scraper.py 内部处理）
```

**Step 2: 修改 `Pipeline.__init__()`**

删除以下两行（不再需要关键词预热）：
```python
self.keywords = get_all_keywords(config)
is_ai_related("", "", keywords=self.keywords)
```

同时将 emit 信息更新：
```python
emit(f"开始采集新闻...")
```

**Step 3: 修改查询上限**

```python
recent_news = self.db.get_news_within_days(days=self.date_window_days, limit=300)
```

如果 config.yaml 里加了 `db_limit` 字段，可改为：
```python
db_limit = self.config.get("collection", {}).get("db_limit", 300)
recent_news = self.db.get_news_within_days(days=self.date_window_days, limit=db_limit)
```

**Step 4: 修改 Scorer 调用**

```python
# 综合评分（移除 top_n，Scorer 返回所有相关条目）
emit(f"综合评分：{len(recent_news)} 条候选（时效+关联性）...")
all_relevant = self.scorer.score_and_rank(recent_news)
score_map = {n["id"]: n["score"] for n in all_relevant}
self.db.update_scores(score_map)
```

**Step 5: 新增深度/扫描分层逻辑**

```python
        # 深度分析层（前 20 条，保留同源限制）+ 扫描层（其余相关条目）
        _DEEP_N = 20
        _DEEP_SOURCE_CAP = 2
        deep_news: List[Dict] = []
        source_counts: Dict[str, int] = {}
        for item in all_relevant:
            src = item.get("source_name", "unknown")
            if source_counts.get(src, 0) >= _DEEP_SOURCE_CAP:
                continue
            deep_news.append(item)
            source_counts[src] = source_counts.get(src, 0) + 1
            if len(deep_news) >= _DEEP_N:
                break

        deep_ids = {n["id"] for n in deep_news}
        scan_extras = [n for n in all_relevant if n["id"] not in deep_ids]

        emit(f"评分完成: 相关 {len(all_relevant)} 条 → 深度分析 {len(deep_news)} 条 / 扫描层 {len(scan_extras)} 条")
```

**Step 6: 修改 Analyzer 调用**

```python
        analysis = self.analyzer.analyze(deep_news, scan_extras=scan_extras)
```

**Step 7: 修改报告保存**

将所有 `analysis["top10"]` 改为 `analysis["news"]`：

```python
        report = {
            ...
            "top10_ids": json.dumps(
                [n["id"] for n in analysis["news"]] +
                [n["id"] for n in scan_extras]
            ),
            ...
            "titles_cn": json.dumps(
                {str(i+1): n.get("title_cn", "") for i, n in enumerate(analysis["news"])},
                ensure_ascii=False,
            ),
        }
```

**Step 8: 验证导入**

```bash
python -c "from backend.pipeline import Pipeline; print('OK')"
```

Expected: `OK`

---

### Task 7: main.py — 同步 analyze 端点

**Files:**
- Modify: `backend/main.py`

`/api/analyze` 端点的 `run_analyze()` 内部有一套独立的 Scorer + Analyzer 调用，与 pipeline.py 类似，需同步相同修改：

**Step 1: 修改 Scorer 调用**

```python
top_items = scorer.score_and_rank(recent_news)   # 移除 top_n=10
```

**Step 2: 新增分层逻辑（同 pipeline.py Task 6 Step 5）**

在 scorer 调用后、analyzer 调用前，添加相同的 deep_news / scan_extras 分层代码。

**Step 3: 修改 Analyzer 调用**

```python
analysis = analyzer.analyze(deep_news, scan_extras=scan_extras)
```

**Step 4: 修改 report 保存**

将 `analysis["top10"]` 改为 `analysis["news"]`，`top10_ids` 同样存入所有相关 ID。

**Step 5: 启动服务验证**

```bash
python -m uvicorn backend.main:app --reload --port 8000
```

访问 `http://localhost:8000/api/health`，Expected: `{"status":"ok"}`

---

### Task 8: 端到端冒烟测试

**Step 1: 触发一次手动采集**

在前端点击「+ 采集新闻」或：
```bash
curl -X POST http://localhost:8000/api/collect
```

**Step 2: 观察后端日志，确认关键输出**

期望看到：
- `采集: 36氪AI频道` → 后面有 `预筛跳过 X 条非AI新闻`（关键词过滤生效）
- `采集: 量子位` → 无 `预筛跳过` 日志（不过滤）
- `综合评分：XXX 条候选`（应 > 原来的 200 上限可到 300）
- `关联性过滤: 移除 X 条 relevance<30 的新闻`（新逻辑生效）
- `深度分析 XX 条 / 扫描层 XX 条`（分层生效）

**Step 3: 查看生成的报告**

前端切到报告页，确认：
- 「一句话扫描」区块条数 > 5（原来硬限制 5 条）
- 头条和分类精选内容正常显示

---
