import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.selection import select_deep_news


def _news(i, source):
    return {"id": f"n{i}", "source_name": source, "score": 100 - i}


def test_source_cap_limits_same_source():
    """同源最多 source_cap 条，多出的留给扫描层。"""
    items = [_news(i, "same_source") for i in range(5)]
    deep = select_deep_news(items, deep_n=20, source_cap=2)
    assert len(deep) == 2
    assert [n["id"] for n in deep] == ["n0", "n1"]


def test_deep_n_truncates_total():
    """不同源、超过 deep_n 时截断到 deep_n。"""
    items = [_news(i, f"src{i}") for i in range(50)]
    deep = select_deep_news(items, deep_n=20, source_cap=2)
    assert len(deep) == 20


def test_preserves_input_order():
    items = [_news(2, "a"), _news(0, "b"), _news(1, "a")]
    deep = select_deep_news(items, deep_n=20, source_cap=2)
    assert [n["id"] for n in deep] == ["n2", "n0", "n1"]


def test_missing_source_name_grouped_as_unknown():
    items = [{"id": "x", "score": 1}, {"id": "y", "score": 1}, {"id": "z", "score": 1}]
    deep = select_deep_news(items, deep_n=20, source_cap=2)
    assert [n["id"] for n in deep] == ["x", "y"]


def test_empty_input():
    assert select_deep_news([], deep_n=20, source_cap=2) == []
