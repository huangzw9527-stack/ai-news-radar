import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from backend.deduplicator import Deduplicator

def make_news(id_, url, title, score=50.0, tier=1):
    return {"id": id_, "url": url, "title": title, "summary": title,
            "score": score, "source_tier": tier, "published_at": "2026-03-11T08:00:00"}

def test_url_dedup_removes_duplicate():
    dedup = Deduplicator(semantic_threshold=0.85)
    news_list = [
        make_news("a1", "https://example.com/1", "GPT-5发布"),
        make_news("a1", "https://example.com/1", "GPT-5发布"),  # 同URL同ID
    ]
    result = dedup.deduplicate(news_list, existing_ids=set())
    assert len(result) == 1

def test_existing_id_filtered():
    dedup = Deduplicator(semantic_threshold=0.85)
    news_list = [make_news("a1", "https://example.com/1", "GPT-5发布")]
    result = dedup.deduplicate(news_list, existing_ids={"a1"})
    assert len(result) == 0

def test_semantic_dedup_removes_similar():
    dedup = Deduplicator(semantic_threshold=0.85)
    news_list = [
        make_news("a1", "https://example.com/1", "OpenAI发布GPT-5模型，推理能力大幅提升", score=80),
        make_news("a2", "https://example.com/2", "OpenAI推出GPT-5，推理性能显著提高", score=60),
        make_news("a3", "https://example.com/3", "DeepSeek发布新模型R2，超越GPT-4", score=70),
    ]
    result = dedup.deduplicate(news_list, existing_ids=set())
    # a1和a2语义相似，保留分数高的a1；a3不同，保留
    assert len(result) == 2
    ids = {r["id"] for r in result}
    assert "a1" in ids
    assert "a3" in ids


def test_stopwords_excluded_from_distinctive_tokens():
    """ai / the 这类常见词不应计入区分性 token。"""
    from backend.deduplicator import _distinctive_tokens
    tokens = _distinctive_tokens("New AI feature is the future of OpenAI GPT-5")
    assert "openai" in tokens
    assert "gpt-5" in tokens
    assert "ai" not in tokens
    assert "the" not in tokens
    assert "new" not in tokens
    assert "is" not in tokens


def test_is_duplicate_three_tier_thresholds():
    """_is_duplicate 三档判定：sim≥0.85 / sim≥0.70+shared≥2 / sim≥0.55+shared≥4。"""
    dedup = Deduplicator()
    many = {"karpathy", "claude.md", "github", "65", "94"}
    # 第三档：低 sim + 高 token 共享 → 同
    assert dedup._is_duplicate(0.60, many, many) is True
    # 第三档下限：sim 太低不判同（避免误删）
    assert dedup._is_duplicate(0.50, many, many) is False
    # 第二档：中 sim + 共享 2 个 → 同
    assert dedup._is_duplicate(0.75, {"gpt-5", "openai"}, {"gpt-5", "openai"}) is True
    # 第二档：中 sim + 只共享 1 个 → 不同
    assert dedup._is_duplicate(0.75, {"gpt-5"}, {"gpt-5"}) is False
    # 第三档：中-低 sim + 共享只有 3 个 → 不同（4 是下限）
    three = {"karpathy", "claude.md", "github"}
    assert dedup._is_duplicate(0.60, three, three) is False
    # 高 sim 直接判同，token 不参与
    assert dedup._is_duplicate(0.90, set(), set()) is True
