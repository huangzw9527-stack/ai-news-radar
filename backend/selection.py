"""深度分析层选取的纯函数（无重依赖，便于单测）。"""
from typing import Dict, List


def select_deep_news(
    all_relevant: List[Dict],
    deep_n: int = 20,
    source_cap: int = 2,
) -> List[Dict]:
    """按打分顺序选取深度分析层：每个来源最多 source_cap 条，总计最多 deep_n 条。

    入参须已按分数降序排列；保持其相对顺序。其余条目归入扫描层（由调用方计算）。
    """
    deep_news: List[Dict] = []
    source_counts: Dict[str, int] = {}
    for item in all_relevant:
        src = item.get("source_name", "unknown")
        if source_counts.get(src, 0) >= source_cap:
            continue
        deep_news.append(item)
        source_counts[src] = source_counts.get(src, 0) + 1
        if len(deep_news) >= deep_n:
            break
    return deep_news
