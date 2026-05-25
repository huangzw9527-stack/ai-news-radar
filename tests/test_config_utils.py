import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.config_utils import drop_empty_topics


def test_removes_fully_blank_topic():
    topics = [{"name": "", "description": "", "keywords": []}]
    assert drop_empty_topics(topics) == []


def test_keeps_topic_with_only_name():
    topics = [{"name": "大模型竞争格局", "description": "", "keywords": []}]
    assert drop_empty_topics(topics) == topics


def test_keeps_topic_with_only_keywords():
    topics = [{"name": "", "description": "", "keywords": ["GPT-5"]}]
    assert drop_empty_topics(topics) == topics


def test_whitespace_only_fields_count_as_empty():
    topics = [{"name": "  ", "description": "\n\t", "keywords": ["   ", ""]}]
    assert drop_empty_topics(topics) == []


def test_missing_keys_treated_as_empty():
    assert drop_empty_topics([{}]) == []


def test_mixed_keeps_only_meaningful_topics():
    topics = [
        {"name": "有效话题", "description": "描述", "keywords": ["AI"]},
        {"name": "", "description": "", "keywords": []},
        {"name": "", "description": "只有描述", "keywords": []},
    ]
    assert drop_empty_topics(topics) == [
        {"name": "有效话题", "description": "描述", "keywords": ["AI"]},
        {"name": "", "description": "只有描述", "keywords": []},
    ]


def test_non_list_returned_unchanged():
    assert drop_empty_topics(None) is None
    assert drop_empty_topics("not a list") == "not a list"
