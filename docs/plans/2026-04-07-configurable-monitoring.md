# 可配置监控系统设计

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将信源、话题、关键词、新闻类别全部做成前端可配置，统一存储在 config.yaml 中。

---

## 数据模型（config.yaml 新结构）

```yaml
# === 监控话题 ===
topics:
  - name: 公司
    description: |
      公司...（完整公司背景）
    keywords: [协同办公, 邮箱, 信创, 智算, 数字人]

  - name: 大模型竞争格局
    description: 关注国内外大模型厂商的最新动态、性能对比、开源进展
    keywords: [GPT, Claude, Gemini, Llama, DeepSeek, Qwen, 开源模型]

  - name: AI监管政策
    description: 各国AI立法、合规要求、数据安全相关政策
    keywords: [AI治理, AI安全, AI监管, 合规, 数据安全]

# === AI 关键词（采集预筛） ===
keywords:
  base:
    - AI
    - 人工智能
    - 机器学习
    - 深度学习
    - 大模型
    - LLM
    - GPT
    - ... （从 filters.py 迁移）
  custom: []

# === 新闻类别（LLM 分类约束） ===
categories:
  - 大模型
  - AI应用
  - 芯片/算力
  - AI监管
  - 投融资
  - 企业动态

# === 信源 ===
sources:
  websites:
    - name: OpenAI Research Blog
      institution: OpenAI
      tier: 1
      indicator: academic
      type: rss
      url: https://openai.com/blog/rss.xml
      selector: ""
    - name: 36氪AI频道
      institution: 36氪
      tier: 2
      indicator: industry
      type: scrape
      url: https://36kr.com/information/AI/
      selector: "a.article-item-title"
    # ... 其余网站信源

  wechat:
    - name: 量子位（公众号）
      institution: 量子位
      tier: 2
      indicator: industry
      nickname: 量子位
    - name: 机器之心（公众号）
      institution: 机器之心
      tier: 2
      indicator: industry
      nickname: 机器之心
    # ...

# === 其他配置（不变） ===
collection:
  max_per_source: 5
  timeout_seconds: 120
database:
  path: data/news_radar.db
dedup:
  semantic_threshold: 0.85
llm:
  provider: openai
  model: MiniMax-M2.5
  api_key: ...
  base_url: ...
scheduler:
  cron: "0 8 * * *"
  enabled: true
```

---

## 前端配置页布局

```
┌─────────────────────────────────────┐
│ 系统配置                              │
├─────────────────────────────────────┤
│ ① LLM 配置          （现有，不变）     │
├─────────────────────────────────────┤
│ ② 监控话题                           │
│   可折叠卡片列表，每个话题：            │
│   - 名称、描述（文本框）、关键词（tag） │
│   [+ 添加话题]                       │
├─────────────────────────────────────┤
│ ③ 关键词                             │
│   基础关键词: tag 列表（可增删）        │
│   自定义关键词: tag 列表 + 添加        │
├─────────────────────────────────────┤
│ ④ 新闻类别                           │
│   tag 列表（可增删）                   │
│   [+ 添加类别]                       │
├─────────────────────────────────────┤
│ ⑤ 网站信源                           │
│   表格: 名称|机构|类型|URL|操作        │
│   [+ 添加信源]                       │
├─────────────────────────────────────┤
│ ⑥ 微信公众号                         │
│   凭证状态 + 扫码登录 + 仅采集微信     │
│   表格: 名称|机构|昵称|操作            │
│   [+ 添加公众号]                     │
├─────────────────────────────────────┤
│ ⑦ 采集配置          （现有，不变）     │
├─────────────────────────────────────┤
│ ⑧ 定时任务          （现有，不变）     │
├─────────────────────────────────────┤
│         [保存配置]                    │
└─────────────────────────────────────┘
```

---

## 后端改动

### 1. 配置读写

- `load_sources()` 改为从 config.yaml 读取 `sources.websites` + `sources.wechat`
- 返回统一列表，websites 保留原有 type 字段，wechat 自动补充 `type: "wechat"`

### 2. 关键词过滤

- `filters.py` 的 `is_ai_related()` 改为接收关键词列表参数
- 关键词 = `keywords.base` + `keywords.custom` + 所有 `topics[].keywords` 去重合并
- Pipeline 在初始化时从 config 组装关键词列表，传给 filter

### 3. LLM 分析

- `analyzer.py` 构造函数改为接收 `topics` 列表和 `categories` 列表
- Prompt 中拼接所有话题描述，替代原来的 `company_profile`
- 分类约束：在 prompt 中注入 categories 列表，要求 LLM 从中选择

### 4. 迁移

首次启动时自动迁移：
- 读取 sources.yaml → 写入 config.yaml 的 `sources.websites` / `sources.wechat`
- `company.profile` → 创建第一个 topic（名称取 `company.name` 或 "默认话题"）
- filters.py 硬编码关键词 → `keywords.base`
- 迁移后 sources.yaml 保留但不再使用

### 5. API Key 安全

现有 `GET /api/config` 隐藏 api_key 的逻辑保持不变。

---

## 实施任务

### Task 1: 迁移数据到 config.yaml

**Files:** config.yaml, backend/pipeline.py

- 将 sources.yaml 内容迁移到 config.yaml 的 `sources.websites` / `sources.wechat`
- 将 `company` 改为 `topics` 列表（第一个 topic 用原有 profile）
- 添加 `keywords.base`（从 filters.py 复制）、`keywords.custom: []`
- 添加 `categories` 列表
- 修改 `load_sources()` 从 config.yaml 读取

### Task 2: 改造关键词过滤

**Files:** backend/collector/filters.py, backend/pipeline.py

- `is_ai_related()` 改为接收关键词列表参数
- Pipeline 初始化时从 config 组装完整关键词列表
- 传递给 RSSCollector、WebScraper、WechatCollector 使用

### Task 3: 改造 LLM 分析

**Files:** backend/analyzer.py

- 构造函数改为接收 `topics` 和 `categories`
- 重写 prompt 模板：拼接所有话题描述 + 类别约束
- Pipeline 中传入 config 的 topics 和 categories

### Task 4: 前端 - 监控话题 section

**Files:** frontend/src/pages/ConfigPage.jsx

- 可折叠卡片列表
- 每个话题：名称输入框、描述文本框、关键词 tag 编辑
- 添加/删除话题

### Task 5: 前端 - 关键词 section

**Files:** frontend/src/pages/ConfigPage.jsx

- 基础关键词 tag 列表（可增删）
- 自定义关键词 tag 列表（可增删）

### Task 6: 前端 - 新闻类别 section

**Files:** frontend/src/pages/ConfigPage.jsx

- 类别 tag 列表（可增删）

### Task 7: 前端 - 网站信源 section

**Files:** frontend/src/pages/ConfigPage.jsx

- 表格展示现有网站信源
- 添加信源弹窗/表单（name, institution, tier, indicator, type, url, selector）
- 编辑/删除操作

### Task 8: 前端 - 微信公众号 section

**Files:** frontend/src/pages/ConfigPage.jsx

- 保留现有扫码登录 + 仅采集微信按钮
- 添加公众号表格（name, institution, nickname）
- 添加/删除操作

### Task 9: 清理与验证

- 删除 sources.yaml（或标记废弃）
- 删除 filters.py 中硬编码关键词
- 删除 config.yaml 中的 `company` 字段
- 端到端验证：修改配置 → 保存 → 采集 → 分析
