"""
Copilot session refresher -- extracts cookies + temporarySessionKey and saves
them to .env so copilot_worker.py can chat without 451 errors.

Three modes (tried in order):
  1. FAST (no browser): just refresh the session key via API if COPILOT_COOKIE
     is already saved and still valid.  Takes ~1s.
  2. INTERACTIVE: print a JS one-liner, user pastes it in Edge DevTools Console
     on copilot.microsoft.com, pastes back the output.  Works 100% of the time.
  3. BROWSER (Playwright): open Edge, wait for Windows SSO to sign in,
     extract everything automatically.  May fail if SSO is not configured.

Usage:
    # Auto (tries fast, then interactive):
    .venv/Scripts/python.exe tools/copilot_session_refresh.py

    # Force full re-authentication (interactive mode):
    .venv/Scripts/python.exe tools/copilot_session_refresh.py --full

    # Try browser automation only:
    .venv/Scripts/python.exe tools/copilot_session_refresh.py --browser
"""

import asyncio
import json
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv, set_key

_ROOT = Path(__file__).parent.parent
_ENV_FILE = _ROOT / ".env"
load_dotenv(str(_ENV_FILE))

_COPILOT_URL = "https://copilot.microsoft.com"


# ---------------------------------------------------------------------------
# Mode 1: Fast API refresh (no browser)
# ---------------------------------------------------------------------------

def _fast_refresh() -> str:
    """Try to refresh COPILOT_SESSION_KEY via API. Returns new key or ''."""
    import requests

    cookie = os.getenv("COPILOT_COOKIE", "").strip()
    if not cookie:
        return ""

    try:
        r = requests.post(
            f"{_COPILOT_URL}/c/api/user/sessions/temporary",
            headers={
                "Cookie": cookie,
                "Content-Type": "application/json",
                "Referer": f"{_COPILOT_URL}/",
                "Origin": _COPILOT_URL,
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/132.0.0.0 Safari/537.36 Edg/132.0.0.0"
                ),
            },
            json={},
            timeout=10,
        )
        if r.status_code == 200:
            key = r.json().get("sessionKey", "")
            if key:
                return key
        print(f"[refresh] API returned {r.status_code} — need browser refresh.")
    except Exception as e:
        print(f"[refresh] API error: {e}")
    return ""


# ---------------------------------------------------------------------------
# Mode 2: Interactive (JS snippet in DevTools)
# ---------------------------------------------------------------------------

_JS_SNIPPET = r"""
(async () => {
  const r = await fetch('/c/api/user/sessions/temporary', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: '{}'
  });
  const d = await r.json();
  const out = JSON.stringify({
    key: d.sessionKey || '',
    status: r.status,
    cookie: document.cookie
  });
  console.log('COPILOT_REFRESH:' + out);
  return out;
})()
""".strip()


def _interactive_refresh() -> dict:
    """
    Print the JS snippet, wait for user to paste the output, parse it.
    Returns {"cookie_header": str, "session_key": str}.
    """
    print()
    print("=" * 70)
    print("MANUAL REFRESH — paste this snippet in Edge DevTools Console")
    print("  (go to copilot.microsoft.com → F12 → Console tab)")
    print("=" * 70)
    print()
    print(_JS_SNIPPET)
    print()
    print("-" * 70)
    print("After running it, copy the line that starts with COPILOT_REFRESH:")
    print("then paste it below and press Enter.")
    print("-" * 70)
    print()

    while True:
        try:
            raw = input("Paste output here: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nCancelled.")
            return {}

        if not raw:
            continue

        # Accept either the raw JSON or the full console line
        if "COPILOT_REFRESH:" in raw:
            raw = raw.split("COPILOT_REFRESH:", 1)[1].strip()

        # Strip surrounding quotes if console added them
        if raw.startswith('"') and raw.endswith('"'):
            raw = raw[1:-1].replace('\\"', '"')

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            print("Could not parse — try again (paste the COPILOT_REFRESH:... line).")
            continue

        status = data.get("status", 0)
        key = data.get("key", "")
        cookie = data.get("cookie", "")

        if status != 200 or not key:
            print(f"Session key fetch returned status={status}. "
                  f"Make sure you're signed in to copilot.microsoft.com.")
            continue

        return {"cookie_header": cookie, "session_key": key}


# ---------------------------------------------------------------------------
# Mode 3: Browser automation (Playwright)
# ---------------------------------------------------------------------------

async def _browser_refresh(sign_in_timeout_s: int = 90) -> dict:
    """
    Launch Edge, use Windows SSO to sign in, extract cookies + session key.
    Returns {"cookie_header": str, "session_key": str} or raises.
    """
    from playwright.async_api import async_playwright

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            channel="msedge",
            headless=False,
            args=[
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-blink-features=AutomationControlled",
            ],
            ignore_default_args=["--enable-automation"],
        )
        ctx = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/132.0.0.0 Safari/537.36 Edg/132.0.0.0"
            ),
        )
        await ctx.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            window.chrome = {runtime: {}};
        """)
        page = await ctx.new_page()

        print(f"[refresh-browser] Navigating to {_COPILOT_URL} ...")
        print("[refresh-browser] If asked to sign in, do so in the browser window.")

        await page.goto(_COPILOT_URL, wait_until="domcontentloaded", timeout=30_000)

        # Poll for sign-in completion (look for _U cookie)
        deadline = time.time() + sign_in_timeout_s
        signed_in = False
        while time.time() < deadline:
            cookies = await ctx.cookies([_COPILOT_URL])
            u = next((c for c in cookies if c["name"] == "_U"), None)
            login_url = page.url
            if u and "login." not in login_url:
                signed_in = True
                break
            if "login." in login_url or "microsoftonline" in login_url:
                # Redirect back after sign-in
                pass
            await asyncio.sleep(2)

        if not signed_in:
            await browser.close()
            raise RuntimeError("Windows SSO did not complete — use interactive mode instead.")

        print("[refresh-browser] Signed in — fetching session key ...")
        await asyncio.sleep(1)
        await page.goto(_COPILOT_URL, wait_until="networkidle", timeout=20_000)

        # Fetch session key from inside the browser (same-origin)
        result = await page.evaluate("""async () => {
            const r = await fetch('/c/api/user/sessions/temporary', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: '{}'
            });
            const d = await r.json();
            return {status: r.status, key: d.sessionKey || '', cookie: document.cookie};
        }""")

        cookies = await ctx.cookies([_COPILOT_URL])
        cookie_header = "; ".join(f"{c['name']}={c['value']}" for c in cookies)
        session_key = result.get("key", "") if isinstance(result, dict) else ""

        await browser.close()

        return {"cookie_header": cookie_header or result.get("cookie", ""),
                "session_key": session_key}


# ---------------------------------------------------------------------------
# Save to .env
# ---------------------------------------------------------------------------

def _save(cookie_header: str, session_key: str) -> None:
    env = str(_ENV_FILE)
    if cookie_header:
        set_key(env, "COPILOT_COOKIE", cookie_header)
        os.environ["COPILOT_COOKIE"] = cookie_header
    if session_key:
        set_key(env, "COPILOT_SESSION_KEY", session_key)
        os.environ["COPILOT_SESSION_KEY"] = session_key

    print()
    print("[refresh] Saved to .env:")
    if cookie_header:
        print(f"  COPILOT_COOKIE    = {cookie_header[:60]}...")
    if session_key:
        print(f"  COPILOT_SESSION_KEY = {session_key[:50]}...")
    print()
    print("Test with:")
    print("  .venv/Scripts/python.exe tools/copilot_worker.py \"List files in tools/\"")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    args = sys.argv[1:]
    force_full = "--full" in args
    browser_only = "--browser" in args

    # ---- Mode 1: fast API refresh ----
    if not force_full and not browser_only:
        print("[refresh] Trying fast API refresh (no browser)...")
        key = _fast_refresh()
        if key:
            _save("", key)
            sys.exit(0)

    # ---- Mode 3: browser (if explicitly requested) ----
    if browser_only:
        try:
            result = asyncio.run(_browser_refresh())
            _save(result["cookie_header"], result["session_key"])
            sys.exit(0)
        except Exception as e:
            print(f"[refresh] Browser mode failed: {e}")
            sys.exit(1)

    # ---- Mode 2: interactive ----
    result = _interactive_refresh()
    if result:
        _save(result["cookie_header"], result["session_key"])
    else:
        print("[refresh] No data collected.")
        sys.exit(1)
