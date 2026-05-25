"""配置相关的纯函数工具（无重依赖，便于单测）。"""
import socket
from typing import Any, Dict, Optional
from urllib.parse import urlparse

_DEFAULT_PROXY_URL = "http://127.0.0.1:10809"

# 国内站名单，复用 start.bat NO_PROXY；命中则 use_proxy 智能默认为 False。
_DOMESTIC_DOMAINS = (
    "zhipuai.cn", "deepseek.com", "qbitai.com", "jiqizhixin.com",
    "latepost.com", "infoq.cn", "36kr.com", "xinzhiyuan.com",
    "tmtpost.com", "aibase.com",
)


def _topic_is_empty(topic: Any) -> bool:
    if not isinstance(topic, dict):
        return True
    name = (topic.get("name") or "").strip()
    desc = (topic.get("description") or "").strip()
    keywords = [k for k in (topic.get("keywords") or []) if str(k).strip()]
    return not name and not desc and not keywords


def drop_empty_topics(topics: Any) -> Any:
    """剔除「名称/描述/关键词」全为空的话题卡片。

    非 list 输入原样返回（交由调用方处理类型）。
    """
    if not isinstance(topics, list):
        return topics
    return [t for t in topics if not _topic_is_empty(t)]


def effective_proxies(use_proxy: bool, proxy_url: str) -> Dict[str, Optional[str]]:
    """返回 requests 风格 proxies。

    use_proxy=False 时显式置 None，使 requests 忽略环境变量代理。
    """
    if use_proxy:
        return {"http": proxy_url, "https": proxy_url}
    return {"http": None, "https": None}


def probe_proxy(proxy_url: str, timeout: float = 5.0) -> bool:
    """TCP 探测代理端口是否可达。

    proxy_url 为空 / 解析失败 / 连接失败均返回 False。
    使用裸 socket，不会自身经过 HTTP_PROXY 环境变量。
    """
    if not proxy_url:
        return False
    try:
        parsed = urlparse(proxy_url)
        host = parsed.hostname
        port = parsed.port
        if not host or not port:
            return False
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (OSError, ValueError):
        return False


def _is_domestic(url: str) -> bool:
    host = (urlparse(url or "").hostname or "").lower()
    if not host:
        return False
    return any(host == d or host.endswith("." + d) for d in _DOMESTIC_DOMAINS)


def normalize_proxy_config(cfg: Dict) -> Dict:
    """幂等迁移代理配置：全局 proxy_url + 每源 use_proxy。

    - sources.proxy_url 缺失 → 取旧 twitter.proxy，再无则默认值
    - website 源缺 use_proxy → 智能默认（国内站 False，其余 True）
    - twitter 缺 use_proxy → 由旧 proxy 推导，默认 True；旧 proxy 键移除
    - wechat 源缺 use_proxy → False
    """
    sources = cfg.setdefault("sources", {})
    twitter = sources.get("twitter")

    if not sources.get("proxy_url"):
        tw_proxy = twitter.get("proxy") if isinstance(twitter, dict) else None
        sources["proxy_url"] = tw_proxy or _DEFAULT_PROXY_URL

    for w in sources.get("websites") or []:
        if isinstance(w, dict) and "use_proxy" not in w:
            w["use_proxy"] = not _is_domestic(w.get("url", ""))

    for w in sources.get("wechat") or []:
        if isinstance(w, dict) and "use_proxy" not in w:
            w["use_proxy"] = False

    if isinstance(twitter, dict):
        if "use_proxy" not in twitter:
            twitter["use_proxy"] = (
                bool(twitter.get("proxy")) if "proxy" in twitter else True
            )
        twitter.pop("proxy", None)

    return cfg
