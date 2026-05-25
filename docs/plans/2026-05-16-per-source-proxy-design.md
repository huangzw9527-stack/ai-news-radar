# 按信源代理 + 配置页吸底保存/Toast 设计

日期：2026-05-16
状态：已确认，待实现

## 背景

环境为大陆网络，单一 V2Ray 出口 `127.0.0.1:10809`。当前代理靠 `start.bat`
全局注入 `HTTP(S)_PROXY` + `NO_PROXY` 国内白名单；Twitter 另有独立
`sources.twitter.proxy` 字段。需求：

1. 把"代理地址"做成配置项，并让**每个信源**可独立决定是否走代理。
2. 配置页保存按钮吸底常驻；保存成功/失败弹 toast。

## 决策（已确认）

- 代理模型：**全局一个 `proxy_url` + 每源 `use_proxy` 布尔开关**。
- 覆盖范围：**所有采集源**——websites、Twitter（并入该模型，弃用独立
  `proxy` 字段）、wechat（默认关）。
- 迁移默认：**智能默认**——海外源 `use_proxy=true`，国内源 `false`。

## ① 配置 schema + 迁移

```yaml
sources:
  proxy_url: http://127.0.0.1:10809
  websites:
    - { name: ..., url: ..., type: rss|scrape, ..., use_proxy: true }
  wechat:
    - { ..., use_proxy: false }
  twitter:
    use_proxy: true            # 取代旧 proxy: <addr>
```

`backend/config_utils.py` 新增纯函数 `normalize_proxy_config(cfg) -> cfg`
（读时调用，幂等，TDD）：

- `sources.proxy_url` 缺失 → 取旧 `sources.twitter.proxy`，再无则
  `http://127.0.0.1:10809`。
- website 源缺 `use_proxy` → 智能默认：URL host 命中国内名单则 `false`，
  否则 `true`。国内名单复用 start.bat NO_PROXY：
  `zhipuai.cn, deepseek.com, qbitai.com, jiqizhixin.com, latepost.com,
  infoq.cn, 36kr.com, xinzhiyuan.com, tmtpost.com, aibase.com`
  （后缀匹配 hostname）。
- twitter 缺 `use_proxy` → 由旧 `proxy` 推导 `bool(proxy)`，默认 `true`；
  旧 `proxy` 值并入 `proxy_url`（若全局为空）后移除该键。
- wechat 源缺 `use_proxy` → `false`。

在 `main.get_config()` 与 `pipeline.load_config()` 读后调用；幂等，
用户下次保存即落盘，不做破坏性自动改写。

## ② 采集器接入（每源开关为唯一权威，覆盖环境变量）

纯函数 `effective_proxies(use_proxy, proxy_url)`（config_utils，TDD）返回
requests 风格 dict：on → `{'http':p,'https':p}`，off → `{'http':None,'https':None}`。

- RSS（feedparser/urllib）：`feedparser.parse(url, handlers=[ProxyHandler(...)])`，
  on 用 `{'http':p,'https':p}`，off 用 `ProxyHandler({})` 显式屏蔽环境代理。
- Scrape 静态（requests）：`session.get(url, proxies=effective_proxies(...))`。
- Scrape 动态（Playwright 子进程）：on 传 `--proxy-server=<proxy_url>`，off 不传。
- Twitter 子进程：`TWS_PROXY = proxy_url if use_proxy else ''`。
- 微信（Playwright）：同动态抓取，按 `use_proxy` 传/不传 `--proxy-server`。

接线：`Pipeline.__init__` 读 `sources.proxy_url` 传入采集器；采集时按
`source.get('use_proxy', False)` 决定有效代理。`start.bat` 不改（LLM 仍可
能需环境代理；采集器现自带显式控制，不受影响）。

## ③ 前端 ConfigPage + 功能 2

- 「网站信源」顶部加全局 `代理地址` 输入（绑定 `sources.proxy_url`）+ 说明。
- 每源"走代理" checkbox：`SourcesSection`（表单 + 表格列，`EMPTY_SOURCE`
  加 `use_proxy:true`）、`WechatSourcesTable`（列，默认 false）、
  `TwitterSection`（原 proxy 输入改为绑定 `twitter.use_proxy` 的 checkbox）。
- 吸底保存：保存按钮移出滚动流，放入 `sticky bottom-0` 页脚条
  （半透明白底 + 上边框 + 阴影，宽度对齐 `max-w-2xl`）。
- Toast：极简自研组件（无第三方库，3s 自动消失）。`save()` 成功 → 绿色
  「配置已保存」；失败补 `catch` → 红色「保存失败：<msg>」。

## 测试

- `normalize_proxy_config`、`effective_proxies`：TDD（`tests/test_proxy_config.py`，
  RED→GREEN）。
- 现有套件不回归（注意：本仓库 HEAD 为重构中快照，HEAD 自身有 2 个与本次
  无关的 red，见记忆 repo-midrefactor-wip）。
- 前端改完 `cd frontend && npm run build`。

## 提交

设计文档 + 实现按既有"scoped 提交"方式：仅提交本次改动，对与未提交 WIP
混合的文件（如 ConfigPage.jsx、config.yaml）用 checkout→重放→add→还原
切出我们的 hunk。
