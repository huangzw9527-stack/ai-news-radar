"""X/Twitter 采集健壮性测试：twscrape 缺失降级 + 代理解析 + API 端点提示。"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---- twscrape_available / TWSCRAPE_MISSING_MSG ----

def test_twscrape_available_returns_true_when_installed():
    # twscrape 已在 backend/requirements.txt 声明，测试环境应已安装
    from backend.collector.twitter_auth import twscrape_available
    assert twscrape_available() is True


def test_twscrape_missing_msg_is_actionable():
    from backend.collector.twitter_auth import TWSCRAPE_MISSING_MSG
    assert "twscrape" in TWSCRAPE_MISSING_MSG
    assert "pip install" in TWSCRAPE_MISSING_MSG


# ---- _resolve_proxy ----

def test_resolve_proxy_empty_when_proxy_disabled():
    from backend.collector.twitter import _resolve_proxy
    assert _resolve_proxy({"use_proxy": False}, "http://127.0.0.1:10809") == ""


def test_resolve_proxy_prefers_explicit_twitter_proxy():
    from backend.collector.twitter import _resolve_proxy
    assert _resolve_proxy({"use_proxy": True, "proxy": "http://a:1"}, "http://b:2") == "http://a:1"


def test_resolve_proxy_falls_back_to_global_proxy_url():
    from backend.collector.twitter import _resolve_proxy
    assert _resolve_proxy({"use_proxy": True}, "http://b:2") == "http://b:2"


def test_resolve_proxy_falls_back_to_env(monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "http://env:3")
    from backend.collector.twitter import _resolve_proxy
    assert _resolve_proxy({"use_proxy": True}, "") == "http://env:3"


# ---- collect_all 降级与代理注入 ----

def test_collect_all_skips_when_twscrape_missing(monkeypatch, capsys):
    from backend.collector import twitter, twitter_auth

    monkeypatch.setattr(twitter_auth, "twscrape_available", lambda: False)
    called = []
    monkeypatch.setattr(twitter.subprocess, "run", lambda *a, **k: called.append(True))

    collector = twitter.TwitterCollector()
    result = collector.collect_all({"enabled": True, "accounts": [{"handle": "OpenAI"}]})

    assert result == []
    assert called == []  # twscrape 缺失时不应启动采集子进程
    out = capsys.readouterr().out
    assert "twscrape" in out and "pip install" in out


def test_collect_all_injects_resolved_proxy(monkeypatch):
    from backend.collector import twitter, twitter_auth

    monkeypatch.setattr(twitter_auth, "twscrape_available", lambda: True)
    monkeypatch.setattr(twitter_auth, "has_accounts", lambda: True)
    monkeypatch.setattr(twitter_auth, "has_browser_session", lambda: False)

    captured = {}

    def fake_run(*args, **kwargs):
        captured["env"] = kwargs.get("env", {})
        raise RuntimeError("stop after capturing env")

    monkeypatch.setattr(twitter.subprocess, "run", fake_run)

    collector = twitter.TwitterCollector()
    collector.collect_all(
        {"enabled": True, "use_proxy": True, "accounts": [{"handle": "x"}]},
        proxy_url="http://proxy:9",
    )

    assert captured["env"].get("TWS_PROXY") == "http://proxy:9"


# ---- API 端点：twscrape 缺失时返回清晰提示 ----

def _twitter_client():
    from backend.main import app
    from fastapi.testclient import TestClient
    return TestClient(app)


def test_status_endpoint_reports_unavailable_without_twscrape(monkeypatch):
    from backend.collector import twitter_auth
    monkeypatch.setattr(twitter_auth, "twscrape_available", lambda: False)
    resp = _twitter_client().get("/api/twitter/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "unavailable"
    assert "pip install" in body["message"]


def test_add_account_endpoint_rejected_without_twscrape(monkeypatch):
    from backend.collector import twitter_auth
    monkeypatch.setattr(twitter_auth, "twscrape_available", lambda: False)
    resp = _twitter_client().post("/api/twitter/add-account", json={})
    assert resp.status_code == 400
    assert "twscrape" in resp.json()["message"]


def test_login_endpoint_rejected_without_twscrape(monkeypatch):
    from backend.collector import twitter_auth
    monkeypatch.setattr(twitter_auth, "twscrape_available", lambda: False)
    # 守卫缺失时本会启动真实浏览器子进程，桩函数兜底保证测试不弹窗
    monkeypatch.setattr(twitter_auth, "browser_login_and_save", lambda: None)
    resp = _twitter_client().post("/api/twitter/login")
    assert resp.status_code == 400
    assert "twscrape" in resp.json()["message"]


def test_collect_endpoint_rejected_without_twscrape(monkeypatch):
    from backend.collector import twitter_auth
    monkeypatch.setattr(twitter_auth, "twscrape_available", lambda: False)
    resp = _twitter_client().post("/api/twitter/collect")
    assert resp.status_code == 400
    body = resp.json()
    assert body["status"] == "error"
    assert "twscrape" in body["message"]
