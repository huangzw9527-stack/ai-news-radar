# AI News Radar Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 构建一个自动采集全球10家AI机构新闻、LLM分析、挖掘公司业务机会并展示在Web仪表板的完整系统。

**Architecture:** FastAPI后端 + React前端 + SQLite存储。采集层用feedparser(RSS) + Playwright(爬虫)双轨，sentence-transformers做本地语义去重，LLM可配置切换（Claude/OpenAI/Ollama），APScheduler定时触发。

**Tech Stack:** Python 3.11+, FastAPI, feedparser, Playwright, sentence-transformers, APScheduler, SQLite, React 18, Vite, TailwindCSS

---

## Task 1: 项目骨架 & 依赖

**Files:**
- Create: `backend/requirements.txt`
- Create: `config.yaml`
- Create: `backend/__init__.py`

**Step 1: 创建 requirements.txt**

```
fastapi==0.115.0
uvicorn[standard]==0.30.0
feedparser==6.0.11
playwright==1.44.0
beautifulsoup4==4.12.3
requests==2.32.3
sentence-transformers==3.0.1
apscheduler==3.10.4
pyyaml==6.0.1
anthropic==0.30.0
openai==1.40.0
python-dotenv==1.0.1
aiohttp==3.9.5
websockets==12.0
```

**Step 2: 创建 config.yaml**

```yaml
llm:
  provider: claude          # claude | openai | ollama
  model: claude-sonnet-4-6
  api_key: ""               # 留空则读 .env

collection:
  max_per_source: 10        # 每个信源最多抓取条数
  timeout_seconds: 30

dedup:
  semantic_threshold: 0.85  # 语义相似度阈值

scheduler:
  enabled: true
  cron: "0 8 * * *"         # 每天08:00自动采集

database:
  path: "data/news_radar.db"

company:
  profile: |
    公司专注企业数字化转型，主营协同办公、智慧渠道、智算服务与数据智能。
    构建 Rich AICloud（AI原生云）、Rich AIBox（一站式AI应用开发平台）及垂直行业大模型应用全栈服务体系。
```

**Step 3: 安装依赖**

```bash
cd D:/AI/ClaudeProject/ai-news-radar
pip install -r backend/requirements.txt
playwright install chromium
```

Expected: 所有包安装成功，无错误。

**Step 4: Commit**

```bash
git init
git add .
git commit -m "chore: project scaffold and dependencies"
```

---

## Task 2: 数据库模块

**Files:**
- Create: `backend/db.py`
- Create: `tests/test_db.py`

**Step 1: 写失败测试**

```python
# tests/test_db.py
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
```

**Step 2: 运行确认失败**

```bash
python -m pytest tests/test_db.py -v
```

Expected: `ModuleNotFoundError: No module named 'backend.db'`

**Step 3: 实现 db.py**

```python
# backend/db.py
import sqlite3
import os
from typing import List, Dict, Any

class Database:
    def __init__(self, path: str = "data/news_radar.db"):
        self.path = path
        if path != ":memory:":
            os.makedirs(os.path.dirname(path), exist_ok=True)

    def _conn(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def init(self):
        with self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS news (
                    id           TEXT PRIMARY KEY,
                    url          TEXT UNIQUE,
                    title        TEXT,
                    summary      TEXT,
                    full_text    TEXT,
                    source_name  TEXT,
                    source_tier  INTEGER,
                    institution  TEXT,
                    indicator    TEXT,
                    score        REAL DEFAULT 0,
                    published_at TEXT,
                    collected_at TEXT
                );
                CREATE TABLE IF NOT EXISTS reports (
                    id            TEXT PRIMARY KEY,
                    created_at    TEXT,
                    trigger       TEXT,
                    top10_ids     TEXT,
                    opportunities TEXT,
                    signals       TEXT,
                    llm_provider  TEXT,
                    llm_model     TEXT
                );
            """)

    def upsert_news(self, news: Dict[str, Any]):
        with self._conn() as conn:
            conn.execute("""
                INSERT OR IGNORE INTO news
                (id,url,title,summary,full_text,source_name,source_tier,
                 institution,indicator,score,published_at,collected_at)
                VALUES (:id,:url,:title,:summary,:full_text,:source_name,
                        :source_tier,:institution,:indicator,:score,
                        :published_at,:collected_at)
            """, news)

    def update_scores(self, scores: Dict[str, float]):
        with self._conn() as conn:
            for news_id, score in scores.items():
                conn.execute("UPDATE news SET score=? WHERE id=?", (score, news_id))

    def get_recent_news(self, limit: int = 100) -> List[Dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM news ORDER BY collected_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    def get_news_by_ids(self, ids: List[str]) -> List[Dict]:
        placeholders = ",".join("?" * len(ids))
        with self._conn() as conn:
            rows = conn.execute(
                f"SELECT * FROM news WHERE id IN ({placeholders})", ids
            ).fetchall()
        return [dict(r) for r in rows]

    def save_report(self, report: Dict[str, Any]):
        with self._conn() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO reports
                (id,created_at,trigger,top10_ids,opportunities,signals,llm_provider,llm_model)
                VALUES (:id,:created_at,:trigger,:top10_ids,:opportunities,:signals,
                        :llm_provider,:llm_model)
            """, report)

    def get_reports(self, limit: int = 20) -> List[Dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM reports ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    def get_report_by_id(self, report_id: str) -> Dict | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM reports WHERE id=?", (report_id,)
            ).fetchone()
        return dict(row) if row else None
```

**Step 4: 运行测试确认通过**

```bash
python -m pytest tests/test_db.py -v
```

Expected: 3 tests PASS

**Step 5: Commit**

```bash
git add backend/db.py tests/test_db.py
git commit -m "feat: database module with news and reports tables"
```

---

## Task 3: LLM Provider 抽象层

**Files:**
- Create: `backend/llm/__init__.py`
- Create: `backend/llm/base.py`
- Create: `backend/llm/claude.py`
- Create: `backend/llm/openai_provider.py`
- Create: `backend/llm/ollama.py`
- Create: `backend/llm/factory.py`
- Create: `tests/test_llm_factory.py`

**Step 1: 写失败测试**

```python
# tests/test_llm_factory.py
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from backend.llm.factory import create_llm_provider
from backend.llm.base import BaseLLMProvider

def test_factory_returns_provider():
    config = {"provider": "claude", "model": "claude-sonnet-4-6", "api_key": "test"}
    provider = create_llm_provider(config)
    assert isinstance(provider, BaseLLMProvider)
    assert provider.model == "claude-sonnet-4-6"

def test_factory_unknown_provider_raises():
    import pytest
    with pytest.raises(ValueError, match="Unknown provider"):
        create_llm_provider({"provider": "unknown", "model": "x", "api_key": ""})
```

**Step 2: 运行确认失败**

```bash
python -m pytest tests/test_llm_factory.py -v
```

**Step 3: 实现 LLM 层**

```python
# backend/llm/base.py
from abc import ABC, abstractmethod

class BaseLLMProvider(ABC):
    def __init__(self, model: str, api_key: str):
        self.model = model
        self.api_key = api_key

    @abstractmethod
    def chat(self, system: str, user: str) -> str:
        """发送消息，返回文本响应"""
        pass
```

```python
# backend/llm/claude.py
import anthropic
from .base import BaseLLMProvider

class ClaudeProvider(BaseLLMProvider):
    def chat(self, system: str, user: str) -> str:
        client = anthropic.Anthropic(api_key=self.api_key)
        msg = client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=system,
            messages=[{"role": "user", "content": user}]
        )
        return msg.content[0].text
```

```python
# backend/llm/openai_provider.py
from openai import OpenAI
from .base import BaseLLMProvider

class OpenAIProvider(BaseLLMProvider):
    def chat(self, system: str, user: str) -> str:
        client = OpenAI(api_key=self.api_key)
        resp = client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ]
        )
        return resp.choices[0].message.content
```

```python
# backend/llm/ollama.py
import requests
from .base import BaseLLMProvider

class OllamaProvider(BaseLLMProvider):
    def __init__(self, model: str, api_key: str = "", base_url: str = "http://localhost:11434"):
        super().__init__(model, api_key)
        self.base_url = base_url

    def chat(self, system: str, user: str) -> str:
        resp = requests.post(f"{self.base_url}/api/chat", json={
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
        })
        return resp.json()["message"]["content"]
```

```python
# backend/llm/factory.py
from .base import BaseLLMProvider
from .claude import ClaudeProvider
from .openai_provider import OpenAIProvider
from .ollama import OllamaProvider

def create_llm_provider(config: dict) -> BaseLLMProvider:
    provider = config.get("provider", "claude")
    model = config.get("model", "")
    api_key = config.get("api_key", "")
    if provider == "claude":
        return ClaudeProvider(model, api_key)
    elif provider == "openai":
        return OpenAIProvider(model, api_key)
    elif provider == "ollama":
        return OllamaProvider(model)
    else:
        raise ValueError(f"Unknown provider: {provider}")
```

```python
# backend/llm/__init__.py
from .factory import create_llm_provider
```

**Step 4: 运行测试**

```bash
python -m pytest tests/test_llm_factory.py -v
```

Expected: 2 tests PASS

**Step 5: Commit**

```bash
git add backend/llm/ tests/test_llm_factory.py
git commit -m "feat: LLM provider abstraction (Claude/OpenAI/Ollama)"
```

---

## Task 4: 信源配置表

**Files:**
- Create: `backend/collector/sources.yaml`
- Create: `backend/collector/__init__.py`

**Step 1: 创建 sources.yaml**

```yaml
sources:
  # === 学术引领力 (weight: 37) ===
  - name: OpenAI Research Blog
    institution: OpenAI
    tier: 1
    indicator: academic
    type: rss
    url: https://openai.com/blog/rss.xml

  - name: Google DeepMind Blog
    institution: DeepMind
    tier: 1
    indicator: academic
    type: rss
    url: https://deepmind.google/blog/rss.xml

  - name: Anthropic Research
    institution: Anthropic
    tier: 1
    indicator: academic
    type: rss
    url: https://www.anthropic.com/rss.xml

  - name: Microsoft Research Blog
    institution: Microsoft
    tier: 1
    indicator: academic
    type: rss
    url: https://www.microsoft.com/en-us/research/feed/

  - name: arXiv cs.AI (每日)
    institution: arXiv
    tier: 1
    indicator: academic
    type: rss
    url: https://rss.arxiv.org/rss/cs.AI

  - name: arXiv cs.LG (每日)
    institution: arXiv
    tier: 1
    indicator: academic
    type: rss
    url: https://rss.arxiv.org/rss/cs.LG

  - name: 智谱AI官方博客
    institution: 智谱AI
    tier: 1
    indicator: academic
    type: rss
    url: https://zhipuai.cn/rss.xml

  - name: 智源研究院
    institution: 智源研究院
    tier: 1
    indicator: academic
    type: scrape
    url: https://www.baai.ac.cn/news.html
    selector: ".news-item"

  - name: DeepSeek官网动态
    institution: DeepSeek
    tier: 1
    indicator: academic
    type: scrape
    url: https://www.deepseek.com/
    selector: "article"

  # === 产业转化力 (weight: 32) ===
  - name: Hugging Face Blog
    institution: Hugging Face
    tier: 1
    indicator: industry
    type: rss
    url: https://huggingface.co/blog/feed.xml

  - name: GitHub Trending (AI)
    institution: GitHub
    tier: 1
    indicator: industry
    type: api
    url: https://api.github.com/search/repositories?q=topic:ai+topic:llm&sort=updated&order=desc

  - name: 阿里达摩院
    institution: 阿里
    tier: 1
    indicator: industry
    type: rss
    url: https://damo.alibaba.com/rss

  - name: 字节跳动AI
    institution: 字节跳动
    tier: 2
    indicator: industry
    type: scrape
    url: https://www.volcengine.com/news
    selector: ".news-card"

  # === 资本与生态力 (weight: 12) ===
  - name: Crunchbase AI新闻
    institution: Crunchbase
    tier: 1
    indicator: capital
    type: rss
    url: https://news.crunchbase.com/feed/

  # === Agent化转型 (weight: 10) ===
  - name: LangChain Blog
    institution: LangChain
    tier: 2
    indicator: agent
    type: rss
    url: https://blog.langchain.dev/rss/

  - name: AutoGen (Microsoft)
    institution: Microsoft
    tier: 1
    indicator: agent
    type: rss
    url: https://microsoft.github.io/autogen/blog/rss.xml

  # === 前沿战略力 (weight: 9) ===
  - name: MIT Technology Review AI
    institution: MIT Tech Review
    tier: 2
    indicator: frontier
    type: rss
    url: https://www.technologyreview.com/feed/

  - name: The Batch (DeepLearning.AI)
    institution: DeepLearning.AI
    tier: 2
    indicator: frontier
    type: rss
    url: https://www.deeplearning.ai/the-batch/feed/

  # === 国内二级信源 ===
  - name: 量子位
    institution: 量子位
    tier: 2
    indicator: academic
    type: rss
    url: https://www.qbitai.com/feed

  - name: 机器之心
    institution: 机器之心
    tier: 2
    indicator: academic
    type: rss
    url: https://www.jiqizhixin.com/rss
```

**Step 2: Commit**

```bash
git add backend/collector/sources.yaml backend/collector/__init__.py
git commit -m "feat: news sources configuration (20 sources)"
```

---

## Task 5: RSS 采集器

**Files:**
- Create: `backend/collector/rss.py`
- Create: `tests/test_rss_collector.py`

**Step 1: 写失败测试（使用真实公开RSS）**

```python
# tests/test_rss_collector.py
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from backend.collector.rss import RSSCollector

def test_collect_returns_list():
    source = {
        "name": "Test RSS",
        "institution": "Test",
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
```

**Step 2: 运行确认失败**

```bash
python -m pytest tests/test_rss_collector.py -v
```

**Step 3: 实现 rss.py**

```python
# backend/collector/rss.py
import feedparser
import hashlib
from datetime import datetime, timezone
from typing import List, Dict, Any

class RSSCollector:
    def __init__(self, max_per_source: int = 10, timeout: int = 30):
        self.max_per_source = max_per_source
        self.timeout = timeout

    def collect(self, source: Dict[str, Any]) -> List[Dict]:
        try:
            feed = feedparser.parse(source["url"])
            items = []
            for entry in feed.entries[:self.max_per_source]:
                url = entry.get("link", "")
                if not url:
                    continue
                news_id = hashlib.md5(url.encode()).hexdigest()
                published = self._parse_date(entry)
                items.append({
                    "id": news_id,
                    "url": url,
                    "title": entry.get("title", "").strip(),
                    "summary": entry.get("summary", "")[:500].strip(),
                    "full_text": entry.get("content", [{}])[0].get("value",
                                 entry.get("summary", ""))[:3000],
                    "source_name": source["name"],
                    "source_tier": source["tier"],
                    "institution": source["institution"],
                    "indicator": source["indicator"],
                    "score": 0.0,
                    "published_at": published,
                    "collected_at": datetime.now(timezone.utc).isoformat(),
                })
            return items
        except Exception as e:
            print(f"[RSS] Error collecting {source['name']}: {e}")
            return []

    def _parse_date(self, entry) -> str:
        for field in ("published_parsed", "updated_parsed"):
            t = entry.get(field)
            if t:
                try:
                    return datetime(*t[:6], tzinfo=timezone.utc).isoformat()
                except Exception:
                    pass
        return datetime.now(timezone.utc).isoformat()
```

**Step 4: 运行测试**

```bash
python -m pytest tests/test_rss_collector.py -v
```

Expected: 1 test PASS（需要网络连接）

**Step 5: Commit**

```bash
git add backend/collector/rss.py tests/test_rss_collector.py
git commit -m "feat: RSS news collector with metadata tagging"
```

---

## Task 6: 去重模块（URL + 语义）

**Files:**
- Create: `backend/deduplicator.py`
- Create: `tests/test_deduplicator.py`

**Step 1: 写失败测试**

```python
# tests/test_deduplicator.py
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
        make_news("a1", "https://example.com/1", "GPT-5发布"),  # 同URL
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
```

**Step 2: 运行确认失败**

```bash
python -m pytest tests/test_deduplicator.py -v
```

**Step 3: 实现 deduplicator.py**

```python
# backend/deduplicator.py
from typing import List, Dict, Set
import numpy as np

class Deduplicator:
    def __init__(self, semantic_threshold: float = 0.85):
        self.threshold = semantic_threshold
        self._model = None  # 懒加载，避免启动慢

    def _get_model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
        return self._model

    def deduplicate(self, news_list: List[Dict], existing_ids: Set[str]) -> List[Dict]:
        # 第一层：过滤已有ID（URL哈希去重）
        seen_ids = set(existing_ids)
        unique = []
        for n in news_list:
            if n["id"] not in seen_ids:
                seen_ids.add(n["id"])
                unique.append(n)

        if len(unique) <= 1:
            return unique

        # 第二层：语义去重
        texts = [n["title"] + " " + n.get("summary", "") for n in unique]
        model = self._get_model()
        embeddings = model.encode(texts, convert_to_numpy=True)

        # 归一化
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        embeddings = embeddings / np.maximum(norms, 1e-9)

        # 按分数降序排列，优先保留高分
        indexed = sorted(enumerate(unique), key=lambda x: (
            -x[1].get("score", 0),
            -(x[1].get("source_tier") == 1),
        ))

        kept_indices = []
        removed = set()

        for i, (orig_idx, news) in enumerate(indexed):
            if orig_idx in removed:
                continue
            kept_indices.append(orig_idx)
            # 与后续比较
            for j, (other_idx, _) in enumerate(indexed[i+1:], i+1):
                if other_idx in removed:
                    continue
                sim = float(np.dot(embeddings[orig_idx], embeddings[other_idx]))
                if sim >= self.threshold:
                    removed.add(other_idx)

        return [unique[i] for i in sorted(kept_indices)]
```

**Step 4: 运行测试**

```bash
python -m pytest tests/test_deduplicator.py -v
```

Expected: 3 tests PASS（第一次运行会下载模型，约120MB）

**Step 5: Commit**

```bash
git add backend/deduplicator.py tests/test_deduplicator.py
git commit -m "feat: dual-layer deduplication (URL hash + semantic similarity)"
```

---

## Task 7: 权重评分模块

**Files:**
- Create: `backend/ranker.py`
- Create: `tests/test_ranker.py`

**Step 1: 写失败测试**

```python
# tests/test_ranker.py
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from backend.ranker import Ranker
from datetime import datetime, timezone, timedelta

def make_news(indicator, tier, published_hours_ago=1):
    published = (datetime.now(timezone.utc) - timedelta(hours=published_hours_ago)).isoformat()
    return {"indicator": indicator, "source_tier": tier, "published_at": published}

def test_academic_scores_higher_than_frontier():
    ranker = Ranker()
    academic = make_news("academic", 1)
    frontier = make_news("frontier", 1)
    assert ranker.score(academic) > ranker.score(frontier)

def test_tier1_scores_higher_than_tier2():
    ranker = Ranker()
    tier1 = make_news("academic", 1)
    tier2 = make_news("academic", 2)
    assert ranker.score(tier1) > ranker.score(tier2)

def test_fresh_news_scores_higher_than_old():
    ranker = Ranker()
    fresh = make_news("academic", 1, published_hours_ago=1)
    old = make_news("academic", 1, published_hours_ago=72)
    assert ranker.score(fresh) > ranker.score(old)

def test_rank_returns_top_n():
    ranker = Ranker()
    news_list = [make_news("academic", 1, i) for i in range(50)]
    top = ranker.rank(news_list, top_n=30)
    assert len(top) == 30
```

**Step 2: 运行确认失败**

```bash
python -m pytest tests/test_ranker.py -v
```

**Step 3: 实现 ranker.py**

```python
# backend/ranker.py
import math
from datetime import datetime, timezone
from typing import List, Dict, Any

WEIGHTS = {
    "academic": 37,
    "industry": 32,
    "capital":  12,
    "agent":    10,
    "frontier":  9,
}

class Ranker:
    def score(self, news: Dict[str, Any]) -> float:
        base = WEIGHTS.get(news.get("indicator", "frontier"), 9)
        tier_mult = 1.0 if news.get("source_tier", 2) == 1 else 0.6
        recency = self._recency(news.get("published_at", ""))
        return base * tier_mult * recency

    def _recency(self, published_at: str) -> float:
        try:
            pub = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
            if pub.tzinfo is None:
                pub = pub.replace(tzinfo=timezone.utc)
            hours_ago = (datetime.now(timezone.utc) - pub).total_seconds() / 3600
            # 48h内线性从1.0到0.5，之后指数衰减
            if hours_ago <= 48:
                return 1.0 - 0.5 * (hours_ago / 48)
            return 0.5 * math.exp(-0.01 * (hours_ago - 48))
        except Exception:
            return 0.5

    def rank(self, news_list: List[Dict], top_n: int = 30) -> List[Dict]:
        scored = []
        for news in news_list:
            s = self.score(news)
            scored.append({**news, "score": s})
        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:top_n]
```

**Step 4: 运行测试**

```bash
python -m pytest tests/test_ranker.py -v
```

Expected: 4 tests PASS

**Step 5: Commit**

```bash
git add backend/ranker.py tests/test_ranker.py
git commit -m "feat: weighted scoring ranker with recency decay"
```

---

## Task 8: LLM 分析模块

**Files:**
- Create: `backend/analyzer.py`
- Create: `tests/test_analyzer.py`

**Step 1: 写失败测试（使用 mock LLM）**

```python
# tests/test_analyzer.py
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from backend.analyzer import Analyzer
from backend.llm.base import BaseLLMProvider

class MockLLM(BaseLLMProvider):
    def __init__(self):
        super().__init__("mock", "")
    def chat(self, system: str, user: str) -> str:
        # 模拟LLM返回固定JSON
        if "选出" in user:
            return json.dumps({"selected_ids": ["id1","id2","id3"], "reasons": {}})
        return json.dumps({
            "opportunities": {"id1": "公司可接入此技术强化AIBox能力"},
            "signals": ["信号1", "信号2", "信号3"]
        })

def make_news(id_):
    return {"id": id_, "title": f"新闻{id_}", "summary": "摘要",
            "full_text": "全文", "score": 50.0, "url": f"https://ex.com/{id_}",
            "source_name": "Test", "institution": "Test", "indicator": "academic"}

def test_analyze_returns_report_structure():
    news_list = [make_news(f"id{i}") for i in range(1, 4)]
    analyzer = Analyzer(llm=MockLLM(), company_profile="公司是一家AI公司")
    result = analyzer.analyze(news_list)
    assert "top10" in result
    assert "opportunities" in result
    assert "signals" in result
    assert isinstance(result["signals"], list)
```

**Step 2: 运行确认失败**

```bash
python -m pytest tests/test_analyzer.py -v
```

**Step 3: 实现 analyzer.py**

```python
# backend/analyzer.py
import json
from typing import List, Dict, Any
from backend.llm.base import BaseLLMProvider

SYSTEM_PROMPT = """你是一位资深AI产业分析师，专注于挖掘AI前沿动态对企业的战略价值。
分析时请严格基于提供的新闻内容，不要虚构数据。
输出必须是合法的JSON格式。"""

class Analyzer:
    def __init__(self, llm: BaseLLMProvider, company_profile: str):
        self.llm = llm
        self.company_profile = company_profile

    def analyze(self, news_list: List[Dict]) -> Dict[str, Any]:
        if not news_list:
            return {"top10": [], "opportunities": {}, "signals": []}

        # Step 1: 选出 Top10
        top10 = self._select_top10(news_list)

        # Step 2: 挖掘公司业务机会
        opportunities, signals = self._mine_opportunities(top10)

        return {
            "top10": top10,
            "opportunities": opportunities,
            "signals": signals,
        }

    def _select_top10(self, news_list: List[Dict]) -> List[Dict]:
        n = min(10, len(news_list))
        if len(news_list) <= 10:
            return news_list

        summaries = "\n".join(
            f"[{i+1}] ID:{n['id']} 来源:{n['source_name']} 得分:{n['score']:.1f}\n标题:{n['title']}\n摘要:{n['summary'][:200]}"
            for i, n in enumerate(news_list)
        )
        prompt = f"""以下是 {len(news_list)} 条AI新闻，请选出最有价值的{n}条。
评选标准：技术突破性、产业影响力、时效性、对企业决策的参考价值。

{summaries}

请返回JSON格式：
{{
  "selected_ids": ["id1", "id2", ...],
  "reasons": {{"id1": "选择原因"}}
}}"""
        try:
            resp = self.llm.chat(SYSTEM_PROMPT, prompt)
            data = self._parse_json(resp)
            selected_ids = data.get("selected_ids", [])
            id_map = {n["id"]: n for n in news_list}
            return [id_map[sid] for sid in selected_ids if sid in id_map][:10]
        except Exception as e:
            print(f"[Analyzer] select_top10 error: {e}")
            return news_list[:10]

    def _mine_opportunities(self, top10: List[Dict]):
        if not top10:
            return {}, []

        news_text = "\n\n".join(
            f"【新闻{i+1}】ID:{n['id']}\n标题:{n['title']}\n来源:{n['source_name']}\n内容:{n['full_text'][:800]}"
            for i, n in enumerate(top10)
        )
        prompt = f"""公司背景：
{self.company_profile}

以下是本期Top10 AI新闻：
{news_text}

请分析每条新闻对公司的业务机会和战略启示，并总结3个最重要的战略信号。

返回JSON格式：
{{
  "opportunities": {{
    "新闻ID": "对公司的具体业务机会或战略启示（1-2句）"
  }},
  "signals": ["战略信号1", "战略信号2", "战略信号3"]
}}"""
        try:
            resp = self.llm.chat(SYSTEM_PROMPT, prompt)
            data = self._parse_json(resp)
            return data.get("opportunities", {}), data.get("signals", [])
        except Exception as e:
            print(f"[Analyzer] mine_opportunities error: {e}")
            return {}, []

    def _parse_json(self, text: str) -> Dict:
        # 兼容LLM在JSON外包裹markdown代码块的情况
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1])
        return json.loads(text)
```

**Step 4: 运行测试**

```bash
python -m pytest tests/test_analyzer.py -v
```

Expected: 1 test PASS

**Step 5: Commit**

```bash
git add backend/analyzer.py tests/test_analyzer.py
git commit -m "feat: LLM analyzer for top10 selection and company opportunity mining"
```

---

## Task 9: Pipeline 主流程 & 调度器

**Files:**
- Create: `backend/pipeline.py`
- Create: `backend/scheduler.py`

**Step 1: 实现 pipeline.py**

```python
# backend/pipeline.py
import uuid
import yaml
import os
import json
from datetime import datetime, timezone
from typing import Optional

from backend.db import Database
from backend.collector.rss import RSSCollector
from backend.deduplicator import Deduplicator
from backend.ranker import Ranker
from backend.analyzer import Analyzer
from backend.llm.factory import create_llm_provider

def load_sources():
    path = os.path.join(os.path.dirname(__file__), "collector", "sources.yaml")
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)["sources"]

class Pipeline:
    def __init__(self, config: dict, db: Database):
        self.config = config
        self.db = db
        self.rss_collector = RSSCollector(
            max_per_source=config["collection"]["max_per_source"],
            timeout=config["collection"]["timeout_seconds"],
        )
        self.dedup = Deduplicator(
            semantic_threshold=config["dedup"]["semantic_threshold"]
        )
        self.ranker = Ranker()
        llm = create_llm_provider(config["llm"])
        self.analyzer = Analyzer(llm=llm, company_profile=config["company"]["profile"])
        self.sources = load_sources()

    def run(self, trigger: str = "manual", progress_callback=None) -> dict:
        def emit(msg):
            if progress_callback:
                progress_callback(msg)
            print(f"[Pipeline] {msg}")

        emit("开始采集新闻...")
        all_news = []
        existing_ids = {n["id"] for n in self.db.get_recent_news(limit=500)}

        for source in self.sources:
            emit(f"采集: {source['name']}")
            if source["type"] == "rss":
                items = self.rss_collector.collect(source)
            else:
                items = []  # scraper在Task10实现
            all_news.extend(items)

        emit(f"采集完成，共 {len(all_news)} 条原始新闻")

        emit("去重中...")
        unique_news = self.dedup.deduplicate(all_news, existing_ids=existing_ids)
        emit(f"去重后剩余 {len(unique_news)} 条")

        emit("评分排序...")
        ranked = self.ranker.rank(unique_news, top_n=30)

        # 存入数据库
        for news in unique_news:
            self.db.upsert_news(news)
        score_map = {n["id"]: n["score"] for n in ranked}
        self.db.update_scores(score_map)

        emit("LLM分析中...")
        analysis = self.analyzer.analyze(ranked)

        # 保存报告
        report_id = str(uuid.uuid4())
        report = {
            "id": report_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "trigger": trigger,
            "top10_ids": json.dumps([n["id"] for n in analysis["top10"]]),
            "opportunities": json.dumps(analysis["opportunities"], ensure_ascii=False),
            "signals": json.dumps(analysis["signals"], ensure_ascii=False),
            "llm_provider": self.config["llm"]["provider"],
            "llm_model": self.config["llm"]["model"],
        }
        self.db.save_report(report)
        emit(f"完成！报告ID: {report_id}")
        return report
```

**Step 2: 实现 scheduler.py**

```python
# backend/scheduler.py
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

class NewsScheduler:
    def __init__(self, pipeline_factory, cron_expr: str = "0 8 * * *"):
        self.scheduler = BackgroundScheduler()
        self.pipeline_factory = pipeline_factory
        self.cron_expr = cron_expr

    def start(self):
        parts = self.cron_expr.split()
        trigger = CronTrigger(
            minute=parts[0], hour=parts[1],
            day=parts[2], month=parts[3], day_of_week=parts[4]
        )
        self.scheduler.add_job(
            self._run_job, trigger, id="news_collection", replace_existing=True
        )
        self.scheduler.start()

    def _run_job(self):
        pipeline = self.pipeline_factory()
        pipeline.run(trigger="scheduled")

    def shutdown(self):
        self.scheduler.shutdown()
```

**Step 3: Commit**

```bash
git add backend/pipeline.py backend/scheduler.py
git commit -m "feat: pipeline orchestration and APScheduler integration"
```

---

## Task 10: FastAPI 后端

**Files:**
- Create: `backend/main.py`

**Step 1: 实现 main.py**

```python
# backend/main.py
import json
import yaml
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, BackgroundTasks, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from typing import List

from backend.db import Database
from backend.pipeline import Pipeline
from backend.scheduler import NewsScheduler

# 加载配置
with open("config.yaml", encoding="utf-8") as f:
    CONFIG = yaml.safe_load(f)

db = Database(CONFIG["database"]["path"])
db.init()

pipeline: Pipeline | None = None
scheduler: NewsScheduler | None = None
active_ws: list[WebSocket] = []

def get_pipeline():
    return Pipeline(CONFIG, db)

@asynccontextmanager
async def lifespan(app: FastAPI):
    global pipeline, scheduler
    pipeline = get_pipeline()
    if CONFIG["scheduler"]["enabled"]:
        scheduler = NewsScheduler(get_pipeline, CONFIG["scheduler"]["cron"])
        scheduler.start()
    yield
    if scheduler:
        scheduler.shutdown()

app = FastAPI(title="AI News Radar", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# --- WebSocket for progress ---
@app.websocket("/ws/progress")
async def ws_progress(websocket: WebSocket):
    await websocket.accept()
    active_ws.append(websocket)
    try:
        while True:
            await asyncio.sleep(30)
    except Exception:
        pass
    finally:
        active_ws.remove(websocket)

async def broadcast(msg: str):
    for ws in list(active_ws):
        try:
            await ws.send_text(msg)
        except Exception:
            active_ws.remove(ws)

# --- API Routes ---
@app.post("/api/collect")
async def trigger_collection(background_tasks: BackgroundTasks):
    def run():
        p = get_pipeline()
        def cb(msg):
            asyncio.run(broadcast(msg))
        p.run(trigger="manual", progress_callback=cb)
    background_tasks.add_task(run)
    return {"status": "started"}

@app.get("/api/reports")
def list_reports(limit: int = 20):
    return db.get_reports(limit=limit)

@app.get("/api/reports/{report_id}")
def get_report(report_id: str):
    report = db.get_report_by_id(report_id)
    if not report:
        return JSONResponse({"error": "not found"}, status_code=404)
    top10_ids = json.loads(report["top10_ids"])
    news_items = db.get_news_by_ids(top10_ids)
    opportunities = json.loads(report["opportunities"])
    signals = json.loads(report["signals"])
    # 合并机会信息到新闻
    for n in news_items:
        n["opportunity"] = opportunities.get(n["id"], "")
    return {**report, "news": news_items, "signals": signals}

@app.get("/api/config")
def get_config():
    safe = {k: v for k, v in CONFIG.items() if k != "llm" or "api_key" not in v}
    return safe

@app.put("/api/config")
def update_config(updates: dict):
    CONFIG.update(updates)
    with open("config.yaml", "w", encoding="utf-8") as f:
        yaml.dump(CONFIG, f, allow_unicode=True)
    return {"status": "ok"}

@app.get("/api/sources")
def list_sources():
    from backend.pipeline import load_sources
    return load_sources()
```

**Step 2: 启动测试**

```bash
cd D:/AI/ClaudeProject/ai-news-radar
uvicorn backend.main:app --reload --port 8000
```

访问 http://localhost:8000/docs 确认 API 文档正常显示。

**Step 3: Commit**

```bash
git add backend/main.py
git commit -m "feat: FastAPI backend with collect/reports/config/ws endpoints"
```

---

## Task 11: React 前端

**Files:**
- Create: `frontend/` (Vite + React + TailwindCSS 项目)

**Step 1: 初始化前端项目**

```bash
cd D:/AI/ClaudeProject/ai-news-radar
npm create vite@latest frontend -- --template react
cd frontend
npm install
npm install -D tailwindcss postcss autoprefixer
npx tailwindcss init -p
npm install axios react-router-dom lucide-react
```

**Step 2: 配置 tailwind.config.js**

```js
/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: { extend: {} },
  plugins: [],
}
```

**Step 3: 配置 vite.config.js（API代理）**

```js
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
      '/ws': { target: 'ws://localhost:8000', ws: true }
    }
  }
})
```

**Step 4: 创建核心组件**

`frontend/src/components/NewsCard.jsx`：
```jsx
export function NewsCard({ news, opportunity }) {
  const indicatorColors = {
    academic: 'bg-blue-100 text-blue-800',
    industry: 'bg-green-100 text-green-800',
    capital:  'bg-yellow-100 text-yellow-800',
    agent:    'bg-purple-100 text-purple-800',
    frontier: 'bg-red-100 text-red-800',
  }
  const indicatorLabels = {
    academic: '学术', industry: '产业', capital: '资本',
    agent: 'Agent', frontier: '前沿'
  }

  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-5 hover:shadow-md transition-shadow">
      <div className="flex items-center gap-2 mb-2">
        <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${indicatorColors[news.indicator] || 'bg-gray-100'}`}>
          {indicatorLabels[news.indicator] || news.indicator}
        </span>
        <span className={`text-xs px-2 py-0.5 rounded-full ${news.source_tier === 1 ? 'bg-emerald-50 text-emerald-700' : 'bg-gray-50 text-gray-600'}`}>
          {news.source_tier === 1 ? '一级信源' : '二级信源'}
        </span>
        <span className="text-xs text-gray-400 ml-auto">{news.source_name}</span>
      </div>

      <a href={news.url} target="_blank" rel="noopener noreferrer"
         className="block text-base font-semibold text-gray-900 hover:text-blue-600 mb-2 leading-snug">
        {news.title} ↗
      </a>

      <p className="text-sm text-gray-500 mb-3 line-clamp-2">{news.summary}</p>

      {opportunity && (
        <div className="bg-amber-50 border-l-4 border-amber-400 px-3 py-2 rounded-r">
          <p className="text-xs font-medium text-amber-700 mb-0.5">公司业务机会</p>
          <p className="text-sm text-amber-900">{opportunity}</p>
        </div>
      )}

      <div className="flex justify-between items-center mt-3">
        <span className="text-xs text-gray-400">{news.institution}</span>
        <span className="text-xs font-mono text-gray-400">得分 {(news.score || 0).toFixed(1)}</span>
      </div>
    </div>
  )
}
```

**Step 5: 创建首页 ReportPage**

`frontend/src/pages/ReportPage.jsx`：
```jsx
import { useEffect, useState } from 'react'
import axios from 'axios'
import { NewsCard } from '../components/NewsCard'

export function ReportPage() {
  const [reports, setReports] = useState([])
  const [current, setCurrent] = useState(null)
  const [loading, setLoading] = useState(false)
  const [progress, setProgress] = useState([])
  const [collecting, setCollecting] = useState(false)

  useEffect(() => {
    axios.get('/api/reports').then(r => {
      setReports(r.data)
      if (r.data.length > 0) loadReport(r.data[0].id)
    })
    const ws = new WebSocket(`ws://${location.host}/ws/progress`)
    ws.onmessage = e => setProgress(p => [...p.slice(-20), e.data])
    return () => ws.close()
  }, [])

  const loadReport = id => {
    setLoading(true)
    axios.get(`/api/reports/${id}`).then(r => {
      setCurrent(r.data)
      setLoading(false)
    })
  }

  const triggerCollect = async () => {
    setCollecting(true)
    setProgress([])
    await axios.post('/api/collect')
    setTimeout(() => {
      axios.get('/api/reports').then(r => {
        setReports(r.data)
        if (r.data.length > 0) loadReport(r.data[0].id)
      })
      setCollecting(false)
    }, 5000)
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white border-b px-6 py-4 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-gray-900">AI News Radar</h1>
          <p className="text-sm text-gray-500">公司 · AI一线动态监测</p>
        </div>
        <button onClick={triggerCollect} disabled={collecting}
          className="bg-blue-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50">
          {collecting ? '采集中...' : '立即采集'}
        </button>
      </header>

      <div className="flex">
        {/* 历史报告侧边栏 */}
        <aside className="w-52 bg-white border-r min-h-screen p-4">
          <p className="text-xs font-medium text-gray-500 mb-3 uppercase tracking-wider">历史报告</p>
          {reports.map(r => (
            <button key={r.id} onClick={() => loadReport(r.id)}
              className={`w-full text-left px-3 py-2 rounded-lg text-sm mb-1 ${current?.id === r.id ? 'bg-blue-50 text-blue-700' : 'text-gray-600 hover:bg-gray-50'}`}>
              {r.created_at?.slice(0, 10)}<br/>
              <span className="text-xs opacity-60">{r.trigger === 'manual' ? '手动' : '定时'}</span>
            </button>
          ))}
        </aside>

        {/* 主内容 */}
        <main className="flex-1 p-6">
          {collecting && progress.length > 0 && (
            <div className="bg-blue-50 border border-blue-200 rounded-xl p-4 mb-6">
              <p className="text-sm font-medium text-blue-800 mb-2">采集进度</p>
              {progress.map((msg, i) => (
                <p key={i} className="text-xs text-blue-600">{msg}</p>
              ))}
            </div>
          )}

          {current?.signals?.length > 0 && (
            <div className="bg-gradient-to-r from-indigo-50 to-purple-50 border border-indigo-100 rounded-xl p-5 mb-6">
              <h2 className="font-semibold text-gray-900 mb-3">本期三大战略信号</h2>
              {current.signals.map((s, i) => (
                <div key={i} className="flex gap-3 mb-2">
                  <span className="flex-shrink-0 w-5 h-5 bg-indigo-600 text-white text-xs rounded-full flex items-center justify-center font-bold">{i+1}</span>
                  <p className="text-sm text-gray-700">{s}</p>
                </div>
              ))}
            </div>
          )}

          {loading ? (
            <p className="text-gray-400 text-center py-20">加载中...</p>
          ) : (
            <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
              {current?.news?.map(n => (
                <NewsCard key={n.id} news={n} opportunity={n.opportunity} />
              ))}
            </div>
          )}
        </main>
      </div>
    </div>
  )
}
```

**Step 6: 更新 App.jsx**

```jsx
// frontend/src/App.jsx
import { ReportPage } from './pages/ReportPage'
import './index.css'

export default function App() {
  return <ReportPage />
}
```

**Step 7: 更新 index.css（引入 Tailwind）**

```css
@tailwind base;
@tailwind components;
@tailwind utilities;
```

**Step 8: 启动前端**

```bash
cd frontend
npm run dev
```

访问 http://localhost:5173 确认页面正常显示。

**Step 9: Commit**

```bash
git add frontend/
git commit -m "feat: React dashboard with news cards, signals panel, and collect trigger"
```

---

## Task 12: 配置页面 & 运行验证

**Files:**
- Create: `frontend/src/pages/ConfigPage.jsx`
- Modify: `frontend/src/App.jsx` (加路由)

**Step 1: 添加路由**

```bash
cd frontend && npm install react-router-dom
```

更新 `App.jsx`：
```jsx
import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom'
import { ReportPage } from './pages/ReportPage'
import { ConfigPage } from './pages/ConfigPage'

export default function App() {
  return (
    <BrowserRouter>
      <nav className="bg-white border-b px-6 py-3 flex gap-6">
        <NavLink to="/" className={({isActive}) => isActive ? 'text-blue-600 font-medium text-sm' : 'text-gray-500 text-sm'}>报告</NavLink>
        <NavLink to="/config" className={({isActive}) => isActive ? 'text-blue-600 font-medium text-sm' : 'text-gray-500 text-sm'}>配置</NavLink>
      </nav>
      <Routes>
        <Route path="/" element={<ReportPage />} />
        <Route path="/config" element={<ConfigPage />} />
      </Routes>
    </BrowserRouter>
  )
}
```

**Step 2: 创建 ConfigPage.jsx**

```jsx
import { useEffect, useState } from 'react'
import axios from 'axios'

export function ConfigPage() {
  const [config, setConfig] = useState(null)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    axios.get('/api/config').then(r => setConfig(r.data))
  }, [])

  const save = async () => {
    await axios.put('/api/config', config)
    setSaved(true)
    setTimeout(() => setSaved(false), 2000)
  }

  if (!config) return <p className="p-8 text-gray-400">加载中...</p>

  return (
    <div className="max-w-2xl mx-auto p-8">
      <h2 className="text-lg font-bold mb-6">系统配置</h2>

      <section className="bg-white rounded-xl border p-5 mb-4">
        <h3 className="font-medium mb-3">LLM 配置</h3>
        <div className="space-y-3">
          <div>
            <label className="text-sm text-gray-600">Provider</label>
            <select className="block w-full mt-1 border rounded px-3 py-2 text-sm"
              value={config.llm?.provider}
              onChange={e => setConfig({...config, llm: {...config.llm, provider: e.target.value}})}>
              <option value="claude">Claude (Anthropic)</option>
              <option value="openai">OpenAI</option>
              <option value="ollama">Ollama (本地)</option>
            </select>
          </div>
          <div>
            <label className="text-sm text-gray-600">Model</label>
            <input className="block w-full mt-1 border rounded px-3 py-2 text-sm"
              value={config.llm?.model || ''}
              onChange={e => setConfig({...config, llm: {...config.llm, model: e.target.value}})} />
          </div>
        </div>
      </section>

      <section className="bg-white rounded-xl border p-5 mb-4">
        <h3 className="font-medium mb-3">采集配置</h3>
        <div className="space-y-3">
          <div>
            <label className="text-sm text-gray-600">每信源最大抓取数</label>
            <input type="number" className="block w-32 mt-1 border rounded px-3 py-2 text-sm"
              value={config.collection?.max_per_source || 10}
              onChange={e => setConfig({...config, collection: {...config.collection, max_per_source: +e.target.value}})} />
          </div>
          <div>
            <label className="text-sm text-gray-600">语义去重阈值 (0-1)</label>
            <input type="number" step="0.05" min="0" max="1" className="block w-32 mt-1 border rounded px-3 py-2 text-sm"
              value={config.dedup?.semantic_threshold || 0.85}
              onChange={e => setConfig({...config, dedup: {...config.dedup, semantic_threshold: +e.target.value}})} />
          </div>
        </div>
      </section>

      <section className="bg-white rounded-xl border p-5 mb-6">
        <h3 className="font-medium mb-3">定时任务</h3>
        <div>
          <label className="text-sm text-gray-600">Cron 表达式</label>
          <input className="block w-full mt-1 border rounded px-3 py-2 text-sm font-mono"
            value={config.scheduler?.cron || '0 8 * * *'}
            onChange={e => setConfig({...config, scheduler: {...config.scheduler, cron: e.target.value}})} />
          <p className="text-xs text-gray-400 mt-1">示例: 每天08:00 = "0 8 * * *"</p>
        </div>
      </section>

      <button onClick={save}
        className="bg-blue-600 text-white px-6 py-2 rounded-lg text-sm font-medium hover:bg-blue-700">
        {saved ? '已保存 ✓' : '保存配置'}
      </button>
    </div>
  )
}
```

**Step 3: 端到端测试**

```bash
# 终端1：启动后端
cd D:/AI/ClaudeProject/ai-news-radar
uvicorn backend.main:app --reload --port 8000

# 终端2：启动前端
cd frontend && npm run dev

# 在仪表板点击「立即采集」按钮，观察进度推送，确认报告生成
```

**Step 4: Commit**

```bash
git add frontend/src/pages/ConfigPage.jsx frontend/src/App.jsx
git commit -m "feat: config page with LLM/collection/scheduler settings"
```

---

## Task 13: 启动脚本

**Files:**
- Create: `start.bat`

**Step 1: 创建启动脚本**

```batch
@echo off
echo Starting AI News Radar...
start "Backend" cmd /k "cd /d D:\AI\ClaudeProject\ai-news-radar && uvicorn backend.main:app --port 8000"
timeout /t 3
start "Frontend" cmd /k "cd /d D:\AI\ClaudeProject\ai-news-radar\frontend && npm run dev"
timeout /t 3
start http://localhost:5173
```

**Step 2: Commit**

```bash
git add start.bat
git commit -m "chore: add Windows startup script"
```

---

## 完成验证清单

- [ ] `python -m pytest tests/ -v` 全部通过
- [ ] 后端启动无报错，`/docs` 可访问
- [ ] 前端启动，仪表板正常显示
- [ ] 点击「立即采集」触发 pipeline，WebSocket 推送进度
- [ ] 报告页显示 Top10 新闻，含原文链接跳转
- [ ] 新闻卡片显示公司业务机会
- [ ] 3大战略信号面板正常显示
- [ ] 历史报告可切换查看
- [ ] 配置页可切换 LLM Provider 并保存
