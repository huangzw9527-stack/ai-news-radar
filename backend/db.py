import json
import sqlite3
import os
from typing import List, Dict, Any

class Database:
    def __init__(self, path: str = "data/news_radar.db"):
        self.path = path
        self._memory_conn = None
        if path != ":memory:":
            os.makedirs(os.path.dirname(path), exist_ok=True)
        else:
            # For in-memory databases, keep a single persistent connection
            self._memory_conn = sqlite3.connect(":memory:")
            self._memory_conn.row_factory = sqlite3.Row

    def _conn(self):
        if self._memory_conn is not None:
            return self._memory_conn
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def init(self):
        conn = self._conn()
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
                collected_at TEXT,
                interaction_count INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS reports (
                id            TEXT PRIMARY KEY,
                created_at    TEXT,
                trigger       TEXT,
                top10_ids     TEXT,
                opportunities TEXT,
                signals       TEXT,
                summaries     TEXT,
                keywords      TEXT,
                value_insights TEXT,
                titles_cn     TEXT,
                categories    TEXT,
                impacts       TEXT,
                actions       TEXT,
                briefing      TEXT,
                main_categories TEXT,
                aux_tags      TEXT,
                llm_provider  TEXT,
                llm_model     TEXT
            );
        """)
        self._migrate()

    def _migrate(self):
        """Add new columns if they don't exist (for existing databases)."""
        conn = self._conn()
        # news 表迁移（旧数据库兼容）
        existing_news = {row[1] for row in conn.execute("PRAGMA table_info(news)").fetchall()}
        if "interaction_count" not in existing_news:
            conn.execute("ALTER TABLE news ADD COLUMN interaction_count INTEGER DEFAULT 0")
        existing = {row[1] for row in conn.execute("PRAGMA table_info(reports)").fetchall()}
        for col in ["summaries", "keywords", "value_insights", "titles_cn", "categories",
                    "impacts", "actions", "concepts", "principles", "practices", "briefing",
                    "main_categories", "aux_tags"]:
            if col not in existing:
                conn.execute(f"ALTER TABLE reports ADD COLUMN {col} TEXT")
        conn.commit()

    def upsert_news(self, news: Dict[str, Any]):
        conn = self._conn()
        conn.execute("""
            INSERT OR IGNORE INTO news
            (id,url,title,summary,full_text,source_name,source_tier,
             institution,indicator,score,published_at,collected_at,interaction_count)
            VALUES (:id,:url,:title,:summary,:full_text,:source_name,
                    :source_tier,:institution,:indicator,:score,
                    :published_at,:collected_at,:interaction_count)
        """, {**news, "interaction_count": news.get("interaction_count", 0)})
        conn.commit()

    def update_news_content(self, news_id: str, title: str, summary: str, full_text: str):
        """Update cleaned content for a news item."""
        conn = self._conn()
        conn.execute(
            "UPDATE news SET title=?, summary=?, full_text=? WHERE id=?",
            (title, summary, full_text, news_id)
        )
        conn.commit()

    def update_scores(self, scores: Dict[str, float]):
        conn = self._conn()
        for news_id, score in scores.items():
            conn.execute("UPDATE news SET score=? WHERE id=?", (score, news_id))
        conn.commit()

    def get_recent_news(self, limit: int = 100, days: int = 0) -> List[Dict]:
        """获取最近的新闻。days>0 时只取发布时间在最近 N 天内的。"""
        conn = self._conn()
        if days > 0:
            cutoff = f"-{days} days"
            rows = conn.execute(
                """SELECT * FROM news
                   WHERE published_at >= datetime('now', ?)
                      OR (published_at IS NULL AND collected_at >= datetime('now', ?))
                   ORDER BY published_at DESC LIMIT ?""",
                (cutoff, cutoff, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM news ORDER BY published_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    def get_news_by_date(self, target_date: str, limit: int = 100) -> List[Dict]:
        conn = self._conn()
        rows = conn.execute(
            """SELECT * FROM news
               WHERE substr(published_at, 1, 10) = ?
                  OR (published_at IS NULL AND substr(collected_at, 1, 10) = ?)
               ORDER BY published_at DESC LIMIT ?""",
            (target_date, target_date, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_news_within_days(self, days: int = 3, limit: int = 200) -> List[Dict]:
        """取最近 N 天（按 published_at；为空时退回 collected_at）采集到的新闻。"""
        from datetime import datetime, timedelta, timezone
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()
        conn = self._conn()
        rows = conn.execute(
            """SELECT * FROM news
               WHERE (published_at IS NOT NULL AND substr(published_at, 1, 10) >= ?)
                  OR (published_at IS NULL AND substr(collected_at, 1, 10) >= ?)
               ORDER BY COALESCE(published_at, collected_at) DESC LIMIT ?""",
            (cutoff, cutoff, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_news_by_ids(self, ids: List[str]) -> List[Dict]:
        if not ids:
            return []
        placeholders = ",".join("?" * len(ids))
        conn = self._conn()
        rows = conn.execute(
            f"SELECT * FROM news WHERE id IN ({placeholders})", ids
        ).fetchall()
        return [dict(r) for r in rows]

    def save_report(self, report: Dict[str, Any]):
        conn = self._conn()
        cols = [
            "id", "created_at", "trigger", "top10_ids", "opportunities", "signals",
            "summaries", "keywords", "value_insights", "titles_cn", "categories",
            "impacts", "actions", "concepts", "principles", "practices",
            "briefing", "main_categories", "aux_tags",
            "llm_provider", "llm_model",
        ]
        row = {c: report.get(c) for c in cols}
        placeholders = ",".join(f":{c}" for c in cols)
        conn.execute(
            f"INSERT OR REPLACE INTO reports ({','.join(cols)}) VALUES ({placeholders})",
            row,
        )
        conn.commit()

    def get_reports(self, limit: int = 20) -> List[Dict]:
        conn = self._conn()
        rows = conn.execute(
            "SELECT * FROM reports ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    def delete_report(self, report_id: str):
        conn = self._conn()
        conn.execute("DELETE FROM reports WHERE id=?", (report_id,))
        conn.commit()

    def get_report_by_id(self, report_id: str) -> Dict | None:
        conn = self._conn()
        row = conn.execute(
            "SELECT * FROM reports WHERE id=?", (report_id,)
        ).fetchone()
        return dict(row) if row else None

    def get_used_news_ids(self) -> set:
        """获取所有已在报告中使用过的新闻ID。"""
        conn = self._conn()
        rows = conn.execute("SELECT top10_ids FROM reports").fetchall()
        used = set()
        for row in rows:
            try:
                ids = json.loads(row["top10_ids"] or "[]")
                used.update(ids)
            except (json.JSONDecodeError, TypeError):
                pass
        return used

    def close(self):
        if self._memory_conn is not None:
            self._memory_conn.close()
            self._memory_conn = None
