import json
import yaml
import asyncio
import os
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi import FastAPI, BackgroundTasks, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from typing import List

# 从项目根目录的 .env 加载环境变量（LLM_API_KEY 等），需在导入其他模块之前调用
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))

from backend.db import Database
from backend.collector.rss import RSSCollector
from backend.pipeline import Pipeline, load_config
from backend.scheduler import NewsScheduler
from backend.config_utils import drop_empty_topics, normalize_proxy_config

# 加载配置（从项目根目录）
CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.yaml")

def get_config():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return normalize_proxy_config(yaml.safe_load(f))

CONFIG = get_config()

db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), CONFIG["database"]["path"])
db = Database(db_path)
db.init()


active_ws: List[WebSocket] = []
scheduler_instance = None


def pipeline_factory():
    return Pipeline(get_config(), db)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global scheduler_instance
    cfg = get_config()
    if cfg["scheduler"]["enabled"]:
        scheduler_instance = NewsScheduler(pipeline_factory, cfg["scheduler"]["cron"])
        scheduler_instance.start()
    yield
    if scheduler_instance:
        scheduler_instance.shutdown()


app = FastAPI(title="AI News Radar", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- WebSocket for real-time progress ---
@app.websocket("/ws/progress")
async def ws_progress(websocket: WebSocket):
    await websocket.accept()
    active_ws.append(websocket)
    try:
        while True:
            await asyncio.sleep(30)
    except WebSocketDisconnect:
        pass
    finally:
        if websocket in active_ws:
            active_ws.remove(websocket)


async def broadcast(msg: str):
    disconnected = []
    for ws in list(active_ws):
        try:
            await ws.send_text(msg)
        except Exception:
            disconnected.append(ws)
    for ws in disconnected:
        if ws in active_ws:
            active_ws.remove(ws)


# --- API Routes ---

@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/llm/test")
def test_llm(payload: dict = None):
    """测试 LLM 连通性，支持传入临时配置（未保存也可测）"""
    try:
        cfg = payload if payload else get_config()["llm"]
        from backend.llm.factory import create_llm_provider
        provider = create_llm_provider(cfg)
        reply = provider.chat("You are a helpful assistant.", "Reply with exactly: OK")
        return {"status": "ok", "reply": reply.strip()}
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=200)


@app.post("/api/collect")
async def trigger_collection(background_tasks: BackgroundTasks):
    """手动触发采集"""
    def run_pipeline():
        import asyncio as _asyncio

        def sync_broadcast(msg):
            loop = _asyncio.new_event_loop()
            try:
                loop.run_until_complete(broadcast(msg))
            except Exception:
                pass
            finally:
                loop.close()

        try:
            print("[API] run_pipeline started", flush=True)
            p = pipeline_factory()
            p.run(trigger="manual", progress_callback=sync_broadcast)
            print("[API] run_pipeline finished", flush=True)
        except Exception as e:
            print(f"[API] run_pipeline EXCEPTION: {e}", flush=True)
            import traceback; traceback.print_exc()

    background_tasks.add_task(run_pipeline)
    return {"status": "started", "message": "采集任务已启动，请通过WebSocket监听进度"}


@app.post("/api/analyze")
async def trigger_analyze(background_tasks: BackgroundTasks):
    """跳过采集，直接用数据库现有数据跑排序+LLM分析（测试用）"""
    def run_analyze():
        import asyncio as _asyncio
        import uuid
        from datetime import datetime, timezone
        from backend.scorer import Scorer
        from backend.analyzer import Analyzer
        from backend.llm.factory import create_llm_provider

        def sync_broadcast(msg):
            loop = _asyncio.new_event_loop()
            try:
                loop.run_until_complete(broadcast(msg))
            except Exception:
                pass
            finally:
                loop.close()

        try:
            print("[API] run_analyze started", flush=True)
            cfg = get_config()
            sync_broadcast("使用现有数据库数据分析...")
            window_days = cfg.get("collection", {}).get("date_window_days", 3)
            db_limit = cfg.get("collection", {}).get("db_limit", 300)
            recent_news = db.get_news_within_days(days=window_days, limit=db_limit)

            # 清洗已有数据中的HTML标签，并写回数据库
            cleaned_count = 0
            for n in recent_news:
                old_title = n.get("title", "")
                old_summary = n.get("summary", "")
                old_full = n.get("full_text", "")
                n["title"] = RSSCollector._strip_html(old_title)
                n["summary"] = RSSCollector._strip_html(old_summary)
                n["full_text"] = RSSCollector._strip_html(old_full)
                if n["title"] != old_title or n["summary"] != old_summary or n["full_text"] != old_full:
                    db.update_news_content(n["id"], n["title"], n["summary"], n["full_text"])
                    cleaned_count += 1
            if cleaned_count > 0:
                sync_broadcast(f"已清洗 {cleaned_count} 条新闻中的HTML标签")

            # 排除已在历史报告中使用过的新闻
            used_ids = db.get_used_news_ids()
            before_count = len(recent_news)
            recent_news = [n for n in recent_news if n["id"] not in used_ids]
            if before_count != len(recent_news):
                sync_broadcast(f"排除已用新闻: {before_count} → {len(recent_news)} 条")

            sync_broadcast(f"读取到 {len(recent_news)} 条新闻，开始评分...")
            llm = create_llm_provider(cfg["llm"])
            scorer = Scorer(llm=llm, topics=cfg.get("topics", []), db=db)
            all_relevant = scorer.score_and_rank(recent_news)
            score_map = {n["id"]: n["score"] for n in all_relevant}
            db.update_scores(score_map)

            # 深度分析层（前 20 条，含同源限制）+ 扫描层（其余相关条目）
            _DEEP_N = 20
            _DEEP_SOURCE_CAP = 2
            deep_news = []
            source_counts = {}
            for item in all_relevant:
                src = item.get("source_name", "unknown")
                if source_counts.get(src, 0) >= _DEEP_SOURCE_CAP:
                    continue
                deep_news.append(item)
                source_counts[src] = source_counts.get(src, 0) + 1
                if len(deep_news) >= _DEEP_N:
                    break
            deep_ids = {n["id"] for n in deep_news}
            scan_extras = [n for n in all_relevant if n["id"] not in deep_ids]

            sync_broadcast(f"进入LLM分析（深度 {len(deep_news)} 条 / 扫描层 {len(scan_extras)} 条）...")
            analyzer = Analyzer(
                llm=llm,
                topics=cfg.get("topics", []),
                categories=cfg.get("categories", []),
            )
            analysis = analyzer.analyze(deep_news, scan_extras=scan_extras)

            report_id = str(uuid.uuid4())
            report = {
                "id": report_id,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "trigger": "analyze_only",
                "top10_ids": json.dumps(
                    [n["id"] for n in analysis["news"]] +
                    [n["id"] for n in scan_extras]
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
                "llm_provider": cfg["llm"]["provider"],
                "llm_model": cfg["llm"]["model"],
            }
            db.save_report(report)
            sync_broadcast(f"分析完成！报告ID: {report_id}")
            print("[API] run_analyze finished", flush=True)
        except Exception as e:
            print(f"[API] run_analyze EXCEPTION: {e}", flush=True)
            import traceback; traceback.print_exc()

    background_tasks.add_task(run_analyze)
    return {"status": "started", "message": "分析任务已启动"}


@app.get("/api/reports")
def list_reports(limit: int = 20):
    """获取历史报告列表"""
    return db.get_reports(limit=limit)


@app.delete("/api/reports/{report_id}")
def delete_report_api(report_id: str):
    """删除指定报告"""
    report = db.get_report_by_id(report_id)
    if not report:
        return JSONResponse({"error": "Report not found"}, status_code=404)
    db.delete_report(report_id)
    return {"status": "ok", "message": "报告已删除"}


@app.get("/api/reports/{report_id}")
def get_report(report_id: str):
    """获取单份报告详情"""
    report = db.get_report_by_id(report_id)
    if not report:
        return JSONResponse({"error": "Report not found"}, status_code=404)

    raw_briefing = report.get("briefing") or "{}"
    if isinstance(raw_briefing, str):
        briefing = json.loads(raw_briefing)
    else:
        briefing = raw_briefing

    return {
        "id": report["id"],
        "created_at": report["created_at"],
        "trigger": report["trigger"],
        "llm_provider": report.get("llm_provider", ""),
        "llm_model": report.get("llm_model", ""),
        "briefing": briefing,
    }


@app.get("/api/config")
def get_config_api():
    """获取当前配置（隐藏 API Key）"""
    cfg = get_config()
    if "llm" in cfg and "api_key" in cfg["llm"]:
        cfg["llm"]["api_key"] = "***" if cfg["llm"]["api_key"] else ""
    return cfg


@app.put("/api/config")
def update_config(updates: dict):
    """更新配置（写回 config.yaml）"""
    cfg = get_config()
    # 如果前端传回的 api_key 是掩码值 "***"，保留原值
    if "llm" in updates and updates["llm"].get("api_key") in ("***", ""):
        updates["llm"]["api_key"] = cfg.get("llm", {}).get("api_key", "")
    # 剔除前端可能提交的空白话题卡片，避免污染语义过滤
    if "topics" in updates:
        updates["topics"] = drop_empty_topics(updates["topics"])
    # 深度合并
    for key, val in updates.items():
        if isinstance(val, dict) and key in cfg and isinstance(cfg[key], dict):
            cfg[key].update(val)
        else:
            cfg[key] = val
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.dump(cfg, f, allow_unicode=True, default_flow_style=False)
    return {"status": "ok"}


@app.get("/api/wechat/status")
def wechat_status():
    """获取微信公众号 session 状态"""
    from backend.collector.wechat_auth import has_session, SESSION_PATH
    if has_session():
        mtime = os.path.getmtime(SESSION_PATH)
        from datetime import datetime, timezone
        saved_at = datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()
        return {"status": "saved", "saved_at": saved_at, "message": "session 已保存（有效性需采集时验证）"}
    return {"status": "none", "message": "尚未登录，请扫码授权"}


@app.post("/api/wechat/login")
def wechat_login():
    """启动 Playwright 浏览器，扫码登录微信公众号后台"""
    try:
        from backend.collector.wechat_auth import login_and_save_session
        result = login_and_save_session()
        if result:
            return {"status": "ok", "message": "登录成功，session 已保存"}
        return JSONResponse(
            {"status": "error", "message": "登录失败或超时，请重试"},
            status_code=400,
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse(
            {"status": "error", "message": f"登录异常: {e}"},
            status_code=500,
        )


@app.post("/api/wechat/collect")
async def wechat_collect(background_tasks: BackgroundTasks):
    """仅采集微信公众号（测试用）"""
    def run_wechat_collect():
        import asyncio as _asyncio

        def sync_broadcast(msg):
            loop = _asyncio.new_event_loop()
            try:
                loop.run_until_complete(broadcast(msg))
            except Exception:
                pass
            finally:
                loop.close()

        try:
            from backend.pipeline import load_sources
            from backend.collector.wechat import WechatCollector

            cfg = get_config()
            sources = [s for s in load_sources() if s.get("type") == "wechat"]
            if not sources:
                sync_broadcast("未配置微信公众号源")
                return

            sync_broadcast(f"开始采集 {len(sources)} 个微信公众号...")
            collector = WechatCollector(max_per_source=cfg["collection"]["max_per_source"])
            items = collector.collect_all(sources)
            sync_broadcast(f"微信采集完成: {len(items)} 条文章")

            # 写入数据库
            for news in items:
                db.upsert_news(news)
            sync_broadcast(f"已写入数据库 {len(items)} 条")
        except Exception as e:
            import traceback
            traceback.print_exc()
            sync_broadcast(f"微信采集失败: {e}")

    background_tasks.add_task(run_wechat_collect)
    return {"status": "started", "message": "微信公众号采集已启动"}


@app.get("/api/twitter/status")
def twitter_status():
    """获取 Twitter 账号配置状态"""
    from backend.collector.twitter_auth import (
        has_accounts, has_browser_session, ACCOUNTS_DB_PATH, BROWSER_SESSION_PATH,
        twscrape_available, TWSCRAPE_MISSING_MSG,
    )
    from datetime import datetime, timezone
    if not twscrape_available():
        return {"status": "unavailable", "message": TWSCRAPE_MISSING_MSG}
    if has_accounts():
        mtime = os.path.getmtime(ACCOUNTS_DB_PATH)
        saved_at = datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()
        return {"status": "configured", "saved_at": saved_at, "message": "账号已配置（twscrape 账号池）"}
    if has_browser_session():
        mtime = os.path.getmtime(BROWSER_SESSION_PATH)
        saved_at = datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()
        return {"status": "configured", "saved_at": saved_at, "message": "账号已配置（浏览器登录凭证）"}
    return {"status": "none", "message": "尚未配置 X 账号"}


@app.post("/api/twitter/add-account")
async def twitter_add_account(body: dict):
    """添加 X 账号并登录（需提供 username/password/email）"""
    from backend.collector.twitter_auth import twscrape_available, TWSCRAPE_MISSING_MSG
    if not twscrape_available():
        return JSONResponse(
            {"status": "error", "message": TWSCRAPE_MISSING_MSG}, status_code=400
        )
    username = body.get("username", "").strip()
    password = body.get("password", "").strip()
    email = body.get("email", "").strip()
    email_password = body.get("email_password", "").strip()

    if not username or not password or not email:
        return JSONResponse(
            {"status": "error", "message": "username / password / email 均为必填"},
            status_code=400,
        )
    try:
        from backend.collector.twitter_auth import add_account
        result = await add_account(username, password, email, email_password)
        return {"status": "ok", "message": f"账号已添加，登录成功 {result['logged_in']}/{result['total']} 个"}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse(
            {"status": "error", "message": f"添加失败: {e}"},
            status_code=500,
        )


@app.post("/api/twitter/login")
def twitter_browser_login():
    """启动 Playwright 浏览器，用户手动登录 X.com 后自动保存 cookies 凭证"""
    from backend.collector.twitter_auth import twscrape_available, TWSCRAPE_MISSING_MSG
    if not twscrape_available():
        return JSONResponse(
            {"status": "error", "message": TWSCRAPE_MISSING_MSG}, status_code=400
        )
    try:
        from backend.collector.twitter_auth import browser_login_and_save, add_account_from_session
        result = browser_login_and_save()
        if not result:
            return JSONResponse(
                {"status": "error", "message": "登录失败或超时，请重试"},
                status_code=400,
            )
        # 将 cookies 注入 twscrape 账号池
        import asyncio as _asyncio
        loop = _asyncio.new_event_loop()
        try:
            add_result = loop.run_until_complete(add_account_from_session())
            username = add_result.get("username", "")
        except Exception as e:
            # 注入 twscrape 失败不影响凭证已保存的结果
            print(f"[Twitter] twscrape 注入失败（凭证已保存）: {e}", flush=True)
            username = ""
        finally:
            loop.close()
        msg = f"登录成功，凭证已保存" + (f"（@{username}）" if username else "")
        return {"status": "ok", "message": msg}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse(
            {"status": "error", "message": f"登录异常: {e}"},
            status_code=500,
        )


@app.post("/api/twitter/collect")
async def twitter_collect(background_tasks: BackgroundTasks):
    """仅采集 X/Twitter 推文（测试用）"""
    from backend.collector.twitter_auth import twscrape_available, TWSCRAPE_MISSING_MSG
    if not twscrape_available():
        return JSONResponse(
            {"status": "error", "message": TWSCRAPE_MISSING_MSG}, status_code=400
        )

    def run_twitter_collect():
        import asyncio as _asyncio

        def sync_broadcast(msg):
            loop = _asyncio.new_event_loop()
            try:
                loop.run_until_complete(broadcast(msg))
            except Exception:
                pass
            finally:
                loop.close()

        try:
            cfg = get_config()
            twitter_cfg = cfg.get("sources", {}).get("twitter", {})
            accounts = twitter_cfg.get("accounts", [])
            if not accounts:
                sync_broadcast("未配置 X 监控账号，请先在配置页添加账号")
                return

            from backend.collector.twitter import TwitterCollector
            sync_broadcast(f"开始采集 {len(accounts)} 个 X 账号...")
            collector = TwitterCollector(date_window_days=cfg.get("collection", {}).get("date_window_days", 3))
            items = collector.collect_all(twitter_cfg, proxy_url=cfg.get("sources", {}).get("proxy_url", ""))
            sync_broadcast(f"X 采集完成: {len(items)} 条推文")

            for news in items:
                db.upsert_news(news)
            sync_broadcast(f"已写入数据库 {len(items)} 条")
        except Exception as e:
            import traceback
            traceback.print_exc()
            sync_broadcast(f"X 采集失败: {e}")

    background_tasks.add_task(run_twitter_collect)
    return {"status": "started", "message": "X/Twitter 采集已启动"}


@app.get("/api/sources")
def list_sources():
    """获取所有信源配置"""
    from backend.pipeline import load_sources
    return load_sources()


# --- 静态文件托管（前端）---
FRONTEND_DIST = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend", "dist")
if os.path.exists(FRONTEND_DIST):
    app.mount("/assets", StaticFiles(directory=os.path.join(FRONTEND_DIST, "assets")), name="assets")

    @app.get("/")
    def serve_index():
        return FileResponse(os.path.join(FRONTEND_DIST, "index.html"))

    @app.get("/{full_path:path}")
    def serve_spa(full_path: str):
        # SPA fallback：所有非 /api 路径都返回 index.html
        file_path = os.path.join(FRONTEND_DIST, full_path)
        if os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse(os.path.join(FRONTEND_DIST, "index.html"))
