import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from backend.collector.twitter import _normalize

_BASE = {
    "url": "https://x.com/OpenAI/status/123",
    "rawContent": "OpenAI releases GPT-5 with major improvements in reasoning and coding ability. This is a significant advancement in AI.",
    "date": "2026-05-15T08:00:00+00:00",
    "retweetCount": 1000,
    "likeCount": 3000,
    "replyCount": 500,
}

def test_normalize_basic():
    item = _normalize(_BASE, "OpenAI 官方", "OpenAI", date_window_days=7)
    assert item is not None
    assert item["url"] == "https://x.com/OpenAI/status/123"
    assert item["source_name"] == "OpenAI 官方 (@OpenAI)"
    assert item["interaction_count"] == 4500
    assert item["source_tier"] == 2
    assert item["indicator"] == "twitter"
    assert len(item["title"]) <= 80

def test_normalize_filters_empty_url():
    raw = {**_BASE, "url": ""}
    assert _normalize(raw, "OpenAI 官方", "OpenAI", date_window_days=7) is None

def test_normalize_filters_empty_content():
    raw = {**_BASE, "rawContent": ""}
    assert _normalize(raw, "OpenAI 官方", "OpenAI", date_window_days=7) is None

def test_normalize_filters_old_tweet():
    raw = {**_BASE, "date": "2020-01-01T00:00:00+00:00"}
    assert _normalize(raw, "OpenAI 官方", "OpenAI", date_window_days=7) is None

def test_normalize_interaction_count_zero_on_missing():
    raw = {**_BASE}
    raw.pop("retweetCount")
    raw.pop("likeCount")
    raw.pop("replyCount")
    item = _normalize(raw, "OpenAI 官方", "OpenAI", date_window_days=7)
    assert item is not None
    assert item["interaction_count"] == 0

def test_normalize_filters_non_ai_content():
    raw = {**_BASE, "rawContent": "Just had a great lunch today, loving the weather."}
    assert _normalize(raw, "OpenAI 官方", "OpenAI", date_window_days=7) is None
