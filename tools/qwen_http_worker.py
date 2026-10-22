"""
Qwen Web Chat HTTP client — calls chat.qwen.ai/api/v2/chat/completions directly.

How long does a capture last?
  Alibaba's TianMaDun (bx-ua) ties the fingerprint to the specific session cookies
  active at capture time. The session cookies (acw_tc, isg, sca, xlly_s, atpsida)
  expire after ~4-8 hours, which invalidates the bx-ua along with them.
  So you need to recapture the full cookie + bx-ua every ~4-8 hours.

Setup (recapture when you get SESSION_EXPIRED errors):
  Open DevTools → Network → find the chat/completions POST → Request Headers.
  Copy and paste into .env:

    QWEN_WEB_COOKIE  = <entire cookie: header line, all cookies>
    QWEN_WEB_BX_UA   = <bx-ua value>
    QWEN_WEB_BX_UMID = <bx-umidtoken value>

  When QWEN_WEB_COOKIE expires, the worker falls back to the CDP bridge
  (tools/qwen_bridge.py) automatically if the Qwen desktop app is running.

Usage:
    from tools.qwen_http_worker import chat, run_task, run_build_task

    r = chat("What is Dixon-Coles?")
    print(r.text)
"""

import json
import os
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv

load_dotenv()

_API_URL = "https://chat.qwen.ai/api/v2/chat/completions"
_DEFAULT_MODEL = "qwen3.7-plus"

_SESSION_EXPIRED_CODES = {"FAIL_SYS_USER_VALIDATE", "FAIL_SYS_TOKEN_VALIDATE"}


@dataclass
class WorkerResult:
    text: str
    ok: bool
    error: str = ""
    timing_s: float = 0.0


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


def _get_auth() -> tuple[str, str, str]:
    cookie = os.getenv("QWEN_WEB_COOKIE", "").strip()
    bx_ua = os.getenv("QWEN_WEB_BX_UA", "").strip()
    bx_umid = os.getenv("QWEN_WEB_BX_UMID", "").strip()
    missing = [k for k, v in [("QWEN_WEB_COOKIE", cookie), ("QWEN_WEB_BX_UA", bx_ua), ("QWEN_WEB_BX_UMID", bx_umid)] if not v]
    if missing:
        raise RuntimeError(
            f"Missing env vars: {', '.join(missing)}\n"
            "Open DevTools → Network → chat/completions POST → Request Headers.\n"
            "Paste the entire cookie: line into QWEN_WEB_COOKIE.\n"
            "Session lasts ~4-8h; recapture when you see SESSION_EXPIRED errors."
        )
    return cookie, bx_ua, bx_umid


# ---------------------------------------------------------------------------
# Request builder
# ---------------------------------------------------------------------------


def _build_headers(cookie: str, bx_ua: str, bx_umid: str, request_id: str) -> dict:
    tz_str = datetime.now(timezone.utc).astimezone().strftime(
        "%a %b %d %Y %H:%M:%S GMT%z"
    )
    return {
        "accept": "application/json",
        "accept-encoding": "gzip, deflate, br, zstd",
        "accept-language": "en-US,en;q=0.9",
        "bx-ua": bx_ua,
        "bx-umidtoken": bx_umid,
        "connection": "keep-alive",
        "content-type": "application/json",
        "cookie": cookie,
        "host": "chat.qwen.ai",
        "origin": "https://chat.qwen.ai",
        "referer": "https://chat.qwen.ai/c/guest",
        "sec-ch-ua": '"Google Chrome";v="149", "Chromium";v="149", "Not)A;Brand";v="24"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "source": "web",
        "timezone": tz_str,
        "user-agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/149.0.0.0 Safari/537.36"
        ),
        "version": "0.2.66",
        "x-accel-buffering": "no",
        "x-request-id": request_id,
    }


def _build_body(prompt: str, model: str) -> tuple[str, dict]:
    chat_id = str(uuid.uuid4())
    parent_id = str(uuid.uuid4())
    msg_id = str(uuid.uuid4())

    body = {
        "stream": True,
        "version": "2.1",
        "incremental_output": True,
        "chat_id": chat_id,
        "chat_mode": "guest",
        "model": model,
        "parent_id": parent_id,
        "timestamp": int(time.time()),
        "messages": [
            {
                "fid": msg_id,
                "parentId": parent_id,
                "role": "user",
                "content": prompt,
                "contentType": "text",
                "status": "done",
            }
        ],
    }
    return chat_id, body


# ---------------------------------------------------------------------------
# SSE / response parser
# ---------------------------------------------------------------------------


def _parse_response(resp: requests.Response) -> tuple[bool, str]:
    """
    Returns (ok, text_or_error).
    Handles both SSE (normal) and JSON error bodies (bot-detection / rate-limit).
    """
    raw = b""
    parts = []

    for raw_line in resp.iter_lines():
        if not raw_line:
            continue
        line = raw_line.decode("utf-8", errors="replace") if isinstance(raw_line, bytes) else raw_line
        raw += raw_line if isinstance(raw_line, bytes) else raw_line.encode()

        # Check for JSON error body (not SSE) — Alibaba security/rate-limit
        if line.startswith("{") and not parts:
            try:
                err = json.loads(line)
                ret = err.get("ret", [])
                for code in ret:
                    if code in _SESSION_EXPIRED_CODES:
                        return False, f"SESSION_EXPIRED ({code}) — recapture cookies from DevTools"
                if ret:
                    return False, f"API error: {ret}"
            except json.JSONDecodeError:
                pass

        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if data in ("[DONE]", ""):
            break
        try:
            chunk = json.loads(data)
        except json.JSONDecodeError:
            continue
        choices = chunk.get("choices", [])
        if choices:
            content = choices[0].get("delta", {}).get("content", "")
            if content:
                parts.append(content)

    return (True, "".join(parts).strip()) if parts else (False, "Empty response")


# ---------------------------------------------------------------------------
# CDP fallback
# ---------------------------------------------------------------------------


def _auto_refresh() -> bool:
    """
    Try to capture a fresh session automatically, in priority order:
    1. CDP extract from running Qwen desktop app (fastest, no browser launch)
    2. Playwright scraper via saved browser profile (headless)
    Returns True if any method succeeded.
    """
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))

    # Method 1: CDP from Qwen.exe (already running)
    try:
        from tools.qwen_bridge import extract_session
        result = extract_session(timeout=45)
        if result and result.get("cookie"):
            return True
    except Exception as e:
        print(f"[qwen-http] CDP extract failed: {e}")

    # Method 2: Playwright scraper (needs --setup to have been run once)
    try:
        from tools.web_scraper import capture_qwen_session
        result = capture_qwen_session(headless=True)
        if result:
            return True
    except Exception as e:
        print(f"[qwen-http] Playwright scraper failed: {e}")

    return False


def _cdp_fallback(prompt: str, timeout: int) -> WorkerResult:
    try:
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from tools.qwen_bridge import chat_via_fetch
        r = chat_via_fetch(prompt, timeout=min(timeout, 90))
        return WorkerResult(text=r.text, ok=r.ok, error=r.error, timing_s=r.timing_s)
    except Exception as e:
        return WorkerResult("", False, f"CDP fallback failed: {e}")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def chat(
    prompt: str,
    model: str = _DEFAULT_MODEL,
    timeout: int = 120,
    cdp_fallback: bool = True,
) -> WorkerResult:
    """
    Send prompt to chat.qwen.ai via the web API.

    Session lasts ~4-8h. When it expires you'll get a SESSION_EXPIRED error
    and the worker automatically falls back to the CDP bridge (qwen_bridge.py)
    if the Qwen desktop app is running and cdp_fallback=True.

    Recapture: DevTools → Network → chat/completions POST → paste full cookie:
    header into QWEN_WEB_COOKIE, bx-ua into QWEN_WEB_BX_UA, bx-umidtoken into
    QWEN_WEB_BX_UMID.
    """
    t0 = time.time()

    # Primary: in-browser fetch via CDP (fast, no bot-detection, ~5-10s)
    # The Python HTTP path always fails (TianMaDun rejects non-browser requests)
    if cdp_fallback:
        r = _cdp_fallback(prompt, timeout)
        if r.ok:
            return r
        # CDP not available — fall through to Python HTTP attempt

    try:
        cookie, bx_ua, bx_umid = _get_auth()
    except RuntimeError as e:
        return WorkerResult("", False, str(e))

    chat_id, body = _build_body(prompt, model)
    headers = _build_headers(cookie, bx_ua, bx_umid, str(uuid.uuid4()))

    try:
        resp = requests.post(
            f"{_API_URL}?chat_id={chat_id}",
            headers=headers,
            json=body,
            stream=True,
            timeout=timeout,
        )
    except requests.RequestException as e:
        err = f"Request failed: {e}"
        return _cdp_fallback(prompt, timeout) if cdp_fallback else WorkerResult("", False, err)

    if resp.status_code not in (200,):
        err = f"HTTP {resp.status_code}: {resp.text[:200]}"
        return _cdp_fallback(prompt, timeout) if cdp_fallback else WorkerResult("", False, err, round(time.time() - t0, 1))

    ok, result = _parse_response(resp)

    if not ok:
        if "SESSION_EXPIRED" in result:
            print(f"[qwen-http] {result}")
            # Auto-refresh: launch browser to capture a fresh session, then retry
            print("[qwen-http] auto-refreshing session …")
            if _auto_refresh():
                # Reload fresh credentials and retry once
                try:
                    cookie, bx_ua, bx_umid = _get_auth()
                    chat_id2, body2 = _build_body(prompt, model)
                    headers2 = _build_headers(cookie, bx_ua, bx_umid, str(uuid.uuid4()))
                    resp2 = requests.post(
                        f"{_API_URL}?chat_id={chat_id2}",
                        headers=headers2, json=body2, stream=True, timeout=timeout,
                    )
                    if resp2.status_code == 200:
                        ok2, result2 = _parse_response(resp2)
                        if ok2 and result2:
                            return WorkerResult(text=result2, ok=True, timing_s=round(time.time() - t0, 1))
                except Exception as e:
                    result = f"retry after refresh failed: {e}"
            # Scraper refresh failed or retry failed — fall back to CDP
            if cdp_fallback:
                print("[qwen-http] falling back to CDP bridge")
                return _cdp_fallback(prompt, timeout)
        return WorkerResult("", False, result, round(time.time() - t0, 1))

    return WorkerResult(text=result, ok=True, timing_s=round(time.time() - t0, 1))


def run_task(prompt: str, *, timeout: int = 120, **_) -> WorkerResult:
    return chat(prompt, timeout=timeout)


def run_build_task(task: str, timeout: int = 300) -> WorkerResult:
    return chat(task, timeout=timeout)


# ---------------------------------------------------------------------------
# CLI smoke test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    prompt = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "Reply with only the word ONLINE."
    print(f"[qwen-http] -> {prompt!r}")
    r = chat(prompt, timeout=60)
    print(f"[qwen-http] ok={r.ok}  time={r.timing_s}s")
    if r.ok:
        print(r.text)
    else:
        print(f"ERROR: {r.error}", file=sys.stderr)
        sys.exit(1)
