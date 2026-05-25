import json
import math
import re
from datetime import datetime, timezone
from typing import Dict, List, Optional

import numpy as np

from backend.embeddings import get_model
from backend.llm.base import BaseLLMProvider

_SOURCE_SCORES: Dict[int, float] = {1: 27.0, 2: 20.0, 3: 10.0}
_DEFAULT_SOURCE_SCORE = 15.0
_HALF_LIFE_HOURS: Dict[str, float] = {
    "模型发布": 48.0, "产品动态": 48.0,
    "产业商业": 168.0, "观点深度": 168.0,
    "研究论文": 336.0, "实操技巧": 336.0,
}
_DEFAULT_HALF_LIFE = 72.0
_TIME_GATE_HOURS = 72
_MIN_TOPIC_COS = 0.3
_BATCH_SIZE = 20
_MIN_RELEVANCE = 30          # LLM 关联性低于此值直接过滤

_SYSTEM_PROMPT = "你是AI产业分析师。直接输出JSON，不包含任何markdown标记或思考过程。所有输出使用中文。"


def _hours_since(published_at) -> float:
    if not published_at:
        return float("inf")
    try:
        s = str(published_at).strip().replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt).total_seconds() / 3600
    except Exception:
        return float("inf")


def _time_decay(published_at, main_category: str = "") -> float:
    hours = _hours_since(published_at)
    if hours == float("inf"):
        return 0.1
    half_life = _HALF_LIFE_HOURS.get(main_category, _DEFAULT_HALF_LIFE)
    return math.exp(-math.log(2) * hours / half_life)


class Scorer:
    def __init__(self, llm: BaseLLMProvider, topics: List[Dict], db):
        self.llm = llm
        self.topics = topics
        self.db = db
        self._topic_embeds: Optional[np.ndarray] = None

    def _ensure_topic_embeds(self):
        if self._topic_embeds is not None or not self.topics:
            return
        texts = [
            f"{t.get('name', '')}。{t.get('description', '')}。{' '.join(t.get('keywords', []))}"
            for t in self.topics
        ]
        raw = get_model().encode(texts, convert_to_numpy=True)
        norms = np.linalg.norm(raw, axis=-1, keepdims=True)
        self._topic_embeds = raw / np.maximum(norms, 1e-9)

    def score_and_rank(self, news_list: List[Dict]) -> List[Dict]:
        # Step 1: 时效拦截
        candidates = [
            n for n in news_list
            if _hours_since(n.get("published_at") or n.get("collected_at")) <= _TIME_GATE_HOURS
        ]
        if not candidates:
            return []

        # Step 2: Embedding 相关性过滤（仅在有 topics 时生效）
        if self.topics:
            self._ensure_topic_embeds()
            texts = [(n.get("title") or "") + "。" + (n.get("summary") or "") for n in candidates]
            raw = get_model().encode(texts, convert_to_numpy=True)
            norms = np.linalg.norm(raw, axis=-1, keepdims=True)
            embeds = raw / np.maximum(norms, 1e-9)
            sims = embeds @ self._topic_embeds.T
            max_sims = sims.max(axis=1)
            kept = [n for i, n in enumerate(candidates) if max_sims[i] >= _MIN_TOPIC_COS]
            if kept:
                candidates = kept

        # Step 3: LLM 批量打分（content 维度 + 业务关联性 + main_category）
        self._llm_score(candidates)

        # Step 4: 最终得分 + 排序
        for item in candidates:
            try:
                tier_int = int(item.get("source_tier") or 0)
            except (TypeError, ValueError):
                tier_int = 0
            source_score = _SOURCE_SCORES.get(tier_int, _DEFAULT_SOURCE_SCORE)
            content_score = (
                float(item.get("llm_substantiality", 10)) +
                float(item.get("llm_density", 10)) +
                float(item.get("llm_originality", 10))
            )
            if item.get("indicator") == "twitter":
                raw_interactions = float(item.get("interaction_count", 0) or 0)
                hotness = min(25.0, raw_interactions / 200.0)
            else:
                hotness = min(25.0, float(item.get("report_count", 1)) * 5.0)
            decay = _time_decay(
                item.get("published_at") or item.get("collected_at"),
                item.get("main_category", ""),
            )
            # 有话题配置时，relevance 作为乘法因子（0→0.2 到 100→1.0）
            if self.topics:
                relevance = float(item.get("llm_relevance", 50))
                relevance_factor = 0.2 + 0.8 * (relevance / 100.0)
            else:
                relevance_factor = 1.0
            item["score"] = (source_score + content_score + hotness) * decay * relevance_factor

        # 有话题配置时过滤低关联性条目
        if self.topics:
            before = len(candidates)
            candidates = [n for n in candidates if n.get("llm_relevance", 0) >= _MIN_RELEVANCE]
            filtered = before - len(candidates)
            if filtered:
                print(f"[Scorer] 关联性过滤: 移除 {filtered} 条 relevance<{_MIN_RELEVANCE} 的新闻", flush=True)

        candidates.sort(key=lambda x: x["score"], reverse=True)
        return candidates

    def _llm_score(self, candidates: List[Dict]):
        for batch_start in range(0, len(candidates), _BATCH_SIZE):
            batch = candidates[batch_start: batch_start + _BATCH_SIZE]
            try:
                self._score_batch(batch)
            except Exception as e:
                print(f"[Scorer] batch {batch_start // _BATCH_SIZE + 1} error: {e}", flush=True)
                for item in batch:
                    item.setdefault("llm_relevance", 50)
                    item.setdefault("llm_substantiality", 10)
                    item.setdefault("llm_density", 10)
                    item.setdefault("llm_originality", 10)
                    item.setdefault("main_category", "")

    def _score_batch(self, batch: List[Dict]):
        topics_brief = (
            "\n".join(f"【{t.get('name', '')}】{t.get('description', '')}" for t in self.topics)[:600]
            if self.topics else "AI行业动态监测"
        )

        news_text = "\n\n".join(
            f"[{i+1}] 标题：{item['title']}\n摘要：{(item.get('summary') or '')[:150]}"
            for i, item in enumerate(batch)
        )

        example = {
            str(i + 1): {
                "relevance": 80,
                "content": {"substantiality": 12, "density": 10, "originality": 13},
                "main_category": "模型发布",
            }
            for i in range(len(batch))
        }

        prompt = f"""请对以下新闻评估三个维度：
1. 业务关联性（0-100）：与监控话题的相关程度
2. content（内容质量，各项 0-15）：
   - substantiality（实质性）：硬事件（发布/融资/开源/数据/benchmark）满分15；纯观点/预测≤8
   - density（信息密度）：含具体数字/benchmark/产品名/可验证信息越多越高
   - originality（原创度）：首发原创15；编译/翻译12；纯转载9
3. main_category：从[模型发布, 产品动态, 产业商业, 研究论文, 实操技巧, 观点深度]选一个

[监控话题]
{topics_brief}

[待评估新闻]
{news_text}

直接输出JSON：
{json.dumps({"scores": example}, ensure_ascii=False)}"""

        resp = self.llm.chat(_SYSTEM_PROMPT, prompt)
        data = self._parse_json(resp)
        scores = data.get("scores", {})

        for i, item in enumerate(batch):
            key = str(i + 1)
            s = scores.get(key, {})
            if isinstance(s, dict):
                item["llm_relevance"] = int(float(s.get("relevance", 50)))
                content = s.get("content", {})
                if isinstance(content, dict):
                    item["llm_substantiality"] = int(float(content.get("substantiality", 10)))
                    item["llm_density"] = int(float(content.get("density", 10)))
                    item["llm_originality"] = int(float(content.get("originality", 10)))
                else:
                    item["llm_substantiality"] = 10
                    item["llm_density"] = 10
                    item["llm_originality"] = 10
                item["main_category"] = s.get("main_category", "")
            else:
                item.setdefault("llm_relevance", 50)
                item.setdefault("llm_substantiality", 10)
                item.setdefault("llm_density", 10)
                item.setdefault("llm_originality", 10)
                item.setdefault("main_category", "")

    def _parse_json(self, text: str) -> Dict:
        raw = text
        text = re.sub(r"<think>[\s\S]*?</think>", "", text.strip()).strip()
        if "```" in text:
            m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
            if m:
                text = m.group(1).strip()
        for src in (text, raw):
            obj = self._extract_json(src)
            if obj:
                try:
                    return json.loads(obj)
                except json.JSONDecodeError:
                    pass
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            raise ValueError(f"Cannot parse JSON (len={len(raw)}): {raw[:300]}")

    def _extract_json(self, text: str) -> Optional[str]:
        best: Optional[str] = None
        i = 0
        while i < len(text):
            if text[i] == "{":
                end = self._match_brace(text, i)
                if end is not None and (best is None or end - i + 1 > len(best)):
                    best = text[i: end + 1]
            i += 1
        return best

    def _match_brace(self, text: str, start: int) -> Optional[int]:
        depth, in_str, escape = 0, False, False
        for i in range(start, len(text)):
            ch = text[i]
            if escape:
                escape = False
                continue
            if ch == "\\":
                escape = True
                continue
            if ch == '"':
                in_str = not in_str
                continue
            if in_str:
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return i
        return None
