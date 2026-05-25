# 评分机制完善 + Wiki 知识库落地方案

> ⚠️ **已废弃（仅存档）**：本文档描述的 Wiki 知识库 / 信息增量评分机制已于 2026-05-19 整体下线（提交 `e2a0bbf`、`face1e2`）。当前系统不再使用 wiki 增量判定，话题过滤由 `llm_relevance` 主导。本文仅作历史设计记录保留。

**日期**：2026-04-30  
**目标**：解决重要新闻被埋（B）和旧闻重发混入 Top 10（C）两个核心痛点，同时以副产品形式积累可生长的 AI 知识库。

---

## 核心思路

将现有两步评分（`ranker.py` 规则预排 → `analyzer.py` LLM 业务关联性重打分）合并为一个**新综合评分器**，以「信息增量」为核心维度，结合 Wiki 历史知识库做精准增量判定。

---

## 一、Wiki DB 结构

在现有 SQLite 中新增两张表：

```sql
-- 结构化新闻索引（90天滚动保留）
wiki_news_index (
  id           TEXT PRIMARY KEY,   -- 同 news.id
  event_id     TEXT,               -- 归一化事件ID（LLM提取）
  dimensions   TEXT,               -- JSON: ["概念发布","数据披露"]
  key_facts    TEXT,               -- JSON: ["事实1","事实2","事实3"]
  published_at DATETIME,
  increment_level TEXT             -- S/A/B/C/D
)

-- 概念节点（永久保留）
wiki_concepts (
  name           TEXT PRIMARY KEY, -- 归一化概念名
  definition     TEXT,             -- 60字以内定义
  first_seen     DATE,
  related_events TEXT              -- JSON: [event_id, ...]
)
```

**保留策略**：
- `wiki_news_index`：超过 90 天的记录在每次 Pipeline 运行时清理
- `wiki_concepts`：永久保留，核心概念只增不删

**数据来源**：Step 2 分析时已提取 `concept`/`principle`/`practice`，直接复用回填，无需额外 LLM 调用建库。

---

## 二、改造后的 Pipeline 流程

```
采集 → 去重 → DB
  ↓
取近 N 天新闻（limit ~200条）
  ↓
★ 新综合评分器（替换原 ranker.py + analyzer Step 1）
  见第三节
  ↓ Top 10（含同源限制 ≤2条/源）
  ↓
Analyzer Step 2（不变）：逐条分析
  summary / keywords / concept / principle / practice ...
  ↓
★ 新增：Wiki 回填
  复用 Step 2 提取字段 → 写入 wiki_news_index + wiki_concepts
  ↓
Analyzer Step 3（不变）：战略建议
```

---

## 三、新综合评分器

### 3.1 四步处理流程

```
~200条新闻
  ↓
① 时效拦截（纯规则，极快）
   发布 > 72h → score = 0，直接排除

② Embedding 相关性过滤（纯规则）
   cos < 0.3 → 排除明显无关
   保留约 60-80 条候选

③ Wiki 增量上下文准备
   用 embedding 为每条候选匹配 Top-3 历史相关条目
   来源：wiki_news_index 近 30 天

④ LLM 综合打分（分批，每批 20 条）
   输出：业务关联性（0-100）+ 增量等级（S/A/B/C/D）
```

### 3.2 最终得分公式

```
freshness     = e^(-0.1 × 发布距今小时数)     # 0-1，72h后趋近0
increment_map = {S:100, A:80, B:30, C:5, D:0}
tier_factor   = {1:1.0, 2:0.85, 3:0.70, None:0.80}

score = (业务关联性×0.5 + increment_map[等级]×0.5)
        × freshness
        × tier_factor
```

取 `score` 最高的前 10 条，同源限制 ≤ 2 条/源。

---

## 四、LLM 综合打分 Prompt 设计

### 输入结构（每批 20 条）

```
你是AI产业分析师。请对以下新闻评估两个维度：
1. 业务关联性（0-100）：与监控话题的相关程度
2. 信息增量等级：
   S（全新）：知识库中无任何同源记录
   A（新维度）：主题已有，但本次提供全新信息维度（如已有概念发布，本次是实测数据）
   B（低增量）：主题已有，仅补充边缘信息，核心事实高度重合
   C（复述）：与已有记录高度重复，仅改标题/措辞
   D（旧闻）：内容与已有记录完全一致，或超过72h的旧事件无新进展

[监控话题]
{topics_brief}

[历史知识库摘要 - 近30天]
事件"Claude 4发布" 已覆盖维度：概念发布、产品参数
事件"国产大模型监管" 已覆盖维度：政策解读
...（每条新闻匹配其Top-3相似历史条目，格式：事件名 + 已覆盖维度）

[待评估新闻]
[1] 标题：... 摘要：...
    相关历史：事件"X" 已有维度：Y
[2] ...

输出JSON：
{"1": {"relevance": 85, "increment": "A", "reason": "新增实测数据维度"}, ...}
```

### Wiki 上下文控制

- 每条新闻只传 Top-3 相似历史条目，压缩为「事件名 + 已覆盖维度」
- 单条上下文约 30-50 tokens，20 条一批总 token 可控
- 不传历史全文，避免 context 膨胀

---

## 五、增量等级判定标准（供 LLM 参考）

| 等级 | 判定标准 | 得分 |
|------|---------|------|
| S（全新）| Wiki 中无同源事件记录 | 100 |
| A（新维度）| 同主题已有，但本次维度完全不重叠（如：概念发布→原理拆解→实测数据） | 80 |
| B（低增量）| 同主题已有，本次仅补充边缘信息，核心事实重合度高 | 30 |
| C（复述）| 核心事实、结论与已有记录一致，仅换标题/措辞 | 5 |
| D（旧闻）| 内容与已有记录完全一致，或系旧事件无新进展的重发 | 0 |

---

## 六、改动文件清单

| 文件 | 改动类型 | 说明 |
|------|---------|------|
| `backend/db.py` | 新增 | `wiki_news_index` / `wiki_concepts` 表的 DDL + CRUD |
| `backend/ranker.py` | 废弃/替换 | 原规则排序逻辑迁移到新综合评分器 |
| `backend/scorer.py` | 新建 | 新综合评分器（四步流程 + 最终得分公式） |
| `backend/analyzer.py` | 修改 | 移除 Step 1（LLM 业务关联性打分），新增 Wiki 回填逻辑 |
| `backend/pipeline.py` | 修改 | 将 `ranker.rank()` 替换为 `scorer.score_and_rank()` |

---

## 七、冷启动策略

Wiki 首次运行为空，增量等级全为 S（全新），属于正常行为。经过 3-5 次运行后知识库开始积累，增量判定精度逐步提升。可选：对历史 `reports` 表中已有的 `concepts`/`principles` 字段做一次性回填，缩短冷启动期。
