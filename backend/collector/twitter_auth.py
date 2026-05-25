"""X/Twitter 账号池管理（基于 twscrape AccountsPool）

两种凭证方式：
1. 手动输入账号密码 → add_account() → twscrape 程序化登录
2. 浏览器手动登录 → browser_login_and_save() → 捕获 cookies → add_account_from_session()

账号数据持久化到 data/twitter_accounts.db（twscrape 自维护的 SQLite）。
浏览器 session 持久化到 data/twitter_browser_session.json。
"""
import json
import os
import subprocess
import sys

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
ACCOUNTS_DB_PATH = os.path.join(_PROJECT_ROOT, "data", "twitter_accounts.db")
BROWSER_SESSION_PATH = os.path.join(_PROJECT_ROOT, "data", "twitter_browser_session.json")

# twscrape 是可选依赖：缺失时 X/Twitter 采集整体降级跳过，其余信源不受影响。
TWSCRAPE_MISSING_MSG = (
    "twscrape 未安装，X/Twitter 采集功能不可用。"
    "请运行 pip install -r backend/requirements.txt 安装依赖后重试。"
)


def twscrape_available() -> bool:
    """检测 twscrape 是否已安装（仅定位模块，不导入、不触发其初始化）。"""
    import importlib.util
    try:
        return importlib.util.find_spec("twscrape") is not None
    except (ImportError, ValueError):
        return False


def has_accounts() -> bool:
    """检查是否存在账号池文件（仅验证文件存在，不检查账号数量）。"""
    return os.path.exists(ACCOUNTS_DB_PATH)


def has_browser_session() -> bool:
    """检查是否存在浏览器登录凭证文件。"""
    return os.path.exists(BROWSER_SESSION_PATH)


async def add_account(username: str, password: str, email: str, email_password: str = "") -> dict:
    """添加 X 账号并尝试登录。在 FastAPI async 路由中直接 await。"""
    from twscrape import AccountsPool
    os.makedirs(os.path.dirname(ACCOUNTS_DB_PATH), exist_ok=True)
    pool = AccountsPool(ACCOUNTS_DB_PATH)
    await pool.add_account(username, password, email, email_password or "")
    stats = await pool.login_all()
    logged_in = stats.get("success", 0) if isinstance(stats, dict) else 0
    total = stats.get("total", 0) if isinstance(stats, dict) else 0
    return {"logged_in": logged_in, "total": total}


def browser_login_and_save() -> dict | None:
    """在独立子进程中启动 Playwright 浏览器，让用户手动登录 X.com，捕获 cookies 保存。

    流程：打开 x.com/login → 用户手动完成登录 → 检测到 /home URL → 保存 cookies → 关闭浏览器。
    """
    print("[TwitterAuth] 启动子进程进行浏览器登录...", flush=True)
    try:
        result = subprocess.run(
            [sys.executable, "-u", "-c", _BROWSER_LOGIN_SCRIPT],
            cwd=_PROJECT_ROOT,
            timeout=300,
        )
    except subprocess.TimeoutExpired:
        print("[TwitterAuth] 登录超时（5分钟）", flush=True)
        return None

    if result.returncode == 0 and has_browser_session():
        print("[TwitterAuth] 浏览器登录凭证已保存", flush=True)
        return {"session_path": BROWSER_SESSION_PATH}

    print("[TwitterAuth] 浏览器登录失败", flush=True)
    return None


async def add_account_from_session() -> dict:
    """读取浏览器 session，将 cookies 注入 twscrape 账号池，并直接激活账号。

    注意：不调用 login_all()（空密码会失败并重置 active=False），改为直接操作 SQLite。
    """
    if not has_browser_session():
        raise Exception("未找到浏览器 session，请先进行浏览器登录")

    with open(BROWSER_SESSION_PATH, encoding="utf-8") as f:
        session = json.load(f)

    auth_token = session.get("auth_token", "")
    ct0 = session.get("ct0", "")
    username = session.get("username") or "x_browser_user"

    if not auth_token:
        raise Exception("session 中未找到 auth_token，请重新登录")

    # 清理旧 DB，避免残留的 inactive 状态
    if os.path.exists(ACCOUNTS_DB_PATH):
        os.remove(ACCOUNTS_DB_PATH)
        print("[TwitterAuth] 已清除旧账号池，重新注入", flush=True)

    from twscrape import AccountsPool
    os.makedirs(os.path.dirname(ACCOUNTS_DB_PATH), exist_ok=True)
    pool = AccountsPool(ACCOUNTS_DB_PATH)

    # 只取 Twitter/X 域名下的 cookie，twscrape 只接受 string 格式（"k=v; k2=v2"）
    _TWITTER_COOKIE_NAMES = {"auth_token", "ct0", "kdt", "twid", "att", "lang", "guest_id"}
    twitter_cookies_dict = {}
    for c in session.get("cookies", []):
        name = c.get("name", "")
        domain = c.get("domain", "")
        if name in _TWITTER_COOKIE_NAMES and ("twitter.com" in domain or "x.com" in domain):
            twitter_cookies_dict[name] = c["value"]

    if not twitter_cookies_dict.get("auth_token"):
        twitter_cookies_dict["auth_token"] = auth_token
    if ct0 and not twitter_cookies_dict.get("ct0"):
        twitter_cookies_dict["ct0"] = ct0

    cookies_str = "; ".join(f"{k}={v}" for k, v in twitter_cookies_dict.items())
    print(f"[TwitterAuth] 注入 {len(twitter_cookies_dict)} 个 cookies: {list(twitter_cookies_dict.keys())}", flush=True)
    await pool.add_account(username, "", "", "", cookies=cookies_str)

    # 手工构造 Twitter Web 客户端的标准 headers（twscrape login 流程会做这件事，跳过 login 就得手动）
    # Bearer token 是 Twitter Web 公开常量
    TWITTER_BEARER = "AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"
    headers_dict = {
        "authorization": f"Bearer {TWITTER_BEARER}",
        "content-type": "application/json",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "x-twitter-auth-type": "OAuth2Session",
        "x-twitter-active-user": "yes",
        "x-twitter-client-language": "en",
        "x-csrf-token": twitter_cookies_dict.get("ct0", ct0),
    }

    # 诊断 + 强制激活 + 手工写 headers
    import sqlite3
    conn = sqlite3.connect(ACCOUNTS_DB_PATH)
    try:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(accounts)").fetchall()]
        print(f"[TwitterAuth] accounts 表字段: {cols}", flush=True)
        rows = conn.execute("SELECT username, active, length(cookies), length(headers) FROM accounts").fetchall()
        print(f"[TwitterAuth] 写入后所有账号: {rows}", flush=True)

        # 写入 headers + 强制激活
        conn.execute(
            "UPDATE accounts SET active=1, locks='{}', error_msg=NULL, last_used=NULL, headers=? WHERE username=?",
            (json.dumps(headers_dict), username),
        )
        conn.commit()

        row = conn.execute(
            "SELECT username, active, length(cookies), length(headers), error_msg FROM accounts WHERE username=?",
            (username,),
        ).fetchone()
        print(f"[TwitterAuth] 激活+headers写入后: username={row[0]}, active={row[1]}, cookies_len={row[2]}, headers_len={row[3]}, err={row[4]}", flush=True)
    finally:
        conn.close()

    return {"username": username}


_BROWSER_LOGIN_SCRIPT = r'''
import json, os, sys, time

SESSION_PATH = os.path.join("data", "twitter_browser_session.json")
# 持久化 Chrome Profile：保存 Google 账号等登录状态，下次无需重新登录 Google
USER_DATA_DIR = os.path.abspath(os.path.join("data", "twitter_chrome_profile"))
os.makedirs(USER_DATA_DIR, exist_ok=True)
os.makedirs("data", exist_ok=True)

CHROME_PATHS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expanduser(r"~\AppData\Local\Google\Chrome\Application\chrome.exe"),
]
CHROME_EXE = next((p for p in CHROME_PATHS if os.path.exists(p)), None)

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("[TwitterAuth] playwright 未安装，请运行: playwright install chromium", flush=True)
    sys.exit(1)

with sync_playwright() as p:
    # ignore_default_args 移除 --enable-automation，这是 Google 检测自动化的关键标志
    launch_kwargs = dict(
        user_data_dir=USER_DATA_DIR,
        headless=False,
        ignore_default_args=["--enable-automation"],
        args=[
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-blink-features=AutomationControlled",
        ],
        viewport={"width": 1280, "height": 800},
        locale="zh-CN",
        timezone_id="Asia/Shanghai",
    )
    if CHROME_EXE:
        print(f"[TwitterAuth] 使用本机 Chrome: {CHROME_EXE}", flush=True)
        launch_kwargs["executable_path"] = CHROME_EXE
    else:
        print("[TwitterAuth] 未找到本机 Chrome，使用 Playwright Chromium", flush=True)

    try:
        context = p.chromium.launch_persistent_context(**launch_kwargs)
    except Exception as e:
        print(f"[TwitterAuth] 启动失败: {e}，尝试不指定路径重试", flush=True)
        launch_kwargs.pop("executable_path", None)
        context = p.chromium.launch_persistent_context(**launch_kwargs)

    # 进一步隐藏 webdriver 标记
    context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    page = context.pages[0] if context.pages else context.new_page()
    username = ""

    try:
        page.goto("https://x.com/login", wait_until="domcontentloaded")
        print("[TwitterAuth] 请在浏览器中登录 X/Twitter...", flush=True)
        print("[TwitterAuth] Google 登录状态会保存在专属 Profile 中，下次无需重新登录 Google", flush=True)
        page.wait_for_url("**/home", timeout=300000)
        print("[TwitterAuth] 检测到登录成功", flush=True)
        time.sleep(2)
        try:
            profile_href = page.evaluate(
                "document.querySelector('[data-testid=\"AppTabBar_Profile_Link\"]')?.getAttribute('href')"
            )
            if profile_href:
                username = profile_href.lstrip("/").split("?")[0].split("/")[0]
                print(f"[TwitterAuth] 用户名: @{username}", flush=True)
        except Exception:
            pass
    except Exception as e:
        print(f"[TwitterAuth] 等待登录超时或异常: {e}", flush=True)

    try:
        cookies = context.cookies()
        auth_map = {c["name"]: c["value"] for c in cookies if c["name"] in ("auth_token", "ct0")}
        if not auth_map.get("auth_token"):
            print("[TwitterAuth] 未获取到 auth_token，请确认已成功登录", flush=True)
            context.close()
            sys.exit(1)
        state = {
            "cookies": cookies,
            "auth_token": auth_map["auth_token"],
            "ct0": auth_map.get("ct0", ""),
            "username": username,
        }
        with open(SESSION_PATH, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        print(f"[TwitterAuth] 凭证已保存（用户名: @{username or '未获取'}）", flush=True)
    except Exception as e:
        print(f"[TwitterAuth] 保存凭证失败: {e}", flush=True)
        try:
            context.close()
        except Exception:
            pass
        sys.exit(1)

    try:
        context.close()
    except Exception:
        pass
'''
