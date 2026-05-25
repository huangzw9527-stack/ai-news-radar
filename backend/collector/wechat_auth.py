"""微信公众号后台凭证管理（Playwright 扫码登录 + storage_state 缓存）

登录流程参考 feedgrab 项目：
- 打开浏览器 → 用户扫码登录 → 用户手动关闭浏览器 → 保存 storage_state
- Token 不在登录时提取，而是在采集时通过浏览器访问后台 URL 提取
"""
import json
import os
import subprocess
import sys

SESSION_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "data", "wechat_session.json",
)

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))


def has_session() -> bool:
    """检查是否存在 session 文件。"""
    return os.path.exists(SESSION_PATH)


def login_and_save_session() -> dict | None:
    """在独立子进程中启动 Playwright 浏览器扫码登录。

    流程：打开 mp.weixin.qq.com → 用户扫码 → 用户关闭浏览器 → 保存 cookies。
    Token 不在此时提取，采集时再从浏览器 URL 中获取。

    Returns:
        {"session_path": str} 或 None
    """
    print("[WechatAuth] 启动子进程进行扫码登录...", flush=True)
    try:
        result = subprocess.run(
            [sys.executable, "-u", "-c", _LOGIN_SCRIPT],
            cwd=_PROJECT_ROOT,
            timeout=300,  # 5 分钟超时（等用户关闭浏览器）
        )
    except subprocess.TimeoutExpired:
        print("[WechatAuth] 登录超时（5分钟）", flush=True)
        return None

    if result.returncode == 0 and has_session():
        print("[WechatAuth] session 已保存", flush=True)
        return {"session_path": SESSION_PATH}

    print("[WechatAuth] 登录失败", flush=True)
    return None


# 子进程中执行的登录脚本（参考 feedgrab 的 _login_visible 方式）
_LOGIN_SCRIPT = '''
import json, os, sys

SESSION_PATH = os.path.join("data", "wechat_session.json")
CHROMIUM_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--disable-features=AutomationControlled",
    "--disable-infobars",
    "--no-first-run",
]

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("[WechatAuth] playwright 未安装", flush=True)
    sys.exit(1)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False, args=CHROMIUM_ARGS)
    context = browser.new_context()
    page = context.new_page()
    try:
        page.goto("https://mp.weixin.qq.com/", wait_until="domcontentloaded")
        print("[WechatAuth] 请在浏览器中扫码登录，登录成功后请手动关闭浏览器窗口...", flush=True)

        # 等待用户关闭浏览器（feedgrab 方式）
        page.wait_for_event("close", timeout=300000)
        print("[WechatAuth] 浏览器已关闭，保存 session...", flush=True)

    except Exception as e:
        # 如果 page 关闭导致异常，也尝试保存（浏览器可能已被关闭）
        print(f"[WechatAuth] 浏览器事件: {e}", flush=True)

    # 无论如何都尝试保存 cookies
    try:
        os.makedirs(os.path.dirname(SESSION_PATH), exist_ok=True)
        cookies = context.cookies()
        if len(cookies) > 2:
            state = {"cookies": cookies, "origins": []}
            with open(SESSION_PATH, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
            print(f"[WechatAuth] 已保存 {len(cookies)} 个 cookies", flush=True)
        else:
            print("[WechatAuth] cookies 数量不足，可能未登录成功", flush=True)
            sys.exit(1)
    except Exception as e:
        print(f"[WechatAuth] 保存 cookies 失败: {e}", flush=True)
        sys.exit(1)
    finally:
        try:
            browser.close()
        except Exception:
            pass
'''


def load_session() -> dict | None:
    """加载 session 文件，返回 {session_path} 或 None。"""
    if not has_session():
        return None
    try:
        with open(SESSION_PATH, encoding="utf-8") as f:
            state = json.load(f)
        cookies = state.get("cookies", [])
        if len(cookies) < 2:
            return None
        return {"session_path": SESSION_PATH}
    except Exception:
        return None
