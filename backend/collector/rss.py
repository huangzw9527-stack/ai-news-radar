import feedparser
import hashlib
import re
import socket
import urllib.request
from datetime import datetime, timezone
from typing import List, Dict, Any
from backend.collector.filters import is_ai_related
from backend.date_filters import is_within_recent_days

class RSSCollector:
    def __init__(self, max_per_source: int = 10, timeout: int = 30, date_window_days: int = 3,
                 proxy_url: str = None):
        self.max_per_source = max_per_source
        self.timeout = timeout
        self.date_window_days = date_window_days
        self.proxy_url = proxy_url

    @staticmethod
    def _strip_html(text: str) -> str:
        """移除HTML标签和实体，只保留纯文本。"""
        if not text:
            return ""
        # 移除 CDATA
        text = re.sub(r"<!\[CDATA\[.*?\]\]>", "", text, flags=re.DOTALL)
        # 移除 script/style 块
        text = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", text, flags=re.DOTALL | re.IGNORECASE)
        # 移除HTML标签（含多行属性）
        text = re.sub(r"<[^>]*>", "", text, flags=re.DOTALL)
        # 处理常见HTML实体
        text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
        text = text.replace("&quot;", '"').replace("&#39;", "'").replace("&nbsp;", " ")
        text = text.replace("&mdash;", "—").replace("&ndash;", "–")
        # 处理数字实体 &#123;
        text = re.sub(r"&#(\d+);", lambda m: chr(int(m.group(1))), text)
        # 移除剩余的HTML实体
        text = re.sub(r"&[a-zA-Z0-9#]+;", " ", text)
        # 合并多余空白
        text = re.sub(r"\s+", " ", text).strip()
        return text

    # 通用 User-Agent，避免被部分网站拒绝（量子位、InfoQ 等）
    USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

    def collect(self, source: Dict[str, Any]) -> List[Dict]:
        try:
            old_timeout = socket.getdefaulttimeout()
            socket.setdefaulttimeout(self.timeout)
            try:
                # 显式 ProxyHandler：use_proxy=False 时传空 dict 屏蔽环境代理
                if source.get("use_proxy", False) and self.proxy_url:
                    proxy_map = {"http": self.proxy_url, "https": self.proxy_url}
                else:
                    proxy_map = {}
                feed = feedparser.parse(
                    source["url"],
                    request_headers={"User-Agent": self.USER_AGENT},
                    handlers=[urllib.request.ProxyHandler(proxy_map)],
                )
            finally:
                socket.setdefaulttimeout(old_timeout)
            items = []
            limit = source.get("max_items", self.max_per_source)
            skipped = 0
            skipped_not_yesterday = 0
            for entry in feed.entries:
                if len(items) >= limit:
                    break
                url = entry.get("link", "")
                if not url:
                    continue
                title = self._strip_html(entry.get("title", ""))
                raw_summary = entry.get("summary", "")
                summary = self._strip_html(raw_summary)[:500]

                # 仅对标记了 keyword_filter 的综合媒体信源做关键词预筛
                if source.get('keyword_filter', False) and not is_ai_related(title, summary):
                    skipped += 1
                    continue

                news_id = hashlib.md5(url.encode()).hexdigest()
                published = self._parse_date(entry)
                if not is_within_recent_days(published, days=self.date_window_days):
                    skipped_not_yesterday += 1
                    continue
                raw_full = entry.get("content", [{}])[0].get("value", raw_summary)
                items.append({
                    "id": news_id,
                    "url": url,
                    "title": title,
                    "summary": summary,
                    "full_text": self._strip_html(raw_full)[:3000],
                    "source_name": source["name"],
                    "source_tier": source["tier"],
                    "institution": source["institution"],
                    "indicator": source.get("indicator", ""),
                    "score": 0.0,
                    "published_at": published,
                    "collected_at": datetime.now(timezone.utc).isoformat(),
                })
            if skipped:
                print(f"[RSS] {source['name']}: 预筛跳过 {skipped} 条非AI新闻", flush=True)
            if skipped_not_yesterday:
                print(f"[RSS] {source['name']}: skipped {skipped_not_yesterday} out-of-window items", flush=True)
            return items
        except Exception as e:
            print(f"[RSS] Error collecting {source['name']}: {e}", flush=True)
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
