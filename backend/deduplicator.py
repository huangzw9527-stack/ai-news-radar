import re
from typing import List, Dict, Set
import numpy as np

from backend.embeddings import get_model


# 提取标题中的"区分性 token"：拉丁字母/数字组成的词（如 GPT-5.5、Claude、SOTA、LLM-as-a-Verifier）。
# 中文短语因缺乏分词不纳入；命名实体多以英文/型号出现，足以判定是否同一事件。
_DISTINCTIVE_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9.\-]{1,}|\d{2,}")

# 过滤掉过于通用、不具区分性的 token，避免"两条新闻都提到 AI / GitHub"就被算共享
_STOPWORDS = {
    "ai", "the", "a", "an", "and", "or", "of", "to", "in", "on", "at", "by",
    "for", "with", "is", "are", "was", "were", "be", "as", "from", "this", "that",
    "it", "its", "new", "vs",
}


def _distinctive_tokens(text: str) -> Set[str]:
    tokens = set()
    for t in _DISTINCTIVE_TOKEN.findall(text or ""):
        low = t.lower()
        if len(low) >= 2 and low not in _STOPWORDS:
            tokens.add(low)
    return tokens


class Deduplicator:
    # 高置信阈值：直接判定同一事件
    _HIGH_THRESHOLD = 0.85
    # 中等置信下限：需配合区分性 token 共现
    _LOW_THRESHOLD = 0.70
    # 中等置信下需共享的区分性 token 数量
    _MIN_SHARED_TOKENS = 2
    # 低相似度但 token 高度重叠的兜底路径
    # 抓中文短标题改写场景：sim 因句式差异降到 0.5x，但命名实体/数字大量重合
    _ENTITY_LOW_THRESHOLD = 0.55
    _ENTITY_MIN_SHARED_TOKENS = 4

    def __init__(self, semantic_threshold: float = 0.85):
        self._HIGH_THRESHOLD = semantic_threshold

    def _get_model(self):
        return get_model()

    def deduplicate(self, news_list: List[Dict], existing_ids: Set[str]) -> List[Dict]:
        # 第一层：URL哈希去重
        seen_ids = set(existing_ids)
        unique = []
        for n in news_list:
            if n["id"] not in seen_ids:
                seen_ids.add(n["id"])
                unique.append(n)

        if len(unique) <= 1:
            for n in unique:
                n["report_count"] = 1
            return unique

        # 第二层：基于标题的语义去重。标题比 title+summary 更纯净——
        # 不同信源摘要长度/详略悬殊会稀释余弦相似度
        titles = [n["title"] for n in unique]
        token_sets = [_distinctive_tokens(t) for t in titles]
        model = self._get_model()
        embeddings = model.encode(titles, convert_to_numpy=True)

        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        embeddings = embeddings / np.maximum(norms, 1e-9)

        # 按分数降序排列，优先保留高分
        indexed = sorted(enumerate(unique), key=lambda x: (
            -x[1].get("score", 0),
            -(x[1].get("source_tier") == 1),
        ))

        kept_indices = []
        removed = set()
        duplicate_counts: Dict[int, int] = {}

        for i, (orig_idx, _news) in enumerate(indexed):
            if orig_idx in removed:
                continue
            kept_indices.append(orig_idx)
            for j, (other_idx, _) in enumerate(indexed[i+1:], i+1):
                if other_idx in removed:
                    continue
                sim = float(np.dot(embeddings[orig_idx], embeddings[other_idx]))
                if self._is_duplicate(sim, token_sets[orig_idx], token_sets[other_idx]):
                    removed.add(other_idx)
                    duplicate_counts[orig_idx] = duplicate_counts.get(orig_idx, 0) + 1

        result = [unique[i] for i in sorted(kept_indices)]
        for i in sorted(kept_indices):
            unique[i]["report_count"] = duplicate_counts.get(i, 0) + 1
        return result

    def _is_duplicate(self, sim: float, tokens_a: Set[str], tokens_b: Set[str]) -> bool:
        if sim >= self._HIGH_THRESHOLD:
            return True
        # 中等相似度需要标题共享足够多的命名实体/型号词，
        # 避免把"OpenAI 发布 GPT-5"和"Anthropic 发布 Claude 5"误判为同条
        shared = len(tokens_a & tokens_b)
        if sim >= self._LOW_THRESHOLD and shared >= self._MIN_SHARED_TOKENS:
            return True
        # 兜底：sim 偏低但实体/数字重叠极多，几乎只能是同一事件改写
        if sim >= self._ENTITY_LOW_THRESHOLD and shared >= self._ENTITY_MIN_SHARED_TOKENS:
            return True
        return False
