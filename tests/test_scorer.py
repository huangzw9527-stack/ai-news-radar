import os, sys, math
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from unittest.mock import MagicMock
from backend.scorer import Scorer, _hours_since

# ---------- 纯函数测试 ----------

def test_hours_since_recent():
    from datetime import datetime, timedelta, timezone
    recent = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    assert 1.5 < _hours_since(recent) < 2.5

def test_hours_since_old():
    assert _hours_since("2020-01-01T00:00:00") > 10000

def test_hours_since_none():
    assert _hours_since(None) > 10000
    assert _hours_since("") > 10000

# ---------- Scorer 集成测试（mock LLM + DB）----------

def _make_news(n=3, hours_ago=1, source="src"):
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    pub = (now - timedelta(hours=hours_ago)).isoformat()
    return [{
        "id": f"n{i:03d}", "title": f"AI大模型新闻{i}", "summary": f"某公司发布了新的大语言模型{i}",
        "full_text": "", "source_name": source, "source_tier": 1,
        "published_at": pub, "collected_at": pub,
    } for i in range(n)]

def _make_scorer(llm_resp=None):
    import json
    llm = MagicMock()
    db = MagicMock()
    if llm_resp:
        llm.chat.return_value = llm_resp
    else:
        def fake_chat(system, prompt):
            count = prompt.count("\n[")
            scores = {
                str(i+1): {
                    "relevance": 80,
                    "content": {"substantiality": 10, "density": 10, "originality": 10},
                    "main_category": "模型发布",
                }
                for i in range(max(count, 5))
            }
            return json.dumps({"scores": scores})
        llm.chat.side_effect = fake_chat
    return Scorer(llm=llm, topics=[], db=db)

def test_time_gate_filters_old_news():
    scorer = _make_scorer()
    old_news = _make_news(2, hours_ago=100)
    result = scorer.score_and_rank(old_news)
    assert result == []
    scorer.llm.chat.assert_not_called()

def test_score_and_rank_returns_all_sorted():
    """无话题配置时不截断、不做同源限制：返回全部候选，按 score 降序。

    同源限制/Top-N 已移至 pipeline.select_deep_news（见 test_selection.py）。
    """
    scorer = _make_scorer()
    news = _make_news(5, hours_ago=1)
    result = scorer.score_and_rank(news)
    assert len(result) == 5
    scores = [r["score"] for r in result]
    assert scores == sorted(scores, reverse=True)
