"""内容充实：对摘要缺失或过短的新闻，回源抓取网页正文。"""

import re
import requests
from typing import List, Dict
from bs4 import BeautifulSoup


# 无效摘要的特征（占位符/太短/无意义）
_PLACEHOLDER_PATTERNS = [
    r"点击查看原文",
    r"点击阅读",
    r"阅读全文",
    r"查看更多",
    r"read more",
    r"continue reading",
    r"click here",
]
_PLACEHOLDER_RE = re.compile("|".join(_PLACEHOLDER_PATTERNS), re.IGNORECASE)

# 摘要最少字符数（低于此视为缺失）
MIN_SUMMARY_LEN = 30

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)


def _needs_enrichment(news: Dict) -> bool:
    """判断是否需要内容充实。"""
    summary = (news.get("summary") or "").strip()
    full_text = (news.get("full_text") or "").strip()

    # 无摘要
    if len(summary) < MIN_SUMMARY_LEN and len(full_text) < MIN_SUMMARY_LEN:
        return True

    # 摘要是占位符
    if _PLACEHOLDER_RE.search(summary):
        return True
    if _PLACEHOLDER_RE.search(full_text):
        return True

    return False


def _fetch_article_text(url: str, timeout: int = 15) -> str:
    """抓取网页正文，提取主要文本内容。"""
    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding or "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")

        # 移除无关元素
        for tag in soup.find_all(["script", "style", "nav", "header", "footer", "aside"]):
            tag.decompose()

        # 优先提取 article 标签
        article = soup.find("article")
        if article:
            paragraphs = article.find_all("p")
        else:
            # 回退：取页面所有 <p> 标签
            paragraphs = soup.find_all("p")

        texts = []
        for p in paragraphs:
            text = p.get_text(strip=True)
            if len(text) > 20:  # 过滤太短的段落
                texts.append(text)

        return "\n".join(texts)
    except Exception:
        return ""


def enrich_news_list(news_list: List[Dict], max_enrich: int = 10) -> int:
    """对摘要缺失的新闻回源抓取正文。返回充实成功的条数。"""
    enriched = 0
    for news in news_list:
        if enriched >= max_enrich:
            break
        if not _needs_enrichment(news):
            continue

        url = news.get("url", "")
        if not url:
            continue

        print(f"[Enricher] 补充内容: {news.get('title', '')[:40]}...", flush=True)
        text = _fetch_article_text(url)
        if text and len(text) > MIN_SUMMARY_LEN:
            # 截取前500字作为摘要，前3000字作为全文
            news["summary"] = text[:500]
            news["full_text"] = text[:3000]
            enriched += 1
        else:
            print(f"[Enricher] 抓取失败或内容为空: {url[:60]}", flush=True)

    return enriched
