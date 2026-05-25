# AI News Radar 评分 / 信源 / 简报格式重设计

日期：2026-05-13

## 背景

现有评分模型（主题相关度70 + 媒体可信度30）过于简单，信源配置分散不成体系，报告输出格式（Top10 详细卡片）信息密度低。本次重设计覆盖三个核心维度。

---

## 1. 信源分级体系

tier 字段保持 1/2/3（内部映射 S/A/B），全量替换现有信源为以下推荐清单。

### S 级（tier: 1）—— 10 个一手官方信源
- OpenAI Blog（RSS）
- Anthropic News（RSS）
- Google DeepMind Blog（RSS）
- Meta AI Blog（RSS）
- Google AI Blog（RSS）
- arXiv cs.AI（RSS）
- arXiv cs.CL（RSS）
- Hugging Face Blog（RSS）
- 智谱 AI 官方（scrape）
- 月之暗面 / DeepSeek 官方（RSS / scrape）

### A 级（tier: 2）—— 10 个专业资讯媒体
- TechCrunch AI（RSS）
- MIT Technology Review（RSS）
- The Verge AI（RSS）
- Wired AI（RSS）
- 量子位（RSS）
- 机器之心（RSS）
- 晚点 LatePost（RSS）
- The Batch / DeepLearning.AI（scrape）
- InfoQ（RSS）
- 36氪 AI 频道（RSS）

### B 级（tier: 3）—— 10 个社区与个人信源
- Hacker News（RSS，hnrss.org/frontpage）
- Reddit r/MachineLearning（RSS）
- Reddit r/LocalLLaMA（RSS）
- Ben's Bites Newsletter（RSS）
- TLDR AI（RSS）
- Last Week in AI（RSS）
- LangChain Blog（RSS）
- 新智元（RSS）
- 钛媒体（RSS）
- AIBase（scrape）

---

## 2. 评分模型

### 公式
```
总分 = (信源分 + 内容分 + 热度分) × 时间衰减系数
```

| 维度 | 满分 | 来源 |
|---|---|---|
| 信源分 | 30 | tier 1→27, 2→20, 3→10 |
| 内容分 | 45 | LLM：实质性(0-15) + 信息密度(0-15) + 原创度(0-15) |
| 热度分 | 25 | deduplicator 的 report_count（同事件聚合数，归一化） |
| 时间衰减 | × | exp(-ln(2) × age_hours / half_life) |

### 时间衰减半衰期（按主类别）
| 类别 | 半衰期 |
|---|---|
| 模型发布 / 产品动态 | 48h |
| 产业商业 / 观点深度 | 168h（7天） |
| 研究论文 / 实操技巧 | 336h（14天） |
| 默认（未分类） | 72h |

### 实现位置
- `deduplicator.py`：在去重时记录每个保留项有多少重复被合并 → `report_count` 字段
- `scorer.py`：在已有 LLM 批量打分里添加3个内容评分子维度 + `main_category` 输出；在 `score_and_rank()` 里用新公式替换旧公式
- `ranker.py`：保留但不再被 pipeline 调用（scorer 已覆盖其功能）

### 热度分归一化
`hotness_score = min(25, report_count * 5)`
- 1条：5分（仅本源）
- 2条：10分（被2家报道）
- 5+条：25分（满分）

---

## 3. 内容分类

### 主类别（6个，替换现有）
| 类别 | 定义 | 时间衰减归属 |
|---|---|---|
| 模型发布 | 新模型/能力升级/Benchmark | 48h |
| 产品动态 | ToC/B 产品发布、功能更新 | 48h |
| 产业商业 | 融资、并购、人事、监管 | 168h |
| 研究论文 | arXiv、顶会、技术报告 | 336h |
| 实操技巧 | Prompt/Agent/工具/Workflow | 336h |
| 观点深度 | 长文分析、访谈、行业判断 | 168h |

### 辅助标签
由 LLM 自由生成，≤3个，不限定候选词表。用于检索和个性化，不影响评分。

---

## 4. 每日简报输出格式

三段式结构，总量 15-20 条：

### ① 头条要闻（3条）
- 跨类别选综合评分最高的3条
- 格式：3句摘要 + Why it matters（一句话）+ 原文链接

### ② 分类精选（10-12条）
- 按主类别分组
- 模型发布/产品动态各3条；产业商业/研究论文/实操技巧/观点深度各1-2条
- 格式：1-2句摘要 + 原文链接

### ③ 一句话扫描（≤5条）
- 评分不够头部但仍有参考价值的条目
- 格式：标题 + 原文链接

### 实现位置
- `analyzer.py`：新增 `_generate_briefing()` 方法替换 `_generate_strategic_advice()`；`analyze()` 返回 `briefing` 字段（包含3段）
- `pipeline.py`：更新 `report` 保存结构，存 `briefing` 而非 `signals`
- `frontend/ReportPage.jsx`：三段式布局替换现有 Top10 卡片
- `frontend/App.jsx`：更新 `signalsSections` 解析、下载 HTML 生成逻辑

---

## 5. Config 精简

### 移除字段
- `keywords`（采集过滤关键词移入 `filters.py` 内置）
- `strategic_advice`（被新简报格式替代）

### 保留字段
- `topics`（scorer LLM 打分仍需要话题上下文）
- `categories`（更新为新6个）
- `collection`、`dedup`、`scheduler`、`database`、`llm`

---

## 6. 受影响文件清单

| 文件 | 变更类型 |
|---|---|
| `config.yaml` | 全量替换信源、更新 categories、移除 keywords/strategic_advice |
| `backend/collector/filters.py` | 内置基础关键词（不依赖 config） |
| `backend/deduplicator.py` | 添加 report_count 字段 |
| `backend/scorer.py` | 新评分公式、LLM prompt 加内容评分+主类别 |
| `backend/analyzer.py` | 新 categories、aux_tags、三段式 briefing |
| `backend/pipeline.py` | 更新 report 保存结构 |
| `backend/main.py` | 更新 API 报告结构（检查是否需要改） |
| `frontend/src/pages/ReportPage.jsx` | 三段式布局 |
| `frontend/src/App.jsx` | 更新解析逻辑和下载 HTML |
