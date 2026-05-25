# AI News Radar

AI 新闻自动采集、分析与报告系统，满足用户的AI 动态监测需求。

系统每天自动从数十个 AI 信源抓取最新动态，去重后用大模型评分、筛选、撰写中文摘要与战略建议，最终生成一份当日 AI 简报，在网页上展示。

---

## 一、功能与架构

### 主要功能

- **多源采集**：同时从网站（RSS / 网页抓取）、微信公众号、X/Twitter 三类信源抓取内容
- **智能去重**：URL 去重 + 语义相似度去重，避免同一事件重复出现
- **大模型评分**：按内容质量和话题关联度打分排序，自动筛掉过时、低质、不相关的内容
- **报告生成**：对高分新闻生成中文标题、摘要、分类标签和战略建议，形成结构化简报
- **定时运行**：默认每天 8:00 自动跑一次，也可在网页上手动触发
- **网页界面**：报告浏览 + 信源/模型配置，采集进度通过 WebSocket 实时推送

### 技术栈

| 层 | 技术 |
|---|------|
| 后端 | Python + FastAPI + Uvicorn |
| 前端 | React 19 + Tailwind CSS 4 + Vite 7 |
| 数据库 | SQLite |
| 采集 | feedparser（RSS）+ Playwright + BeautifulSoup（网页/微信/X） |
| 去重 | sentence-transformers（paraphrase-multilingual-MiniLM-L12-v2） |
| 大模型 | 可切换 Claude / OpenAI 兼容接口 / Ollama |
| 调度 | APScheduler，默认每天 8:00 |

### 处理流程

```
采集 → 去重 → 评分排序 → 深度分析 → 生成报告
```

1. **采集**：并行读取所有网站信源（线程池，单源超时跳过）；微信公众号源串行采集（共享浏览器实例）；X 账号动态单独采集
2. **去重**：URL 哈希去重 + 语义相似度去重（余弦相似度 > 0.85）
3. **评分排序**：时效拦截（过滤过时新闻）→ 配置话题时按 embedding 语义过滤 → 大模型按质量与关联度打分 → 综合排序
4. **深度分析**：取分数最高的约 20 条做深度分析（每个信源最多 2 条），其余相关条目进入扫描层
5. **生成报告**：写入 SQLite，前端实时展示进度与结果

### 目录结构

```
ai-news-radar/
├── backend/
│   ├── main.py            # FastAPI 入口，API 路由 + 前端托管
│   ├── pipeline.py        # 主流程：采集→去重→评分→分析→报告
│   ├── scheduler.py       # APScheduler 定时任务
│   ├── scorer.py          # 评分排名
│   ├── analyzer.py        # 大模型分析（摘要 + 战略建议）
│   ├── deduplicator.py    # 去重
│   ├── collector/         # 采集器：rss / scraper / wechat / twitter
│   └── llm/               # 大模型抽象层：claude / openai / ollama
├── frontend/              # React 前端（构建产物在 dist/，由后端托管）
├── config.yaml            # 全局配置（信源 / 模型 / 话题 / 采集 / 调度）
├── config.example.yaml    # 配置示例
└── start.bat              # Windows 启动脚本
```

---

## 二、安装与启动

### 1. 环境准备（首次）

需要 Python 3.10+ 和 Node.js 18+。

```bash
# 后端依赖
pip install -r backend/requirements.txt
playwright install chromium

# 前端构建（产物输出到 frontend/dist，由后端直接托管）
cd frontend
npm install
npm run build
```

> **首次安装会联网下载较大文件，请保证网络通畅（必要时挂代理）：**
>
> | 内容 | 大小 | 触发时机 | 来源 |
> |---|---|---|---|
> | Chromium 浏览器 | 约 150 MB | 执行 `playwright install chromium` 时 | Playwright CDN |
> | 语义去重模型 `paraphrase-multilingual-MiniLM-L12-v2` | 约 470 MB（占盘约 900 MB） | **首次实际采集/去重时**（懒加载，非服务启动时下载） | HuggingFace |
>
> - 去重模型由 `sentence-transformers` 在第一次去重时自动下载，缓存到 `C:\Users\<用户名>\.cache\huggingface\`，下载一次后长期复用，之后离线也能跑。
> - HuggingFace 在国内访问不稳定：`start.bat` 注入的代理会自动作用于该下载；若不想走代理，可改用国内镜像 —— 启动前设置环境变量 `AINR_HF_ENDPOINT=https://hf-mirror.com`（详见「三、配置说明 › 启动脚本环境变量」）。

### 2. 准备配置文件

复制示例配置，按需修改：

```bash
copy config.example.yaml config.yaml
```

配置可以直接编辑 `config.yaml`，也可以先启动服务、再在网页「配置」页修改（详见第三节）。

### 3. 启动

双击运行 **`start.bat`**，脚本会：

- 在 `localhost:8000` 启动后端服务（前端已内置，无需单独启动）
- 自动打开浏览器访问 `http://localhost:8000`

启动后即可在网页上配置信源、触发采集、查看报告。关闭命令行窗口即停止服务。

> 接口文档：`http://localhost:8000/docs`

---

## 三、配置说明

所有配置集中在 `config.yaml`，网页「配置」页提供了对应的可视化编辑。

### 模型 API 配置

在「配置」页的 **LLM 配置** 区，或编辑 `config.yaml` 的 `llm` 段：

```yaml
llm:
  provider: openai          # claude / openai / ollama
  model: MiniMax-M2.7       # 模型名
  api_key: ''               # 留空则读环境变量
  base_url: https://api.minimaxi.com/v1   # 兼容接口地址，留空用默认
```

- **provider**：`claude`（Anthropic 官方）、`openai`（OpenAI 及一切 OpenAI 兼容接口，如 MiniMax、DeepSeek、智谱等）、`ollama`（本地模型）
- **api_key**：填入对应平台的密钥；留空则从环境变量读取
- **base_url**：使用第三方兼容接口时填写其地址；用官方接口可留空
- 配好后点「测试连通性」按钮，确认能正常调用模型

### 代理配置

海外信源（OpenAI、X 等）需要走代理访问，国内信源直连。

`config.yaml` 中的代理地址：

```yaml
sources:
  proxy_url: http://127.0.0.1:10809   # 改成你本地代理的地址和端口
  proxy_probe_timeout: 5              # 代理可达性探测超时（秒）
```

`start.bat` 也会注入 `HTTP_PROXY` / `HTTPS_PROXY` 环境变量，并把国内域名加入 `NO_PROXY` 白名单。这些值都支持用环境变量覆盖，无需改动脚本本身（详见下方「启动脚本环境变量」）。**如果你的代理端口不是 `10809`，请同时设置 `config.yaml` 的 `proxy_url` 和环境变量 `AINR_PROXY`。**

采集开始前系统会自动探测代理是否可达：**代理不通时，所有需要代理的海外信源（含 X）会被自动跳过**，国内信源照常采集，不会因此报错中断。

### 启动脚本环境变量

`start.bat` 的运行参数都支持用环境变量覆盖，**无需直接修改脚本**。启动前设置对应变量即可，未设置则用默认值：

| 变量 | 默认值 | 说明 |
|---|---|---|
| `AINR_PORT` | `8000` | 后端服务端口 |
| `AINR_PROXY` | `http://127.0.0.1:10809` | HTTP / HTTPS 代理地址 |
| `AINR_NO_PROXY` | 国内域名白名单 | 不走代理的域名列表 |
| `AINR_HF_ENDPOINT` | 空（用 HuggingFace 官方源） | 模型下载源；设为 `https://hf-mirror.com` 改用国内镜像 |

用法示例（在命令行中先设置再运行）：

```bat
set AINR_PORT=9000
set AINR_HF_ENDPOINT=https://hf-mirror.com
start.bat
```

脚本启动时会打印当前生效的端口、代理和 HF 源，便于核对。脚本工作目录基于自身位置（`%~dp0`），项目可整体移动到任意路径。

### 信源配置（三类）

信源分三类，配置项和准备工作各不相同：

#### ① 网站信源（RSS / 网页抓取）

配置位置：`config.yaml` 的 `sources.websites`，或网页「配置」页的「网站信源」区。

```yaml
sources:
  websites:
  - name: OpenAI Blog
    type: rss               # rss = 订阅源；scrape = 网页抓取
    url: https://openai.com/news/rss.xml
    use_proxy: true         # 海外源 true，国内源 false
  - name: 机器之心
    type: scrape
    url: https://jiqizhixin.com/
    selector: article a, h3 a   # scrape 类型需指定 CSS 选择器
    use_proxy: false
```

- **是否要代理**：由每条信源的 `use_proxy` 字段决定。海外站点设 `true`，国内站点设 `false`
- **登录**：不需要登录，开箱即用
- **type 为 `scrape`** 的信源必须指定 CSS `selector`；JS 渲染的站点会自动用浏览器渲染

#### ② 微信公众号

配置位置：`config.yaml` 的 `sources.wechat`，或网页「配置」页的「微信公众号」区。

```yaml
sources:
  wechat:
  - name: 量子位（公众号）
    nickname: 量子位          # 公众号昵称，用于后台搜索
    use_proxy: false
```

- **是否要代理**：**不需要**。微信公众号走国内接口（`mp.weixin.qq.com`），`use_proxy` 固定为 `false`
- **登录**：**需要扫码登录一次**。在网页「配置」→「微信公众号」区点 **「扫码登录」**，会弹出浏览器窗口，用手机微信扫码登录公众号后台，登录成功后手动关闭浏览器即可
- 登录凭证（session）会缓存到本地，后续采集复用，失效时再重新扫码

> 微信采集基于 Playwright + 微信公众号后台 API，需要一个能登录公众号后台的微信号。

#### ③ X / Twitter

配置位置：`config.yaml` 的 `sources.twitter`，或网页「配置」页的「X 账号」区。

```yaml
sources:
  twitter:
    enabled: true
    use_proxy: true           # X 必须走代理
    accounts:                 # 要监控的 X 账号
    - handle: OpenAI
      display_name: OpenAI 官方
    - handle: AnthropicAI
      display_name: Anthropic 官方
```

- **依赖**：X 采集依赖 `twscrape`，已包含在 `backend/requirements.txt`。若日志出现 `No module named 'twscrape'`，执行 `pip install -r backend/requirements.txt` 补装即可（`start.bat` 启动时也会自动探测并补装缺失依赖）
- **是否要代理**：**需要**。X 在国内无法直连，`use_proxy` 必须为 `true`，且代理须可用，否则采集会被自动跳过
- **登录**：**需要登录一个 X 账号**用于采集。在网页「配置」→「X 账号」区，有两种方式：
  - **浏览器登录**（推荐）：点「浏览器登录」，在弹出的浏览器窗口中手动登录 X.com，登录后系统自动保存 cookies 凭证
  - **账号密码**：点「+ 账号密码」，填入小号的用户名、密码、邮箱（及邮箱密码），由系统自动登录
- `accounts` 列表是「要监控哪些账号」，与「用哪个账号登录采集」是两回事——前者随便填想看的博主，后者是你自己的采集小号

---

## 四、运行与使用

配置完成后，日常使用只有两步：

1. **启动**：双击 `start.bat`，浏览器自动打开 `http://localhost:8000`
2. **采集**：在「报告」页侧边栏点 **「采集新闻」** 按钮，立即跑一轮采集与分析；进度会实时显示，完成后报告自动出现在侧边栏

此外：

- **定时任务**：`config.yaml` 的 `scheduler` 段默认 `cron: 0 8 * * *`（每天 8:00 自动采集），可在「配置」页开关或调整
- **历史报告**：左侧边栏列出全部历史报告，点击查看，可删除、可下载
- 修改前端代码后需重新 `cd frontend && npm run build`，后端托管 `dist/` 静态文件

---

## 五、相关文档

- 架构设计：`docs/plans/2026-03-11-ai-news-radar-design.md`
- 开发日志：`docs/devlog.md`
- 踩坑记录：`docs/pitfalls.md`
- 项目说明（给 AI 助手）：`CLAUDE.md`
