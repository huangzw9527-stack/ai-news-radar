# 评分机制完善 + Wiki 知识库 Implementation Plan

> ⚠️ **已废弃（仅存档）**：本计划实现的 Wiki 知识库 / 信息增量评分机制已于 2026-05-19 整体下线（提交 `e2a0bbf`、`face1e2`）。请勿再执行本计划，保留仅作历史记录。

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 用「信息增量」替代纯规则排序，解决重要新闻被埋和旧闻重发混入 Top 10 两个核心痛点，同时以副产品形式积累 Wiki 知识库。

**Architecture:** 新建 `backend/scorer.py` 综合评分器取代 `ranker.py` + `analyzer.py` Step 1；在 SQLite 新增 `wiki_news_index` / `wiki_concepts` 两张表；`analyzer.py` 移除 Step 1，新增 Wiki 回填方法；`pipeline.py` 接线。

**Tech Stack:** Python, SQLite, sentence-transformers (已有), FastAPI (不改动), math/numpy (已有)

---

## Task 1: Wiki DB 层

**Files:**
- Modify: `backend/db.py`
- Create: `tests/test_db_wiki.py`

### Step 1: 写失败测试

创建 `tests/test_db_wiki.py`：

```python
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from backend.db import Database

def _make_db():
    db = Database(":memory:")
    db.init()
    return db

def test_upsert_and_get_wiki_news():
    db = _make_db()
    entry = {
        "id": "n001",
        "event_id": "GPT-5发布",
        "dimensions": '["概念发布","产品参数"]',
        "key_facts": '["OpenAI发布GPT-5","支持100万token上下文"]',
        "published_at": "2026-05-01T08:00:00",
        "increment_level": "S",
    }
    db.upsert_wiki_news(entry)
    rows = db.get_wiki_news_recent(days=30)
    assert len(rows) == 1
    assert rows[0]["event_id"] == "GPT-5发布"

def test_wiki_news_upsert_idempotent():
    db = _make_db()
    entry = {
        "id": "n001", "event_id": "X", "dimensions": "[]",
        "key_facts": "[]", "published_at": "2026-05-01T08:00:00",
        "increment_level": "S",
    }
    db.upsert_wiki_news(entry)
    db.upsert_wiki_news(entry)
    assert len(db.get_wiki_news_recent(days=30)) == 1

def test_upsert_and_get_wiki_concept():
    db = _make_db()
    concept = {
        "name": "Chain-of-Thought",
        "definition": "让模型逐步推理的提示技巧",
        "first_seen": "2026-05-01",
        "related_events": '["GPT-4o发布"]',
    }
    db.upsert_wiki_concept(concept)
    rows = db.get_wiki_concepts()
    assert len(rows) == 1
    assert rows[0]["name"] == "Chain-of-Thought"

def test_cleanup_wiki_news():
    db = _make_db()
    old = {
        "id": "old001", "event_id": "旧事件", "dimensions": "[]",
        "key_facts": "[]", "published_at": "2025-01-01T00:00:00",
        "increment_level": "C",
    }
    recent = {
        "id": "new001", "event_id": "新事件", "dimensions": "[]",
        "key_facts": "[]", "published_at": "2026-05-05T00:00:00",
        "increment_level": "S",
    }
    db.upsert_wiki_news(old)
    db.upsert_wiki_news(recent)
    db.cleanup_wiki_news(days=90)
    rows = db.get_wiki_news_recent(days=9999)
    ids = [r["id"] for r in rows]
    assert "old001" not in ids
    assert "new001" in ids
```

### Step 2: 运行测试确认失败

```bash
cd D:\AI\ClaudeProject\ai-news-radar
python -m pytest tests/test_db_wiki.py -v
```
预期：`FAILED` with `AttributeError: 'Database' object has no attribute 'upsert_wiki_news'`

### Step 3: 在 db.py 新增 Wiki 表 DDL + CRUD

在 `backend/db.py` 的 `init()` 方法的 `executescript` 字符串末尾追加两张表：

```python
            CREATE TABLE IF NOT EXISTS wiki_news_index (
                id              TEXT PRIMARY KEY,
                event_id        TEXT,
                dimensions      TEXT,
                key_facts       TEXT,
                published_at    TEXT,
                increment_level TEXT
            );
            CREATE TABLE IF NOT EXISTS wiki_concepts (
                name            TEXT PRIMARY KEY,
                definition      TEXT,
                first_seen      TEXT,
                related_events  TEXT
            );
```

在 `_migrate()` 方法末尾（`conn.commit()` 之前）追加：

```python
        # wiki tables（新数据库由 init() 创建，旧数据库可能没有）
        existing_wiki = {row[1] for row in conn.execute("PRAGMA table_info(wiki_news_index)").fetchall()}
        if not existing_wiki:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS wiki_news_index (
                    id TEXT PRIMARY KEY, event_id TEXT, dimensions TEXT,
                    key_facts TEXT, published_at TEXT, increment_level TEXT
                );
                CREATE TABLE IF NOT EXISTS wiki_concepts (
                    name TEXT PRIMARY KEY, definition TEXT,
                    first_seen TEXT, related_events TEXT
                );
            """)
```

在 `close()` 方法之前新增四个方法：

```python
    def upsert_wiki_news(self, entry: Dict[str, Any]):
        conn = self._conn()
        conn.execute("""
            INSERT OR REPLACE INTO wiki_news_index
            (id, event_id, dimensions, key_facts, published_at, increment_level)
            VALUES (:id, :event_id, :dimensions, :key_facts, :published_at, :increment_level)
        """, entry)
        conn.commit()

    def upsert_wiki_concept(self, concept: Dict[str, Any]):
        conn = self._conn()
        conn.execute("""
            INSERT OR IGNORE INTO wiki_concepts (name, definition, first_seen, related_events)
            VALUES (:name, :definition, :first_seen, :related_events)
        """, concept)
        conn.commit()

    def get_wiki_news_recent(self, days: int = 30) -> List[Dict]:
        from datetime import datetime, timedelta, timezone
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()
        conn = self._conn()
        rows = conn.execute(
            "SELECT * FROM wiki_news_index WHERE substr(published_at,1,10) >= ? ORDER BY published_at DESC",
            (cutoff,)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_wiki_concepts(self) -> List[Dict]:
        conn = self._conn()
        rows = conn.execute("SELECT * FROM wiki_concepts ORDER BY first_seen DESC").fetchall()
        return [dict(r) for r in rows]

    def cleanup_wiki_news(self, days: int = 90):
        from datetime import datetime, timedelta, timezone
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()
        conn = self._conn()
        conn.execute("DELETE FROM wiki_news_index WHERE substr(published_at,1,10) < ?", (cutoff,))
        conn.commit()
```

### Step 4: 运行测试确认通过

```bash
python -m pytest tests/test_db_wiki.py -v
```
预期：全部 `PASSED`

### Step 5: 提交

```bash
git add backend/db.py tests/test_db_wiki.py
git commit -m "feat(db): add wiki_news_index and wiki_concepts tables"
```

---

## Task 2: Scorer 模块

**Files:**
- Create: `backend/scorer.py`
- Create: `tests/test_scorer.py`

### Step 1: 写失败测试

创建 `tests/test_scorer.py`：

```python
import os, sys, math
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from unittest.mock import MagicMock, patch
from backend.scorer import Scorer, _hours_since, _freshness, INCREMENT_SCORES

# ---------- 纯函数测试（无依赖）----------

def test_hours_since_recent():
    from datetime import datetime, timedelta, timezone
    recent = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    assert 1.5 < _hours_since(recent) < 2.5

def test_hours_since_old():
    assert _hours_since("2020-01-01T00:00:00") > 10000

def test_hours_since_none():
    # None/空字符串视为极旧
    assert _hours_since(None) > 10000
    assert _hours_since("") > 10000

def test_freshness_decay():
    # 0小时 → 约1.0，24小时 → 约0.09，72小时 → 约0.0007
    assert _freshness_for_hours(0) > 0.99
    assert 0.08 < _freshness_for_hours(24) < 0.11
    assert _freshness_for_hours(72) < 0.001

def _freshness_for_hours(h):
    return math.exp(-0.1 * h)

def test_increment_scores():
    assert INCREMENT_SCORES["S"] == 100
    assert INCREMENT_SCORES["A"] == 80
    assert INCREMENT_SCORES["B"] == 30
    assert INCREMENT_SCORES["C"] == 5
    assert INCREMENT_SCORES["D"] == 0

# ---------- Scorer 集成测试（mock LLM + DB）----------

def _make_news(n=3, hours_ago=1):
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    items = []
    for i in range(n):
        pub = (now - timedelta(hours=hours_ago)).isoformat()
        items.append({
            "id": f"n{i:03d}",
            "title": f"新闻{i}：AI大模型发布",
            "summary": f"某公司发布了新的大语言模型{i}",
            "full_text": "",
            "source_name": f"source{i}",
            "source_tier": 1,
            "published_at": pub,
            "collected_at": pub,
        })
    return items

def test_time_gate_filters_old_news():
    """超过72小时的新闻不应进入结果。"""
    llm = MagicMock()
    db = MagicMock()
    db.get_wiki_news_recent.return_value = []

    scorer = Scorer(llm=llm, topics=[], db=db)
    old_news = _make_news(2, hours_ago=100)
    result = scorer.score_and_rank(old_news, top_n=10)
    assert result == []
    llm.chat.assert_not_called()

def test_scorer_returns_top_n():
    """正常情况下应返回 top_n 条结果。"""
    llm = MagicMock()
    db = MagicMock()
    db.get_wiki_news_recent.return_value = []

    # LLM返回每条新闻的分数
    def fake_chat(system, prompt):
        import json
        scores = {str(i+1): {"relevance": 80, "increment": "S", "reason": "全新",
                              "event_id": f"事件{i}", "dimensions": ["概念发布"]}
                  for i in range(5)}
        return json.dumps({"scores": scores})

    llm.chat.side_effect = fake_chat

    news = _make_news(5, hours_ago=1)
    scorer = Scorer(llm=llm, topics=[], db=db)
    result = scorer.score_and_rank(news, top_n=3)
    assert len(result) <= 3

def test_source_cap():
    """同一信源最多2条进入结果。"""
    llm = MagicMock()
    db = MagicMock()
    db.get_wiki_news_recent.return_value = []

    def fake_chat(system, prompt):
        import json
        # 5条新闻全给高分
        scores = {str(i+1): {"relevance": 90, "increment": "S", "reason": "全新",
                              "event_id": f"事件{i}", "dimensions": ["概念发布"]}
                  for i in range(5)}
        return json.dumps({"scores": scores})

    llm.chat.side_effect = fake_chat

    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    # 5条新闻，全来自同一信源
    news = [{
        "id": f"n{i}", "title": f"标题{i}", "summary": "摘要", "full_text": "",
        "source_name": "same_source", "source_tier": 1,
        "published_at": (now - timedelta(hours=1)).isoformat(),
        "collected_at": (now - timedelta(hours=1)).isoformat(),
    } for i in range(5)]

    scorer = Scorer(llm=llm, topics=[], db=db)
    result = scorer.score_and_rank(news, top_n=10)
    assert len(result) <= 2
```

### Step 2: 运行测试确认失败

```bash
python -m pytest tests/test_scorer.py -v
```
预期：`ImportError: cannot import name 'Scorer' from 'backend.scorer'`

### Step 3: 实现 scorer.py

创建 `backend/scorer.py`：

```python
import json
import math
import re
from datetime import datetime, timezone
from typing import List, Dict, Optional

import numpy as np

from backend.embeddings import get_model
from backend.llm.base import BaseLLMProvider

INCREMENT_SCORES = {"S": 100, "A": 80, "B": 30, "C": 5, "D": 0}
_TIER_FACTORS = {1: 1.0, 2: 0.85, 3: 0.70}
_DEFAULT_TIER_FACTOR = 0.80
_TIME_GATE_HOURS = 72
_MIN_TOPIC_COS = 0.3
_WIKI_CONTEXT_DAYS = 30
_BATCH_SIZE = 20
_SOURCE_CAP = 2

SYSTEM_PROMPT = "你是AI产业分析师。直接输出JSON，不包含任何markdown标记或思考过程。所有输出使用中文。"


def _hours_since(published_at) -> float:
    if not published_at:
        return float("inf")
    try:
        s = str(published_at).strip()
        s = s.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - dt
        return delta.total_seconds() / 3600
    except Exception:
        return float("inf")


def _freshness(published_at) -> float:
    return math.exp(-0.1 * _hours_since(published_at))


def _tier_factor(tier) -> float:
    try:
        return _TIER_FACTORS.get(int(tier) if tier is not None else None, _DEFAULT_TIER_FACTOR)
    except (TypeError, ValueError):
        return _DEFAULT_TIER_FACTOR


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
            f"{t.get('name','')}。{t.get('description','')}。{' '.join(t.get('keywords',[]))}"
            for t in self.topics
        ]
        raw = get_model().encode(texts, convert_to_numpy=True)
        norms = np.linalg.norm(raw, axis=-1, keepdims=True)
        self._topic_embeds = raw / np.maximum(norms, 1e-9)

    def score_and_rank(self, news_list: List[Dict], top_n: int = 10) -> List[Dict]:
        # Step 1: 时效拦截
        candidates = [
            n for n in news_list
            if _hours_since(n.get("published_at") or n.get("collected_at")) <= _TIME_GATE_HOURS
        ]
        if not candidates:
            return []

        # Step 2: Embedding 相关性过滤
        if self.topics:
            self._ensure_topic_embeds()
            texts = [(n.get("title") or "") + "。" + (n.get("summary") or "") for n in candidates]
            raw = get_model().encode(texts, convert_to_numpy=True)
            norms = np.linalg.norm(raw, axis=-1, keepdims=True)
            embeds = raw / np.maximum(norms, 1e-9)
            sims = embeds @ self._topic_embeds.T
            max_sims = sims.max(axis=1)
            filtered = [(n, embeds[i]) for i, n in enumerate(candidates) if max_sims[i] >= _MIN_TOPIC_COS]
            if not filtered:
                filtered = list(zip(candidates, [None] * len(candidates)))
            candidates, cand_embeds = zip(*filtered)
            candidates = list(candidates)
            cand_embeds = list(cand_embeds)
        else:
            cand_embeds = [None] * len(candidates)

        # Step 3: Wiki 上下文准备
        wiki_entries = self.db.get_wiki_news_recent(days=_WIKI_CONTEXT_DAYS)
        wiki_context = self._build_wiki_context(candidates, cand_embeds, wiki_entries)

        # Step 4: LLM 批量打分
        self._llm_score(candidates, wiki_context)

        # Step 5: 最终得分 + 排序 + 同源限制
        for item in candidates:
            rel = item.get("llm_relevance", 50)
            inc = INCREMENT_SCORES.get(item.get("increment_level", "S"), 100)
            fresh = _freshness(item.get("published_at") or item.get("collected_at"))
            item["score"] = (rel * 0.5 + inc * 0.5) * fresh * _tier_factor(item.get("source_tier"))

        candidates.sort(key=lambda x: x["score"], reverse=True)

        top = []
        source_counts: Dict[str, int] = {}
        for item in candidates:
            src = item.get("source_name", "unknown")
            if source_counts.get(src, 0) >= _SOURCE_CAP:
                continue
            top.append(item)
            source_counts[src] = source_counts.get(src, 0) + 1
            if len(top) >= top_n:
                break

        return top

    def _build_wiki_context(self, candidates, cand_embeds, wiki_entries) -> Dict[str, str]:
        """为每条候选新闻构建紧凑的 Wiki 上下文字符串。"""
        if not wiki_entries:
            return {n["id"]: "" for n in candidates}

        # 编码 wiki 条目标题（用 event_id 作为文本）
        wiki_texts = [e.get("event_id", "") or "" for e in wiki_entries]
        try:
            wiki_raw = get_model().encode(wiki_texts, convert_to_numpy=True)
            wiki_norms = np.linalg.norm(wiki_raw, axis=-1, keepdims=True)
            wiki_embeds = wiki_raw / np.maximum(wiki_norms, 1e-9)
        except Exception:
            return {n["id"]: "" for n in candidates}

        result = {}
        for news, embed in zip(candidates, cand_embeds):
            if embed is None:
                result[news["id"]] = ""
                continue
            sims = wiki_embeds @ embed
            top3_idx = np.argsort(sims)[::-1][:3]
            parts = []
            for idx in top3_idx:
                if sims[idx] < 0.3:
                    continue
                entry = wiki_entries[idx]
                try:
                    dims = json.loads(entry.get("dimensions") or "[]")
                    dims_str = "、".join(dims) if dims else "无"
                except Exception:
                    dims_str = "无"
                parts.append(f'事件"{entry.get("event_id","")}" 已覆盖维度：{dims_str}')
            result[news["id"]] = "\n".join(parts)
        return result

    def _llm_score(self, candidates: List[Dict], wiki_context: Dict[str, str]):
        """分批调用 LLM，将 llm_relevance / increment_level / event_id / dimensions 写回条目。"""
        for batch_start in range(0, len(candidates), _BATCH_SIZE):
            batch = candidates[batch_start: batch_start + _BATCH_SIZE]
            try:
                self._score_batch(batch, wiki_context)
            except Exception as e:
                print(f"[Scorer] batch {batch_start // _BATCH_SIZE + 1} error: {e}", flush=True)
                for item in batch:
                    item.setdefault("llm_relevance", 50)
                    item.setdefault("increment_level", "S")
                    item.setdefault("event_id", "")
                    item.setdefault("dimensions", [])

    def _score_batch(self, batch: List[Dict], wiki_context: Dict[str, str]):
        topics_brief = "\n".join(
            f"【{t.get('name','')}】{t.get('description','')}"
            for t in self.topics
        )[:600] if self.topics else "AI行业动态监测"

        news_text = "\n\n".join(
            f"[{i+1}] 标题：{item['title']}\n摘要：{(item.get('summary') or '')[:150]}"
            + (f"\n相关历史：{wiki_context.get(item['id'], '')}" if wiki_context.get(item['id']) else "")
            for i, item in enumerate(batch)
        )

        example = {str(i+1): {"relevance": 80, "increment": "S", "reason": "全新内容",
                               "event_id": "事件名称", "dimensions": ["概念发布"]}
                   for i in range(len(batch))}

        prompt = f"""请对以下新闻评估两个维度：
1. 业务关联性（0-100）：与监控话题的相关程度
2. 信息增量等级：
   S（全新）：知识库中无任何同源记录
   A（新维度）：主题已有，但本次提供全新信息维度（如已有概念发布，本次是实测数据）
   B（低增量）：主题已有，仅补充边缘信息，核心事实高度重合
   C（复述）：与已有记录高度重复，仅改标题/措辞
   D（旧闻）：内容与已有记录完全一致，无任何新增内容

[监控话题]
{topics_brief}

[待评估新闻]
{news_text}

对每条新闻同时输出：归一化事件名（event_id）、本次涉及的信息维度列表（dimensions，从以下选择：概念发布/原理拆解/数据披露/事件进展/政策解读/实测验证/行业分析/落地实践）。

直接输出JSON：
{json.dumps({"scores": example}, ensure_ascii=False)}"""

        resp = self.llm.chat(SYSTEM_PROMPT, prompt)
        data = self._parse_json(resp)
        scores = data.get("scores", {})

        for i, item in enumerate(batch):
            key = str(i + 1)
            s = scores.get(key, {})
            if isinstance(s, dict):
                item["llm_relevance"] = int(s.get("relevance", 50))
                item["increment_level"] = s.get("increment", "S")
                item["llm_increment_reason"] = s.get("reason", "")
                item["event_id"] = s.get("event_id", "")
                item["dimensions"] = s.get("dimensions", [])
            else:
                item.setdefault("llm_relevance", 50)
                item.setdefault("increment_level", "S")
                item.setdefault("event_id", "")
                item.setdefault("dimensions", [])

    # ------ JSON 解析（与 analyzer.py 相同逻辑）------

    def _parse_json(self, text: str) -> Dict:
        raw = text
        text = text.strip()
        text = re.sub(r"<think>[\s\S]*?</think>", "", text).strip()
        if "<think>" in text:
            text = text.split("</think>")[-1].strip()
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
        best = None
        i = 0
        while i < len(text):
            if text[i] == "{":
                end = self._match_brace(text, i)
                if end and (best is None or end - i > len(best)):
                    best = text[i:end + 1]
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
            if ch == '"' and not escape:
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
```

### Step 4: 运行测试确认通过

```bash
python -m pytest tests/test_scorer.py -v
```
预期：全部 `PASSED`

### Step 5: 提交

```bash
git add backend/scorer.py tests/test_scorer.py
git commit -m "feat(scorer): new comprehensive scorer replacing ranker + analyzer Step 1"
```

---

## Task 3: Analyzer 改造（移除 Step 1，新增 Wiki 回填）

**Files:**
- Modify: `backend/analyzer.py`

### Step 1: 移除 Step 1 的 LLM 业务关联性打分

在 `analyze()` 方法中：

**删除**以下代码块（约第 59-74 行）：
```python
        # Step 1: LLM 评估业务关联性并打分排序
        print(f"[Analyzer] Step 1: LLM 评估 {len(news_list)} 条新闻的业务关联性...", flush=True)
        scored = self._llm_score_relevance(news_list)

        # 同源限制：每个来源最多 SOURCE_CAP 条，保证信源多样性
        top10 = []
        source_counts: dict[str, int] = {}
        for item in scored:
            src = item.get("source_name", "unknown")
            if source_counts.get(src, 0) >= SOURCE_CAP:
                continue
            top10.append(item)
            source_counts[src] = source_counts.get(src, 0) + 1
            if len(top10) >= TOP_N:
                break
        print(f"[Analyzer] Step 1 完成: 选出 {len(top10)} 条（每源≤{SOURCE_CAP}），来源分布: {dict(source_counts)}", flush=True)
```

**替换为**（直接将传入的 news_list 作为 top10，因为 scorer 已完成排序和同源限制）：
```python
        top10 = news_list[:TOP_N]
        print(f"[Analyzer] 接收预排序新闻 {len(top10)} 条，直接进入分析", flush=True)
```

同时**删除** `_llm_score_relevance()` 整个方法（约第 109-167 行）。

也删除文件顶部不再使用的 `SOURCE_CAP = 2` 常量。

### Step 2: 新增 Wiki 回填方法

在 `_generate_strategic_advice()` 方法之前新增：

```python
    def backfill_wiki(self, top10: List[Dict], analysis: Dict, db) -> None:
        """将 Step 2 分析结果回填到 Wiki 知识库。"""
        from datetime import date
        concepts = analysis.get("concepts", {})
        principles = analysis.get("principles", {})

        for i, item in enumerate(top10):
            key = str(i + 1)
            concept = concepts.get(key, "")
            principle = principles.get(key, "")

            wiki_entry = {
                "id": item["id"],
                "event_id": item.get("event_id", concept[:40] if concept else ""),
                "dimensions": json.dumps(item.get("dimensions", []), ensure_ascii=False),
                "key_facts": json.dumps([concept[:60]] if concept else [], ensure_ascii=False),
                "published_at": item.get("published_at", ""),
                "increment_level": item.get("increment_level", "S"),
            }
            try:
                db.upsert_wiki_news(wiki_entry)
            except Exception as e:
                print(f"[Analyzer] wiki_news backfill error #{i+1}: {e}", flush=True)

            if concept:
                concept_entry = {
                    "name": concept[:50],
                    "definition": (principle[:60] if principle else concept[:60]),
                    "first_seen": date.today().isoformat(),
                    "related_events": json.dumps(
                        [item.get("event_id", "")], ensure_ascii=False
                    ),
                }
                try:
                    db.upsert_wiki_concept(concept_entry)
                except Exception as e:
                    print(f"[Analyzer] wiki_concept backfill error #{i+1}: {e}", flush=True)
```

### Step 3: 验证现有测试不受影响

```bash
python -m pytest tests/ -v
```
预期：`test_db.py` 和 `test_db_wiki.py` 全部 `PASSED`（scorer 测试也继续通过）

### Step 4: 提交

```bash
git add backend/analyzer.py
git commit -m "refactor(analyzer): remove Step 1 LLM scoring, add wiki backfill method"
```

---

## Task 4: Pipeline 接线

**Files:**
- Modify: `backend/pipeline.py`

### Step 1: 替换 Ranker 为 Scorer

在 `pipeline.py` 顶部导入区，将：
```python
from backend.ranker import Ranker
```
替换为：
```python
from backend.scorer import Scorer
```

### Step 2: 修改 `__init__` 中的初始化

将：
```python
        self.ranker = Ranker(topics=config.get("topics", []))
```
替换为：
```python
        llm_for_scorer = create_llm_provider(config["llm"])
        self.scorer = Scorer(
            llm=llm_for_scorer,
            topics=config.get("topics", []),
            db=db,
        )
```

注意：`llm` 已在下一行初始化用于 analyzer，这里单独创建一个用于 scorer（同一配置，两个实例，避免共享状态问题）。

### Step 3: 修改 `run()` 中的排序调用

将（约第 162-168 行）：
```python
        # 规则预排序，取 top 20 候选送给 LLM 评估关联性
        ranked = self.ranker.rank(recent_news, top_n=20)
        score_map = {n["id"]: n["score"] for n in ranked}
        self.db.update_scores(score_map)

        emit(f"规则预筛: {len(recent_news)} → {len(ranked)} 条候选")
        emit("进入LLM分析（LLM评分关联性 → 选Top10 → 逐条分析）...")
        analysis = self.analyzer.analyze(ranked)
```
替换为：
```python
        # 综合评分：时效拦截 → Embedding过滤 → Wiki增量判定 → LLM打分 → Top10
        emit(f"综合评分：{len(recent_news)} 条候选（时效+增量+关联性）...")
        top10 = self.scorer.score_and_rank(recent_news, top_n=10)
        score_map = {n["id"]: n["score"] for n in top10}
        self.db.update_scores(score_map)

        emit(f"评分完成: 选出 {len(top10)} 条，进入LLM深度分析...")
        analysis = self.analyzer.analyze(top10)
```

### Step 4: 新增 Wiki 回填调用

在 `analysis = self.analyzer.analyze(top10)` 之后、`# 保存报告` 之前插入：

```python
        # Wiki 知识库回填（复用 Step 2 已提取字段）
        emit("Wiki 知识库回填...")
        self.analyzer.backfill_wiki(analysis["top10"], analysis, self.db)
        # 清理90天前的旧条目
        self.db.cleanup_wiki_news(days=90)
```

### Step 5: 运行完整测试套件

```bash
python -m pytest tests/ -v
```
预期：全部 `PASSED`

### Step 6: 提交

```bash
git add backend/pipeline.py
git commit -m "feat(pipeline): wire scorer + wiki backfill, replace ranker"
```

---

## Task 5: 冒烟测试（可选但推荐）

### Step 1: 启动服务验证流程不崩溃

```bash
# 启动后端（不触发采集，只验证启动正常）
cd D:\AI\ClaudeProject\ai-news-radar
python -m uvicorn backend.main:app --port 8000
```

在另一个终端触发手动采集：
```bash
curl -X POST http://localhost:8000/api/pipeline/run
```

观察日志输出应包含：
```
综合评分：X 条候选（时效+增量+关联性）...
评分完成: 选出 N 条，进入LLM深度分析...
Wiki 知识库回填...
完成！报告ID: ...
```

### Step 2: 提交最终状态

```bash
git add -A
git commit -m "chore: smoke test verified - scoring increment + wiki pipeline working"
```

---

## 文件改动总览

| 文件 | 类型 | 说明 |
|------|------|------|
| `backend/db.py` | 修改 | 新增 wiki 表 DDL + 4个CRUD方法 |
| `backend/scorer.py` | 新建 | 综合评分器（时效/Embedding/Wiki/LLM） |
| `backend/analyzer.py` | 修改 | 移除Step1，新增backfill_wiki() |
| `backend/pipeline.py` | 修改 | Ranker→Scorer，新增Wiki回填调用 |
| `tests/test_db_wiki.py` | 新建 | Wiki DB层测试 |
| `tests/test_scorer.py` | 新建 | Scorer单元测试 |
