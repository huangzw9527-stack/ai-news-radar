import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from backend.db import Database

def test_insert_and_query_news():
    db = Database(":memory:")
    db.init()
    news = {
        "id": "abc123",
        "url": "https://example.com/news/1",
        "title": "GPT-5发布",
        "summary": "OpenAI发布GPT-5",
        "full_text": "全文内容",
        "source_name": "OpenAI Research",
        "source_tier": 1,
        "institution": "OpenAI",
        "indicator": "academic",
        "score": 0.0,
        "published_at": "2026-03-11T08:00:00",
        "collected_at": "2026-03-11T09:00:00",
    }
    db.upsert_news(news)
    results = db.get_recent_news(limit=10)
    assert len(results) == 1
    assert results[0]["title"] == "GPT-5发布"

def test_url_dedup():
    db = Database(":memory:")
    db.init()
    news = {"id": "abc123", "url": "https://example.com/1", "title": "T",
            "summary": "", "full_text": "", "source_name": "X", "source_tier": 1,
            "institution": "X", "indicator": "academic", "score": 0.0,
            "published_at": "2026-03-11T08:00:00", "collected_at": "2026-03-11T09:00:00"}
    db.upsert_news(news)
    db.upsert_news(news)  # 重复插入
    assert len(db.get_recent_news(limit=10)) == 1

def test_save_and_get_report():
    db = Database(":memory:")
    db.init()
    report = {
        "id": "r001",
        "created_at": "2026-03-11T09:00:00",
        "trigger": "manual",
        "top10_ids": '["abc123"]',
        "opportunities": '{}',
        "signals": '[]',
        "llm_provider": "claude",
        "llm_model": "claude-sonnet-4-6",
    }
    db.save_report(report)
    reports = db.get_reports(limit=5)
    assert len(reports) == 1
    assert reports[0]["trigger"] == "manual"


def test_get_news_by_date():
    db = Database(":memory:")
    db.init()
    news_yesterday = {
        "id": "y001",
        "url": "https://example.com/yesterday",
        "title": "Yesterday News",
        "summary": "",
        "full_text": "",
        "source_name": "X",
        "source_tier": 1,
        "institution": "X",
        "indicator": "academic",
        "score": 0.0,
        "published_at": "2026-03-19T08:00:00+00:00",
        "collected_at": "2026-03-19T09:00:00+00:00",
    }
    news_today = {
        "id": "t001",
        "url": "https://example.com/today",
        "title": "Today News",
        "summary": "",
        "full_text": "",
        "source_name": "X",
        "source_tier": 1,
        "institution": "X",
        "indicator": "academic",
        "score": 0.0,
        "published_at": "2026-03-20T08:00:00+00:00",
        "collected_at": "2026-03-20T09:00:00+00:00",
    }
    db.upsert_news(news_yesterday)
    db.upsert_news(news_today)

    results = db.get_news_by_date("2026-03-19", limit=10)
    assert len(results) == 1
    assert results[0]["id"] == "y001"


def test_upsert_news_with_interaction_count():
    from backend.db import Database
    db = Database(":memory:")
    db.init()
    news = {
        "id": "tw_test_001",
        "url": "https://x.com/OpenAI/status/123",
        "title": "Test tweet",
        "summary": "",
        "full_text": "Test tweet full text",
        "source_name": "OpenAI 官方 (@OpenAI)",
        "source_tier": 1,
        "institution": "OpenAI",
        "indicator": "academic",
        "score": 0.0,
        "published_at": "2026-05-15T10:00:00+00:00",
        "collected_at": "2026-05-15T10:00:00+00:00",
        "interaction_count": 5000,
    }
    db.upsert_news(news)
    rows = db._conn().execute("SELECT interaction_count FROM news WHERE id='tw_test_001'").fetchall()
    assert rows[0][0] == 5000


def test_upsert_news_defaults_interaction_count_to_zero():
    from backend.db import Database
    db = Database(":memory:")
    db.init()
    news = {
        "id": "legacy_001",
        "url": "https://example.com/legacy",
        "title": "Legacy",
        "summary": "", "full_text": "",
        "source_name": "RSS", "source_tier": 2,
        "institution": "X", "indicator": "academic",
        "score": 0.0,
        "published_at": "2026-05-01T10:00:00+00:00",
        "collected_at": "2026-05-01T10:00:00+00:00",
    }
    db.upsert_news(news)
    rows = db._conn().execute("SELECT interaction_count FROM news WHERE id='legacy_001'").fetchall()
    assert rows[0][0] == 0
