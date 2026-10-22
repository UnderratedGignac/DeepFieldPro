"""
Copilot cookie harvester + launcher.

Opens a fresh Chromium window, navigates to bing.com, waits for you to sign in,
then automatically extracts the _U auth cookie, writes it to .env, and (optionally)
fires a task through the Copilot worker.

Usage (CLI):
    # Just harvest the cookie and update .env:
    .venv\\Scripts\\python.exe tools\\copilot_auth.py

    # Harvest + run a task:
    .venv\\Scripts\\python.exe tools\\copilot_auth.py "List files in tools/"

Usage (from code):
    from tools.copilot_auth import harvest_cookie, launch

    cookie = harvest_cookie()               # opens browser, gets _U, writes .env
    result = launch("List files in tools/") # harvest + run_task in one call
"""

import os
import re
import sys
import time
from pathlib import Path

from dotenv import load_dotenv, set_key

_PROJECT_ROOT = Path(r"C:\Users\Elie\DeepFieldPro")
_ENV_FILE = _PROJECT_ROOT / ".env"

# Paths where Edge stores user profiles on Windows
_EDGE_USER_DATA = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "Edge" / "User Data"
_CHROME_USER_DATA = Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "User Data"


# ---------------------------------------------------------------------------
# Cookie harvester
# ---------------------------------------------------------------------------

def harvest_cookie(poll_interval: float = 2.0, sign_in_timeout_s: int = 120) -> str:
    """
    Launch a fresh Chromium window, navigate to bing.com, and poll for the _U
    cookie. If you're not signed in yet, a prompt appears in the browser window
    asking you to sign in — the script waits up to sign_in_timeout_s seconds.

    Once the cookie is found it is written to .env and returned.
    """
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        # Use real Edge with stealth flags — Microsoft blocks Playwright's bundled Chromium
        browser = pw.chromium.launch(
            channel="msedge",
            headless=False,
            args=[
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-blink-features=AutomationControlled",
            ],
            ignore_default_args=["--enable-automation"],
        )
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0"
            )
        )
        context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            window.chrome = { runtime: {} };
        """)
        page = context.new_page()

        print("[copilot-auth] Opening bing.com ...")
        page.goto("https://www.bing.com", wait_until="domcontentloaded", timeout=30_000)

        # Check if already signed in
        cookies = context.cookies(["https://www.bing.com"])
        u_cookie = next((c["value"] for c in cookies if c["name"] == "_U"), None)

        if not u_cookie:
            # Inject a visible banner asking user to sign in
            page.evaluate("""() => {
                const div = document.createElement('div');
                div.id = '__deepfield_prompt__';
                div.style.cssText = `
                    position:fixed; top:0; left:0; right:0; z-index:999999;
                    background:#0078d4; color:#fff; font-size:18px; font-weight:bold;
                    padding:16px 24px; text-align:center; font-family:sans-serif;
                    box-shadow:0 2px 8px rgba(0,0,0,.4);
                `;
                div.textContent = '🔑  Sign in to Bing with your Microsoft account — the window will close automatically once done.';
                document.body.prepend(div);
            }""")

            print("[copilot-auth] Waiting for sign-in (blue banner visible in browser) ...")
            deadline = time.time() + sign_in_timeout_s
            while time.time() < deadline:
                time.sleep(poll_interval)
                cookies = context.cookies(["https://www.bing.com"])
                u_cookie = next((c["value"] for c in cookies if c["name"] == "_U"), None)
                if u_cookie:
                    break

        browser.close()

    if not u_cookie:
        raise RuntimeError(
            f"_U cookie not found after {sign_in_timeout_s}s. "
            "Sign in to Bing with your Microsoft account when the browser opens."
        )

    # Write to .env
    set_key(str(_ENV_FILE), "BING_U_COOKIE", u_cookie)
    os.environ["BING_U_COOKIE"] = u_cookie
    print(f"[copilot-auth] _U cookie captured ({len(u_cookie)} chars) → written to .env")
    return u_cookie


# ---------------------------------------------------------------------------
# General-purpose web scraper (bonus utility)
# ---------------------------------------------------------------------------

def scrape(
    url: str,
    *,
    wait_for: str | None = None,
    extract_cookies: bool = False,
    headless: bool = True,
    timeout_s: int = 30,
) -> dict:
    """
    Fetch any URL with a real browser and return:
      {
        "url":     str,       # final URL after redirects
        "title":   str,       # page title
        "text":    str,       # visible text content
        "html":    str,       # full HTML
        "cookies": list[dict] # all cookies (only if extract_cookies=True)
      }

    Args:
        url:             Page to fetch.
        wait_for:        CSS selector to wait for before extracting (optional).
        extract_cookies: If True, include cookies in the return dict.
        headless:        Run without visible window (default True).
        timeout_s:       Page load timeout in seconds.
    """
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=headless)
        page = browser.new_page(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        )

        page.goto(url, wait_until="domcontentloaded", timeout=timeout_s * 1_000)

        if wait_for:
            page.wait_for_selector(wait_for, timeout=timeout_s * 1_000)

        result = {
            "url":   page.url,
            "title": page.title(),
            "text":  page.inner_text("body"),
            "html":  page.content(),
        }

        if extract_cookies:
            result["cookies"] = page.context.cookies()

        browser.close()

    return result


# ---------------------------------------------------------------------------
# launch() — harvest cookie then run a Copilot task
# ---------------------------------------------------------------------------

def launch(prompt: str, *, force_refresh: bool = False, timeout: int = 120) -> "WorkerResult":
    """
    Harvest the Bing _U cookie (if missing or force_refresh=True) then
    immediately dispatch a task to the Copilot worker.

    Returns a WorkerResult from tools.copilot_worker.
    """
    load_dotenv(_ENV_FILE)

    existing = os.getenv("BING_U_COOKIE", "").strip()
    if not existing or force_refresh:
        print("[copilot-auth] No cookie in .env — harvesting from browser ...")
        harvest_cookie()
    else:
        print(f"[copilot-auth] Using existing cookie ({len(existing)} chars)")

    from tools.copilot_worker import run_task
    return run_task(prompt, timeout=timeout)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    load_dotenv(_ENV_FILE)

    prompt = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else None

    # Step 1: harvest cookie
    print("[copilot-auth] Harvesting _U cookie from browser ...")
    try:
        cookie = harvest_cookie()
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    if not prompt:
        print("[copilot-auth] Cookie harvested. Pass a prompt as an argument to also run a task.")
        sys.exit(0)

    # Step 2: run task
    print(f"\n[copilot-auth] Running task: {prompt!r}\n")
    from tools.copilot_worker import run_task

    r = run_task(prompt, timeout=120)
    print(f"\nok={r.ok}  time={r.timing_s}s  tool_calls={r.tool_calls}")
    print("---")
    if r.ok:
        print(r.text)
    else:
        print("ERROR:", r.error, file=sys.stderr)
    sys.exit(0 if r.ok else 1)
