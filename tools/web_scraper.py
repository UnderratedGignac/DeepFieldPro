"""
General-purpose Playwright scraper + Qwen session auto-capturer.

Two modes:

1. fetch(url) → str
   Returns page content (text/HTML) from any URL with a real headless browser.
   Use for JS-rendered pages, SPAs, anything requests/BS4 can't handle.

2. capture_qwen_session() → dict | None
   Launches chat.qwen.ai, submits a probe message, intercepts the real
   /api/v2/chat/completions POST, extracts bx-ua + cookie + bx-umidtoken,
   writes them into .env, and returns the dict.
   Called automatically by qwen_http_worker when SESSION_EXPIRED is detected.

CLI:
    # general fetch
    python tools/web_scraper.py https://example.com

    # Qwen session refresh (headless)
    python tools/web_scraper.py --qwen

    # Qwen session refresh (visible browser window, use if headless fails)
    python tools/web_scraper.py --qwen --visible
"""

import asyncio
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv
from playwright.async_api import async_playwright, Request

load_dotenv()

_PROJECT_ROOT = Path(__file__).parent.parent
_ENV_PATH = _PROJECT_ROOT / ".env"

_QWEN_HOME = "https://chat.qwen.ai/"
_QWEN_GUEST = "https://chat.qwen.ai/c/guest"
_QWEN_API_PATH = "/api/v2/chat/completions"
_PROBE_MSG = "hi"

# Persistent browser profile — keeps Google login alive across runs
_PROFILE_DIR = str(_PROJECT_ROOT / "data" / "qwen_browser_profile")


# ---------------------------------------------------------------------------
# General scraper
# ---------------------------------------------------------------------------


async def _fetch_async(url: str, timeout_ms: int = 30_000) -> str:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/149.0.0.0 Safari/537.36"
            )
        )
        page = await ctx.new_page()
        await page.goto(url, timeout=timeout_ms, wait_until="networkidle")
        content = await page.content()
        await browser.close()
        return content


def fetch(url: str, timeout_ms: int = 30_000) -> str:
    """Fetch a URL with a real headless browser and return the HTML."""
    return asyncio.run(_fetch_async(url, timeout_ms))


# ---------------------------------------------------------------------------
# Qwen session capturer
# ---------------------------------------------------------------------------


async def _login_setup_async() -> None:
    """
    Open a VISIBLE browser with the persistent profile so the user can log in
    to chat.qwen.ai manually. The session is saved to the profile directory
    and reused automatically by all future headless captures.
    Run once: python tools/web_scraper.py --setup
    """
    Path(_PROFILE_DIR).mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(
            _PROFILE_DIR,
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/149.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
        )
        await ctx.add_init_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"
        )
        page = await ctx.new_page()
        await page.goto(_QWEN_HOME)
        print("[scraper] Browser open. Log in to chat.qwen.ai, then press ENTER here to save session.")
        input()
        await ctx.close()
    print(f"[scraper] Session saved to {_PROFILE_DIR}")


async def _capture_qwen_async(headless: bool = True, timeout_ms: int = 60_000) -> dict | None:
    """
    Use the persistent browser profile to open chat.qwen.ai (already logged in),
    send a probe message, intercept the completions POST, return fresh headers.
    """
    captured: dict = {}
    profile = Path(_PROFILE_DIR)
    if not profile.exists():
        print(f"[scraper] No browser profile found at {_PROFILE_DIR}")
        print("[scraper] Run:  python tools/web_scraper.py --setup  to log in once.")
        return None

    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(
            str(profile),
            headless=headless,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/149.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
        )
        await ctx.add_init_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"
        )
        page = await ctx.new_page()

        async def on_request(req: Request):
            if _QWEN_API_PATH in req.url and req.method == "POST" and not captured:
                hdrs = req.headers
                captured["cookie"] = hdrs.get("cookie", "")
                captured["bx_ua"] = hdrs.get("bx-ua", "")
                captured["bx_umid"] = hdrs.get("bx-umidtoken", "")
                print(f"[scraper] captured — cookie={len(captured['cookie'])}b  bx-ua={len(captured['bx_ua'])}b")

        page.on("request", on_request)

        print("[scraper] navigating to /c/guest …")
        try:
            await page.goto(_QWEN_GUEST, timeout=timeout_ms, wait_until="domcontentloaded")
        except Exception as e:
            print(f"[scraper] navigation error: {e}")
            await ctx.close()
            return None

        # Redirect to login = profile session expired, need --setup again
        if "accounts.google.com" in page.url or "login" in page.url:
            print(f"[scraper] redirected to login ({page.url[:60]})")
            print("[scraper] Run:  python tools/web_scraper.py --setup  to refresh login.")
            await ctx.close()
            return None

        # Wait for textarea
        textarea_sel = None
        for sel in ["textarea.message-input-textarea", "textarea"]:
            try:
                await page.wait_for_selector(sel, timeout=15_000)
                textarea_sel = sel
                break
            except Exception:
                continue

        if not textarea_sel:
            print(f"[scraper] no textarea — title={await page.title()!r}  url={page.url!r}")
            await ctx.close()
            return None

        await page.wait_for_timeout(3000)  # let bx-ua JS finish

        print("[scraper] sending probe message …")
        await page.click(textarea_sel)
        await page.type(textarea_sel, _PROBE_MSG, delay=80)
        await page.wait_for_timeout(400)

        # Try send button first, fall back to Enter
        sent = False
        for sel in [".send-button", "button[class*='send']"]:
            try:
                btn = await page.query_selector(sel)
                if btn:
                    await btn.click()
                    sent = True
                    break
            except Exception:
                continue
        if not sent:
            await page.keyboard.press("Enter")

        for _ in range(60):
            if captured:
                break
            await page.wait_for_timeout(500)

        await ctx.close()

    return captured if captured.get("bx_ua") else None


def capture_qwen_session(headless: bool = True) -> dict | None:
    """
    Capture a fresh Qwen session by running a real browser.
    Returns {cookie, bx_ua, bx_umid} and writes them to .env.
    Returns None if capture failed.
    """
    result = asyncio.run(_capture_qwen_async(headless=headless))
    if not result:
        return None

    _update_env(result)
    print(f"[scraper] session captured — cookie len={len(result['cookie'])}")
    return result


def _update_env(session: dict) -> None:
    """Write QWEN_WEB_COOKIE / QWEN_WEB_BX_UA / QWEN_WEB_BX_UMID into .env."""
    env_text = _ENV_PATH.read_text(encoding="utf-8") if _ENV_PATH.exists() else ""

    def _set(text: str, key: str, value: str) -> str:
        pattern = rf"^{re.escape(key)}=.*$"
        replacement = f"{key}={value}"
        if re.search(pattern, text, flags=re.MULTILINE):
            return re.sub(pattern, replacement, text, flags=re.MULTILINE)
        return text + f"\n{replacement}"

    env_text = _set(env_text, "QWEN_WEB_COOKIE", session["cookie"])
    env_text = _set(env_text, "QWEN_WEB_BX_UA", session["bx_ua"])
    env_text = _set(env_text, "QWEN_WEB_BX_UMID", session["bx_umid"])

    _ENV_PATH.write_text(env_text, encoding="utf-8")
    print(f"[scraper] .env updated with fresh Qwen session")

    # Reload into current process so qwen_http_worker picks them up immediately
    os.environ["QWEN_WEB_COOKIE"] = session["cookie"]
    os.environ["QWEN_WEB_BX_UA"] = session["bx_ua"]
    os.environ["QWEN_WEB_BX_UMID"] = session["bx_umid"]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def login_setup() -> None:
    """Open visible browser for one-time login. Saves session to persistent profile."""
    asyncio.run(_login_setup_async())


if __name__ == "__main__":
    args = sys.argv[1:]

    if "--setup" in args:
        # One-time login: opens browser, user logs in, session saved
        print(f"[scraper] opening browser for one-time Qwen login …")
        print(f"[scraper] profile dir: {_PROFILE_DIR}")
        login_setup()

    elif not args or "--qwen" in args:
        # Session capture (requires prior --setup)
        headless = "--visible" not in args
        print(f"[scraper] capturing Qwen session (headless={headless}) …")
        sess = capture_qwen_session(headless=headless)
        if sess:
            print(f"[scraper] bx_ua[:50]: {sess['bx_ua'][:50]}…")
            print(f"[scraper] done — .env updated")
            sys.exit(0)
        else:
            print("[scraper] FAILED — run --setup if not logged in yet", file=sys.stderr)
            sys.exit(1)

    else:
        # General URL fetch
        url = args[0]
        print(f"[scraper] fetching {url} …")
        html = fetch(url)
        print(html[:5000])
