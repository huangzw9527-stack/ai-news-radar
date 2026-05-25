import copy
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.config_utils import effective_proxies, normalize_proxy_config


# ---------------- effective_proxies ----------------

def test_effective_proxies_on():
    assert effective_proxies(True, "http://127.0.0.1:10809") == {
        "http": "http://127.0.0.1:10809",
        "https": "http://127.0.0.1:10809",
    }


def test_effective_proxies_off_explicitly_disables_env():
    # None values make requests ignore ambient HTTP(S)_PROXY env vars
    assert effective_proxies(False, "http://127.0.0.1:10809") == {
        "http": None,
        "https": None,
    }


# ---------------- normalize_proxy_config: proxy_url ----------------

def test_proxy_url_default_when_absent():
    cfg = {"sources": {"websites": []}}
    normalize_proxy_config(cfg)
    assert cfg["sources"]["proxy_url"] == "http://127.0.0.1:10809"


def test_proxy_url_migrated_from_twitter_proxy():
    cfg = {"sources": {"twitter": {"proxy": "http://10.0.0.1:7890", "accounts": []}}}
    normalize_proxy_config(cfg)
    assert cfg["sources"]["proxy_url"] == "http://10.0.0.1:7890"
    assert "proxy" not in cfg["sources"]["twitter"]


def test_existing_proxy_url_preserved():
    cfg = {"sources": {"proxy_url": "http://keep:1", "twitter": {"proxy": "http://x:2"}}}
    normalize_proxy_config(cfg)
    assert cfg["sources"]["proxy_url"] == "http://keep:1"


# ---------------- normalize_proxy_config: website smart default ----------------

def test_website_overseas_defaults_use_proxy_true():
    cfg = {"sources": {"websites": [{"name": "OpenAI", "url": "https://openai.com/news/rss.xml"}]}}
    normalize_proxy_config(cfg)
    assert cfg["sources"]["websites"][0]["use_proxy"] is True


def test_website_domestic_defaults_use_proxy_false():
    cfg = {"sources": {"websites": [
        {"name": "zhipu", "url": "https://www.zhipuai.cn/zh/research"},
        {"name": "deepseek", "url": "https://deepseek.com"},
        {"name": "36kr-sub", "url": "https://36kr.com/feed"},
    ]}}
    normalize_proxy_config(cfg)
    assert [w["use_proxy"] for w in cfg["sources"]["websites"]] == [False, False, False]


def test_explicit_use_proxy_is_preserved():
    cfg = {"sources": {"websites": [
        {"name": "OpenAI", "url": "https://openai.com", "use_proxy": False},
    ]}}
    normalize_proxy_config(cfg)
    assert cfg["sources"]["websites"][0]["use_proxy"] is False


# ---------------- normalize_proxy_config: twitter / wechat ----------------

def test_twitter_use_proxy_derived_from_old_proxy():
    cfg = {"sources": {"twitter": {"proxy": "http://p:1"}}}
    normalize_proxy_config(cfg)
    assert cfg["sources"]["twitter"]["use_proxy"] is True


def test_twitter_use_proxy_false_when_old_proxy_empty():
    cfg = {"sources": {"proxy_url": "http://g:1", "twitter": {"proxy": ""}}}
    normalize_proxy_config(cfg)
    assert cfg["sources"]["twitter"]["use_proxy"] is False


def test_twitter_use_proxy_default_true_when_no_proxy_key():
    cfg = {"sources": {"twitter": {"accounts": []}}}
    normalize_proxy_config(cfg)
    assert cfg["sources"]["twitter"]["use_proxy"] is True


def test_wechat_use_proxy_defaults_false():
    cfg = {"sources": {"wechat": [{"name": "x", "nickname": "y"}]}}
    normalize_proxy_config(cfg)
    assert cfg["sources"]["wechat"][0]["use_proxy"] is False


# ---------------- idempotency ----------------

def test_normalize_is_idempotent():
    cfg = {"sources": {
        "twitter": {"proxy": "http://p:1", "accounts": []},
        "websites": [{"name": "a", "url": "https://openai.com"},
                     {"name": "b", "url": "https://deepseek.com"}],
        "wechat": [{"name": "w", "nickname": "n"}],
    }}
    once = normalize_proxy_config(copy.deepcopy(cfg))
    twice = normalize_proxy_config(copy.deepcopy(once))
    assert once == twice


def test_no_sources_key_is_safe():
    cfg = {}
    normalize_proxy_config(cfg)
    assert cfg["sources"]["proxy_url"] == "http://127.0.0.1:10809"
