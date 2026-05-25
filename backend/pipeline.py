import uuid
import yaml
import os
import json
import concurrent.futures
from datetime import datetime, timezone
from typing import Optional, Callable, List, Dict

from backend.db import Database
from backend.collector.rss import RSSCollector
from backend.collector.scraper import WebScraper
from backend.collector.wechat import WechatCollector
from backend.collector.twitter import TwitterCollector
from backend.collector.enricher import enrich_news_list
from backend.deduplicator import Deduplicator
from backend.scorer import Scorer
from backend.analyzer import Analyzer
from backend.selection import select_deep_news
from backend.config_utils import normalize_proxy_config, probe_proxy
from backend.llm.factory import create_llm_provider


def load_config(path: str = "config.yaml") -> dict:
    with open(path, encoding="utf-8") as f:
        return normalize_proxy_config(yaml.safe_load(f))


def load_sources(config: dict = None) -> list:
    """从 config.yaml 加载信源列表（websites + wechat 合并）。"""
    if config is None:
        config = load_config()
    sources_cfg = config.get("sources", {})
    websites = sources_cfg.get("websites", [])
    wechat = sources_cfg.get("wechat", [])
    # wechat 源自动补充 type 字段
    for s in wechat:
        s["type"] = "wechat"
    return websites + wechat


class Pipeline:
    def __init__(self, config: dict, db: Database):
        self.config = config
        self.db = db
        date_window_days = config["collection"].get("date_window_days", 3)
        proxy_url = config.get("sources", {}).get("proxy_url")
        self.rss_collector = RSSCollector(
            max_per_source=config["collection"]["max_per_source"],
            timeout=config["collection"]["timeout_seconds"],
            date_window_days=date_window_days,
            proxy_url=proxy_url,
        )
        self.web_scraper = WebScraper(
            max_per_source=config["collection"]["max_per_source"],
            timeout=config["collection"]["timeout_seconds"],
            date_window_days=date_window_days,
            proxy_url=proxy_url,
        )
        self.wechat_collector = WechatCollector(
            max_per_source=config["collection"]["max_per_source"],
            date_window_days=date_window_days,
            proxy_url=proxy_url,
        )
        twitter_cfg = config.get("sources", {}).get("twitter", {})
        # 把全局 proxy_url 解析成 twitter 子进程消费的 proxy 字段（按 use_proxy）
        twitter_cfg["proxy"] = proxy_url if twitter_cfg.get("use_proxy") else ""
        self.twitter_collector = TwitterCollector(date_window_days=date_window_days)
        self.twitter_cfg = twitter_cfg
        self.date_window_days = date_window_days
        self.dedup = Deduplicator(
            semantic_threshold=config["dedup"]["semantic_threshold"]
        )
        llm = create_llm_provider(config["llm"])
        self.scorer = Scorer(
            llm=create_llm_provider(config["llm"]),
            topics=config.get("topics", []),
            db=db,
        )
        self.analyzer = Analyzer(
            llm=llm,
            topics=config.get("topics", []),
            categories=config.get("categories", []),
        )
        self.sources = load_sources(config)


    def run(self, trigger: str = "manual", progress_callback: Optional[Callable] = None) -> dict:
        def emit(msg: str):
            if progress_callback:
                progress_callback(msg)
            print(f"[Pipeline] {msg}", flush=True)

        # 代理探测：不可达时跳过 use_proxy=True 的海外源
        sources_cfg = self.config.get("sources", {})
        proxy_url = sources_cfg.get("proxy_url")
        probe_timeout = sources_cfg.get("proxy_probe_timeout", 5)
        proxy_available = probe_proxy(proxy_url, timeout=probe_timeout)

        active_sources = self.sources
        if not proxy_available:
            foreign = [s for s in active_sources if s.get("use_proxy")]
            if foreign:
                names = ", ".join(s.get("name", "?") for s in foreign)
                emit(f"代理 {proxy_url} 不可达（{probe_timeout}s 探测无响应），跳过 {len(foreign)} 个海外源: {names}")
            active_sources = [s for s in active_sources if not s.get("use_proxy")]

        twitter_enabled = self.twitter_cfg.get("enabled", False)
        if twitter_enabled and self.twitter_cfg.get("use_proxy") and not proxy_available:
            emit("代理不可达，跳过 Twitter 采集")
            twitter_enabled = False

        emit(f"开始采集新闻（共 {len(active_sources)} 个信源）...")
        all_news = []

        source_timeout = self.config["collection"]["timeout_seconds"]

        # 分离微信源和其他源
        wechat_sources = [s for s in active_sources if s["type"] == "wechat"]
        other_sources = [s for s in active_sources if s["type"] != "wechat"]

        # 采集 RSS / Scrape 源
        for source in other_sources:
            emit(f"采集: {source['name']}")
            try:
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                    if source["type"] == "rss":
                        future = executor.submit(self.rss_collector.collect, source)
                    elif source["type"] == "scrape":
                        future = executor.submit(self.web_scraper.collect, source)
                    else:
                        future = None
                    items = future.result(timeout=source_timeout) if future else []
            except concurrent.futures.TimeoutError:
                emit(f"  → {source['name']}: 超时跳过（>{source_timeout}s）")
                items = []
            except Exception as e:
                emit(f"  → {source['name']}: 采集异常: {e}")
                items = []
            emit(f"  → {source['name']}: {len(items)} 条")
            all_news.extend(items)

        # 采集微信公众号源（在子进程中执行，避免 Windows asyncio 限制）
        if wechat_sources:
            emit(f"采集微信公众号（{len(wechat_sources)} 个）...")
            try:
                wechat_items = self.wechat_collector.collect_all(wechat_sources)
                emit(f"  → 微信公众号: {len(wechat_items)} 条")
                all_news.extend(wechat_items)
            except Exception as e:
                emit(f"  → 微信采集异常: {e}")

        # 采集 Twitter/X 账号动态
        if twitter_enabled:
            emit(f"采集 Twitter/X 账号动态...")
            try:
                twitter_items = self.twitter_collector.collect_all(self.twitter_cfg)
                emit(f"  → Twitter: {len(twitter_items)} 条")
                all_news.extend(twitter_items)
            except Exception as e:
                emit(f"  → Twitter 采集异常: {e}")

        emit(f"采集完成，共 {len(all_news)} 条原始新闻")

        # 批次内去重（不跨数据库，避免二次采集全被过滤）
        emit("去重中...")
        batch_deduped = self.dedup.deduplicate(all_news, existing_ids=set())
        emit(f"批次去重后 {len(batch_deduped)} 条，写入数据库...")

        # 写入新条目（upsert，已有则忽略）
        for news in batch_deduped:
            self.db.upsert_news(news)

        # 取最近 N 天的新闻做评分和分析
        emit(f"评分排序：仅处理最近 {self.date_window_days} 天内的新闻...")
        db_limit = self.config.get("collection", {}).get("db_limit", 300)
        recent_news = self.db.get_news_within_days(days=self.date_window_days, limit=db_limit)

        # 排除已在历史报告中使用过的新闻
        used_ids = self.db.get_used_news_ids()
        before_count = len(recent_news)
        recent_news = [n for n in recent_news if n["id"] not in used_ids]
        if before_count != len(recent_news):
            emit(f"排除已用新闻: {before_count} → {len(recent_news)} 条")

        # 清洗数据库中的HTML残留（历史数据）
        for n in recent_news:
            old_t, old_s, old_f = n.get("title",""), n.get("summary",""), n.get("full_text","")
            n["title"] = RSSCollector._strip_html(old_t)
            n["summary"] = RSSCollector._strip_html(old_s)
            n["full_text"] = RSSCollector._strip_html(old_f)
            if n["title"] != old_t or n["summary"] != old_s or n["full_text"] != old_f:
                self.db.update_news_content(n["id"], n["title"], n["summary"], n["full_text"])

        # 内容充实：对摘要缺失的新闻回源抓取正文
        emit("内容充实: 检查摘要缺失的新闻...")
        enriched_count = enrich_news_list(recent_news, max_enrich=10)
        if enriched_count > 0:
            emit(f"内容充实: 补充了 {enriched_count} 条新闻的正文")
            # 回写数据库
            for n in recent_news:
                self.db.update_news_content(n["id"], n["title"], n["summary"], n["full_text"])

        # 综合评分：时效拦截 → Embedding过滤 → LLM打分 → 关联性排序
        emit(f"综合评分：{len(recent_news)} 条候选（时效+关联性）...")
        all_relevant = self.scorer.score_and_rank(recent_news)
        score_map = {n["id"]: n["score"] for n in all_relevant}
        self.db.update_scores(score_map)

        # 报告级语义去重：批次内去重不跨数据库，跨日采集的同一事件（不同源转发）
        # 直到评分后才会汇聚到一起，这里再做一次以避免报告内重复
        before_report_dedup = len(all_relevant)
        all_relevant = self.dedup.deduplicate(all_relevant, existing_ids=set())
        if len(all_relevant) != before_report_dedup:
            emit(f"报告级去重: {before_report_dedup} → {len(all_relevant)} 条")
        all_relevant.sort(key=lambda n: n.get("score", 0), reverse=True)

        # 深度分析层（前 20 条，含同源限制）+ 扫描层（其余相关条目）
        _DEEP_N = 20
        _DEEP_SOURCE_CAP = 2
        deep_news = select_deep_news(all_relevant, _DEEP_N, _DEEP_SOURCE_CAP)

        deep_ids = {n["id"] for n in deep_news}
        scan_extras = [n for n in all_relevant if n["id"] not in deep_ids]

        emit(f"评分完成: 相关 {len(all_relevant)} 条 → 深度分析 {len(deep_news)} 条 / 扫描层 {len(scan_extras)} 条")
        analysis = self.analyzer.analyze(deep_news, scan_extras=scan_extras)

        # 保存报告
        report_id = str(uuid.uuid4())
        report = {
            "id": report_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "trigger": trigger,
            # 仅记录"真正进入 briefing 展示的"新闻 ID，未展示的留待后续报告复用
            "top10_ids": json.dumps(
                analysis.get("displayed_ids")
                or [n["id"] for n in analysis["news"]]
            ),
            "briefing": json.dumps(analysis.get("briefing", {}), ensure_ascii=False),
            "summaries": json.dumps(analysis.get("summaries", {}), ensure_ascii=False),
            "main_categories": json.dumps(analysis.get("main_categories", {}), ensure_ascii=False),
            "aux_tags": json.dumps(analysis.get("aux_tags", {}), ensure_ascii=False),
            "titles_cn": json.dumps(
                {str(i+1): n.get("title_cn", "") for i, n in enumerate(analysis["news"])},
                ensure_ascii=False,
            ),
            "concepts": json.dumps(analysis.get("concepts", {}), ensure_ascii=False),
            "principles": json.dumps(analysis.get("principles", {}), ensure_ascii=False),
            "llm_provider": self.config["llm"]["provider"],
            "llm_model": self.config["llm"]["model"],
        }
        self.db.save_report(report)
        self.web_scraper.close()
        emit(f"完成！报告ID: {report_id}")
        return report
