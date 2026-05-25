import hashlib
import re
import subprocess
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from backend.collector.filters import is_ai_related
from backend.config_utils import effective_proxies
from backend.date_filters import is_within_recent_days


_PW_SCRIPT = r"""
import sys
from playwright.sync_api import sync_playwright

url = sys.argv[1]
ua = sys.argv[2]
timeout = int(sys.argv[3])
proxy_server = sys.argv[4] if len(sys.argv) > 4 else ""

pw = sync_playwright().start()
try:
    _launch_kwargs = {"headless": True}
    if proxy_server:
        _launch_kwargs["proxy"] = {"server": proxy_server}
    browser = pw.chromium.launch(**_launch_kwargs)
    page = browser.new_page(user_agent=ua)
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=timeout)
        page.wait_for_timeout(4000)
        html = page.content()
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stdout.write(html)
    finally:
        page.close()
        browser.close()
finally:
    pw.stop()
"""


class WebScraper:
    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    )

    _JS_REQUIRED_DOMAINS = {
        "zhipuai.cn",
        "deepseek.com",
        "sensetime.com",
        "volcengine.com",
        "damo.alibaba.com",
        "jiqizhixin.com",
        "aibase.com",
    }

    def __init__(self, max_per_source: int = 10, timeout: int = 30, date_window_days: int = 3,
                 proxy_url: str = None):
        self.max_per_source = max_per_source
        self.timeout = timeout
        self.date_window_days = date_window_days
        self.proxy_url = proxy_url
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": self.USER_AGENT})

    def _needs_js(self, url: str) -> bool:
        return any(domain in url for domain in self._JS_REQUIRED_DOMAINS)

    def _fetch_static(self, url: str, proxies=None) -> str:
        resp = self.session.get(url, timeout=self.timeout, proxies=proxies)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding or "utf-8"
        return resp.text

    def _fetch_dynamic(self, url: str, proxy_server: str = "") -> str:
        try:
            result = subprocess.run(
                [sys.executable, "-c", _PW_SCRIPT, url, self.USER_AGENT, str(self.timeout * 1000),
                 proxy_server or ""],
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=self.timeout + 30,
            )
            if result.returncode != 0:
                stderr = result.stderr.strip()
                if "Executable doesn't exist" in stderr or "browserType.launch" in stderr:
                    print("[Scraper] Playwright browser is not installed. Run: playwright install chromium", flush=True)
                else:
                    print(f"[Scraper] Playwright child process error: {stderr[:200]}", flush=True)
                return ""
            return result.stdout
        except subprocess.TimeoutExpired:
            print(f"[Scraper] Playwright timeout: {url}", flush=True)
            return ""
        except Exception as e:
            print(f"[Scraper] Playwright startup failed: {e}", flush=True)
            return ""

    @staticmethod
    def _clean_text(text: str) -> str:
        if not text:
            return ""
        return re.sub(r"\s+", " ", text).strip()

    def _extract_published(self, el) -> str:
        time_tag = el.find("time")
        if time_tag:
            published = time_tag.get("datetime", "") or self._clean_text(time_tag.get_text())
            if published:
                return published

        for tag in el.find_all(["span", "div"], class_=re.compile(r"date|time|publish", re.IGNORECASE)):
            text = self._clean_text(tag.get_text())
            if re.search(r"\d{4}[-/]\d{1,2}[-/]\d{1,2}", text):
                return text

        return ""

    def _parse_items(self, html: str, source: Dict[str, Any]) -> List[Dict]:
        soup = BeautifulSoup(html, "html.parser")
        selector = source.get("selector", "article")
        limit = source.get("max_items", self.max_per_source)

        items = self._extract_from_elements(soup.select(selector), source, limit)
        if items:
            return items

        print(f"[Scraper] {source['name']}: selector '{selector}' returned no results, trying fallback", flush=True)
        return self._fallback_extract(soup, source, limit)

    def _extract_from_elements(self, elements, source: Dict, limit: int) -> List[Dict]:
        items = []
        skipped = 0
        skipped_not_yesterday = 0

        for el in elements:
            if len(items) >= limit:
                break

            link_tag = el.find("a", href=True)
            if not link_tag:
                if el.name == "a" and el.get("href"):
                    link_tag = el
                else:
                    continue

            href = link_tag["href"]
            if href.startswith("/") or not href.startswith("http"):
                href = urljoin(source["url"], href)

            title_tag = el.find(["h1", "h2", "h3", "h4"]) or link_tag
            title = self._clean_text(title_tag.get_text())
            if not title or len(title) < 4:
                continue

            summary_tag = el.find("p")
            summary = self._clean_text(summary_tag.get_text()) if summary_tag else ""

            if source.get('keyword_filter', False) and not is_ai_related(title, summary):
                skipped += 1
                continue

            published = self._extract_published(el)
            if not is_within_recent_days(published, days=self.date_window_days):
                skipped_not_yesterday += 1
                continue

            news_id = hashlib.md5(href.encode()).hexdigest()
            items.append({
                "id": news_id,
                "url": href,
                "title": title[:200],
                "summary": summary[:500],
                "full_text": summary[:3000],
                "source_name": source["name"],
                "source_tier": source["tier"],
                "institution": source["institution"],
                "indicator": source.get("indicator", ""),
                "score": 0.0,
                "published_at": published,
                "collected_at": datetime.now(timezone.utc).isoformat(),
            })

        if skipped:
            print(f"[Scraper] {source['name']}: skipped {skipped} non-AI items", flush=True)
        if skipped_not_yesterday:
            print(f"[Scraper] {source['name']}: skipped {skipped_not_yesterday} out-of-window items", flush=True)
        return items

    def _fallback_extract(self, soup: BeautifulSoup, source: Dict, limit: int) -> List[Dict]:
        # fallback 模式下只能从 <a> 标签反推，上下文不足以可靠判断 AI 相关性，
        # 因此此处不做关键词预筛，交给 scorer 的语义打分过滤噪声。
        items = []
        skipped_not_yesterday = 0
        seen_urls = set()

        for a_tag in soup.select("a[href]"):
            if len(items) >= limit:
                break

            href = a_tag.get("href", "")
            if not href or href == "#" or href.startswith("javascript:"):
                continue
            if href.startswith("/") or not href.startswith("http"):
                href = urljoin(source["url"], href)
            if href in seen_urls:
                continue

            if any(x in href for x in ["/category", "/tag", "/page/", "/login", "/signup", "/about"]):
                continue

            title = self._clean_text(a_tag.get_text())
            if not title or len(title) < 10:
                continue
            if len(title) > 200:
                title = title[:200]

            seen_urls.add(href)

            summary = ""
            parent = a_tag.parent
            if parent:
                p_tag = parent.find("p")
                if p_tag:
                    summary = self._clean_text(p_tag.get_text())[:500]

            published = ""
            if parent:
                time_tag = parent.find("time")
                if time_tag:
                    published = time_tag.get("datetime", "") or self._clean_text(time_tag.get_text())
            if not is_within_recent_days(published, days=self.date_window_days):
                skipped_not_yesterday += 1
                continue

            news_id = hashlib.md5(href.encode()).hexdigest()
            items.append({
                "id": news_id,
                "url": href,
                "title": title,
                "summary": summary,
                "full_text": summary[:3000],
                "source_name": source["name"],
                "source_tier": source["tier"],
                "institution": source["institution"],
                "indicator": source.get("indicator", ""),
                "score": 0.0,
                "published_at": published,
                "collected_at": datetime.now(timezone.utc).isoformat(),
            })

        if skipped_not_yesterday:
            print(f"[Scraper] {source['name']}: fallback skipped {skipped_not_yesterday} out-of-window items", flush=True)
        if items:
            print(f"[Scraper] {source['name']}: fallback extracted {len(items)} items", flush=True)
        return items

    def collect(self, source: Dict[str, Any]) -> List[Dict]:
        url = source["url"]
        use_proxy = source.get("use_proxy", False)
        proxies = effective_proxies(use_proxy, self.proxy_url)
        proxy_server = self.proxy_url if (use_proxy and self.proxy_url) else ""
        try:
            if self._needs_js(url):
                print(f"[Scraper] {source['name']}: using Playwright", flush=True)
                html = self._fetch_dynamic(url, proxy_server)
            else:
                html = self._fetch_static(url, proxies)
                items = self._parse_items(html, source)
                if items:
                    return items
                print(f"[Scraper] {source['name']}: static fetch had no results, falling back to Playwright", flush=True)
                html = self._fetch_dynamic(url, proxy_server)

            if not html:
                return []
            return self._parse_items(html, source)
        except Exception as e:
            print(f"[Scraper] Error collecting {source['name']}: {e}", flush=True)
            return []

    def close(self):
        pass
