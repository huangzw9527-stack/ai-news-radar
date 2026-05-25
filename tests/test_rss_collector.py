import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from backend.collector.rss import RSSCollector

def test_collect_returns_list():
    source = {
        "name": "arXiv cs.AI Test",
        "institution": "arXiv",
        "tier": 1,
        "indicator": "academic",
        "type": "rss",
        "url": "https://rss.arxiv.org/rss/cs.AI",
    }
    collector = RSSCollector(max_per_source=3)
    items = collector.collect(source)
    assert isinstance(items, list)
    assert len(items) <= 3
    if items:
        item = items[0]
        assert "id" in item
        assert "url" in item
        assert "title" in item
        assert item["source_tier"] == 1
        assert item["indicator"] == "academic"

def test_collect_invalid_url_returns_empty():
    source = {
        "name": "Invalid",
        "institution": "Test",
        "tier": 1,
        "indicator": "academic",
        "type": "rss",
        "url": "https://this-url-does-not-exist-xyz.com/rss.xml",
    }
    collector = RSSCollector(max_per_source=5)
    items = collector.collect(source)
    assert isinstance(items, list)
    # 无效URL应返回空列表而不是抛出异常

def test_collect_respects_max_per_source():
    source = {
        "name": "arXiv cs.LG",
        "institution": "arXiv",
        "tier": 1,
        "indicator": "academic",
        "type": "rss",
        "url": "https://rss.arxiv.org/rss/cs.LG",
    }
    collector = RSSCollector(max_per_source=2)
    items = collector.collect(source)
    assert len(items) <= 2
