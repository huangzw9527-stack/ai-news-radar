# Twitter / X 账号动态监控设计

**日期**：2026-05-15  
**状态**：待实施

## 背景

在现有 RSS、网页抓取、微信公众号三套采集器基础上，新增 X（Twitter）账号动态监控，不使用官方 API，通过 `twscrape` 库实现。

## 目标

- 监控指定 AI 公司官号和研究者/KOL 个人账号
- 获取推文全文、链接、转推/点赞/回复互动数据
- 拟人化频率控制，降低封号风险
- 与现有采集 → 去重 → 排名 → LLM 流程无缝集成

## 新增文件结构

```
backend/collector/
├── twitter.py        # TwitterCollector 主采集器
└── twitter_auth.py   # 凭证管理（参照 wechat_auth.py 模式）

data/
└── twitter_accounts.json  # twscrape 账号池文件（自动维护）
```

## 拟人化频率控制策略

三层随机延迟，所有账号串行（不并发）抓取：

| 层级 | 说明 | 默认范围 |
|------|------|----------|
| 推文间隔 | 同一账号内每条推文之间 | 1–3 秒随机 |
| 账号间隔 | 切换到下一个账号之前 | 8–20 秒随机 |
| 全局限额 | 单次运行最多抓取推文总数 | 150 条上限 |

账号顺序每次随机打乱，避免固定访问模式。

## config.yaml 新增字段

```yaml
sources:
  twitter:
    enabled: true
    max_tweets_per_account: 10
    fetch_delay_min: 8
    fetch_delay_max: 20
    tweet_delay_min: 1
    tweet_delay_max: 3
    max_total_tweets: 150
    accounts:
      # AI 公司官号
      - { handle: OpenAI,         display_name: OpenAI 官方 }
      - { handle: AnthropicAI,    display_name: Anthropic 官方 }
      - { handle: GoogleDeepMind, display_name: Google DeepMind }
      # 国际研究者
      - { handle: ylecun,         display_name: Yann LeCun }
      - { handle: karpathy,       display_name: Andrej Karpathy }
      # 中文 KOL
      - { handle: vista8,         display_name: 向阳乔木 }
      - { handle: dotey,          display_name: 宝玉 }
      - { handle: AYi_AInotes,    display_name: AYi }
      - { handle: servasyy_ai,    display_name: huangserva }
      - { handle: berryxia,       display_name: berryxia }
      - { handle: AlchainHust,    display_name: 花叔 }
```

## 采集结果数据格式

```python
{
    "title": "推文前 80 字...",
    "url": "https://x.com/{handle}/status/{tweet_id}",
    "content": "推文全文",
    "source": "{display_name} (@{handle})",
    "source_type": "twitter",
    "published": "2026-05-15T10:30:00Z",
    "interaction_count": 3420,   # retweets + likes + replies
    "author_handle": "{handle}",
}
```

## 核心模块设计

### twitter_auth.py

- 封装 `twscrape.AccountsPool`，凭证持久化到 `data/twitter_accounts.json`
- 提供 `add_account(username, password, email)` 和 `get_pool()` 两个接口
- 通过 `POST /api/twitter/add-account` 在前端配置页添加 X 小号

### twitter.py

```python
class TwitterCollector:
    async def collect_all(self, accounts, cfg) -> list[dict]:
        # 随机打乱账号顺序
        # 串行遍历，账号间随机延迟 fetch_delay_min ~ fetch_delay_max 秒
        # 达到 max_total_tweets 上限时停止

    async def _collect_one(self, api, acct, cfg) -> list[dict]:
        # 抓取单个账号，推文间随机延迟 tweet_delay_min ~ tweet_delay_max 秒
        # 过滤纯转推（无评论）、过滤超出 date_window_days 的旧推文
        # 调用 is_ai_related() 做关键词过滤
```

## Ranker 评分集成

`interaction_count` 映射到现有「传播力」维度，无需新增评分维度：

```python
# ranker.py 传播力评分新增 twitter 分支
if item.get("source_type") == "twitter":
    score = min(item.get("interaction_count", 0) / 1000, 10)
```

## 前端配置页

在「信源管理」区域新增 Twitter 分区：
- 账号列表增删（调用现有 `PUT /api/config`）
- X 小号凭证管理入口（调用 `POST /api/twitter/add-account`）

## 完整数据流

```
config.yaml twitter.accounts
        ↓
TwitterCollector.collect_all()   ← 串行 + 随机延迟
        ↓
pipeline.py 合并（RSS + 网页 + Twitter）
        ↓
去重 → Ranker（interaction_count → 传播力）→ LLM 分析
        ↓
前端 NewsCard（source_type=twitter 显示 @handle）
```

## 风险与注意事项

- **账号安全**：使用专用小号，不用主账号；凭证文件加入 `.gitignore`
- **限速处理**：twscrape 遇到 rate limit 时自动等待，无需额外处理
- **纯转推过滤**：无评论的转推信息量低，默认过滤
- **日期窗口**：复用现有 `date_window_days` 配置，只取近期推文
