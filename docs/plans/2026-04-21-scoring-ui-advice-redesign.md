# 评分机制 / 报告 UI / 战略建议可配置 · 重构设计

日期：2026-04-21

## 背景

项目已经把 sources/topics/keywords/categories 等都迁移到 `config.yaml`，但仍有三处硬编码没跟上「配置驱动」的设计：

1. **评分机制**（`backend/ranker.py`）用硬编码的公司产品线关键词和媒体白名单，与 topics 配置解耦。
2. **报告页顶部**有两层硬编码的分类筛选 UI（全部/AI/算力/协同办公/鸿蒙/信创），与 `config.yaml` 的 `categories` 字段不一致，且功能冗余。
3. **战略建议**固定两块（「价值与商机」「公司启发」），生成视角、标题、条数都无法调整。

## 一、评分机制重构

### 目标

评分逻辑改为 **主题关联度 + 媒体可信度** 两维，全部由 `config.yaml` 驱动，不再维护硬编码关键词表。

### 算法

**总分 = 主题关联度(0-70) + 媒体可信度(0-30) = 0-100**

#### 主题关联度（0-70）

语义为主，关键词加分兜底：

1. 复用 `backend/deduplicator.py` 已加载的 sentence-transformers 模型（`paraphrase-multilingual-MiniLM-L12-v2`）。抽出一个懒加载的 shared 单例，避免 ranker 重复加载。
2. 初始化时为每个 topic 编码：`f"{name}。{description}。关键词：{', '.join(keywords)}"`。
3. 每条新闻编码：`title + "。" + summary`。
4. 余弦相似度取 topics 中最大值：`semantic_score = max(cos) * 60`（0-60 分）。
5. 关键词命中加分：若 `title + summary` 命中任一 topic 的任一 keyword，则 `+10` 分（封顶，不按命中数累加）。
6. `topic_relevance = min(70, semantic_score + keyword_bonus)`。

#### 媒体可信度（0-30）

直接用信源已有的 `tier` 字段：

| tier | 分数 |
|------|------|
| 1    | 30   |
| 2    | 20   |
| 3    | 10   |
| 缺失 | 15   |

### `score_detail` 结构

```python
{
  "topic_relevance": 46.0,
  "semantic_score": 36.0,      # cos_max * 60
  "keyword_bonus": 10.0,        # 0 或 10
  "best_topic": "大模型竞争格局",
  "matched_keywords": ["GPT", "Claude"],
  "tier_score": 30,
  "tier": 1,
  "total": 76.0,
}
```

### 改动文件

- `backend/ranker.py` — 完全重写（删除 `_AUTHORITY_MAP`、`_HIGH_RELEVANCE_KEYWORDS`、`_MID_RELEVANCE_KEYWORDS`、`_REACH_BY_AUTHORITY`、`_BREAKTHROUGH_KEYWORDS`、`_ROUTINE_KEYWORDS`）
- `backend/deduplicator.py` — 抽出 shared embedding model 单例（或新增 `backend/embeddings.py`）
- `backend/pipeline.py` — `Ranker(topics=config.get("topics", []))`
- `backend/main.py` — `run_analyze` 内部同样修改
- `tests/test_ranker.py` — 新增

### 测试覆盖

- 空 topics → 所有新闻 relevance = 0，tier 仍生效
- 命中关键词但语义远 → keyword_bonus = 10
- 语义近但未命中关键词 → 只拿 semantic_score
- tier 1/2/3/缺失 的 tier_score 映射
- 多 topic 取 max

---

## 二、报告页筛选 UI 删除

### 目标

移除报告页顶部两层筛选（统计卡片 + 圆角标签按钮），直接展示完整新闻列表。

### 改动

文件：`frontend/src/pages/ReportPage.jsx`

- 删除硬编码数组 `categories`（第 170 行）
- 删除 `activeCategory` state 及 `loadReport` 里的 `setActiveCategory('全部')`
- 删除 `categoryCounts` 统计 memo（但保留 `_originalRank` 排名标注，改名为 `rankedNews`）
- 删除统计卡片 grid（第 499-518 行）和圆角标签按钮（第 521-535 行）
- `AI资讯概览` 标题改为 `AI资讯概览（共 {N} 条）`，右侧下载按钮保留

### 新的顶部结构

```
战略建议区（渐变背景）
────────────────────────
AI资讯概览（共 N 条）        [下载按钮]
────────────────────────
新闻卡片列表（按原始排名）
```

### 测试

前端无单元测试框架，采用手动验证：
- `cd frontend && npm run build` 构建无错
- 启动后端 + 前端，切换报告，确认无 JS 报错，新闻全部展示

---

## 三、战略建议模块可配置

### 目标

让用户在配置页自定义战略建议模块（标题、分析视角描述、条数），支持任意数量。

### 配置 Schema

`config.yaml` 新增：

```yaml
strategic_advice:
  - title: 价值与商机
    description: 从企业决策者视角，指出行业趋势中的商业机会
    count: 3
  - title: 启发建议
    description: 结合监控话题中的业务方向，给出具体可行的建议
    count: 3
```

缺失时 fallback 为上述默认两项。

### 后端改动

**`backend/analyzer.py`**

- `Analyzer.__init__` 新增参数 `strategic_advice_modules: List[Dict]`
- `_generate_strategic_advice` 动态拼 prompt：

```python
sections_spec = "\n".join(
    f'{i+1}. {m["title"]}（{m["count"]}条）：{m["description"]}'
    for i, m in enumerate(modules)
)
example = {"sections": [
    {"title": m["title"], "items": ["..."] * m["count"]}
    for m in modules
]}
```

- 返回格式统一：`{"sections": [{"title": "...", "items": [...]}]}`
- LLM 返回顺序乱时按 `title` 匹配回用户配置；漏模块时按位置兜底；不足 count 不补

**`backend/pipeline.py` + `backend/main.py`**

- 两处 `Analyzer(...)` 构造都新增 `strategic_advice_modules=config.get("strategic_advice", DEFAULTS)`

**`backend/main.py` `get_report`**

读取时规整三种历史格式 → 新格式 `{sections: [...]}`，作为唯一对外契约：

```python
def _normalize_signals(raw) -> dict:
    if isinstance(raw, dict) and "sections" in raw:
        return raw
    if isinstance(raw, dict) and ("values" in raw or "inspirations" in raw):
        sections = []
        if raw.get("values"):
            sections.append({"title": "价值与商机", "items": raw["values"]})
        if raw.get("inspirations"):
            sections.append({"title": "公司启发", "items": raw["inspirations"]})
        return {"sections": sections}
    if isinstance(raw, list):
        items = [f'{s.get("title","")}{"，"+s["analysis"] if s.get("analysis") else ""}'
                 for s in raw if isinstance(s, dict)]
        return {"sections": [{"title": "战略建议", "items": items}] if items else []}
    return {"sections": []}
```

抽为纯函数便于测试。

### 前端改动

**`frontend/src/pages/ConfigPage.jsx`**

- 新增 section「战略建议模块」，复用 `TopicCard` 组件模式
- 每个模块卡片：`title` input + `description` textarea + `count` number input + 删除按钮
- 顶部 + 号新增模块

**`frontend/src/pages/ReportPage.jsx`**

- `signalsData` 直接用 `current.signals.sections`（兼容由后端保证，前端不再转换）
- 渲染战略建议区改为循环：

```jsx
{signalsData?.sections?.map((section, i) => (
  <div key={i} className="bg-white/15 backdrop-blur-sm rounded-xl px-5 py-4 mb-3 border border-white/20 last:mb-0">
    <p className="text-sm font-semibold text-white mb-2">{section.title}</p>
    <ol className="space-y-1.5">
      {section.items.map((v, j) => (
        <li key={j} className="text-sm text-white/90">{j + 1}. {v}</li>
      ))}
    </ol>
  </div>
))}
```

- `downloadReport` HTML 模板做同样的循环改造

### 测试

- `tests/test_analyzer_advice.py` — 单/多模块 prompt 组装、LLM 返回乱序/漏模块的容错
- `tests/test_signals_compat.py` — 抽出的 `_normalize_signals` 对三种历史格式的转换

---

## 改动清单汇总

### 后端

- `backend/ranker.py` 完全重写
- `backend/deduplicator.py` 或新增 `backend/embeddings.py` — shared embedding model 单例
- `backend/analyzer.py` — `_generate_strategic_advice` 改为动态模块驱动
- `backend/pipeline.py` — Ranker/Analyzer 构造增加参数
- `backend/main.py` — `run_analyze` + `get_report` 同步改

### 前端

- `frontend/src/pages/ConfigPage.jsx` — 新增「战略建议模块」配置区
- `frontend/src/pages/ReportPage.jsx` — 删除筛选 UI + 战略建议渲染改循环 + `downloadReport` 模板改循环

### 配置

- `config.yaml` — 新增 `strategic_advice` 块（默认两项）

### 测试

- `tests/test_ranker.py`
- `tests/test_analyzer_advice.py`
- `tests/test_signals_compat.py`

### 文档

- `docs/plans/2026-04-21-scoring-ui-advice-redesign.md`（本文档）
- 完成后在 `docs/devlog.md` 追加条目

## 后续

- 实施计划拆分：可在单个 session 内完成（按「评分 → UI 删除 → 战略建议」顺序实现）
- 无需 git worktree 隔离（改动集中，且 master 分支已有较多未提交的 WIP）
