"""
AI worker — Microsoft Copilot via the live copilot.microsoft.com WebSocket API.

Auth (one-time setup):
  The chat API requires a logged-in Microsoft account session.
  You need TWO things from your browser:

  OPTION A — Full cookie header (recommended):
    1. Sign in to https://copilot.microsoft.com in Edge
    2. Send any message in the chat (so a WebSocket connection is opened)
    3. F12 → Network → filter by "WS" → click the "chat?api-version=2" connection
    4. Headers tab → copy the FULL "Cookie:" header value
    5. Add to .env:
         COPILOT_COOKIE=<paste full cookie header here>

  OPTION B — Temporary session key (expires, ~30min TTL):
    1. Sign in to https://copilot.microsoft.com in Edge
    2. Send any message (triggers session key acquisition)
    3. F12 → Network → filter by "temporary" → find POST /c/api/user/sessions/temporary
    4. Response tab → copy "sessionKey" value
    5. Add to .env:
         COPILOT_SESSION_KEY=<session key here>
         COPILOT_COOKIE=<Cookie header from the same session>

Protocol (reverse-engineered from copilot.microsoft.com JS bundle entry-ssr-*.js):
  REST: POST /c/api/conversations  → get conversationId
  REST: POST /c/api/user/sessions/temporary → get temporarySessionKey (requires login)
  WSS:  wss://copilot.microsoft.com/c/api/chat?api-version=2&temporarySessionKey=...
  Challenge: hashcash SHA-256 proof-of-work (difficulty usually 1–4)
  Send: {event:"send", conversationId, content:[{type:"text",text}], mode:"chat"}
  Recv events: connected → challenge → challengeResponse → send → appendText* → done

Uses a ReAct loop (TOOL:/INPUT:/FINAL:) for tool calling since Copilot has no
native function-calling API.
"""

import asyncio
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

_PROJECT_ROOT = Path(r"C:\Users\Elie\DeepFieldPro")
_VENV_PYTHON = str(_PROJECT_ROOT / ".venv" / "Scripts" / "python.exe")

_BASE_URL = "https://copilot.microsoft.com"
_WS_URL = "wss://copilot.microsoft.com/c/api/chat"
_CONV_URL = f"{_BASE_URL}/c/api/conversations"

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/132.0.0.0 Safari/537.36 Edg/131.0.2903.86"
)


@dataclass
class WorkerResult:
    text: str
    ok: bool
    error: str = ""
    timing_s: float = 0.0
    tool_calls: int = 0


# ---------------------------------------------------------------------------
# Hashcash proof-of-work solver
# ---------------------------------------------------------------------------

def _solve_hashcash(token: str, difficulty: int) -> int:
    """Find nonce n such that SHA256(token+str(n)) has `difficulty` leading zero bits."""
    full_bytes = difficulty // 8
    remaining_bits = difficulty % 8
    mask = (0xFF << (8 - remaining_bits)) & 0xFF if remaining_bits else 0

    nonce = 0
    while True:
        msg = (token + str(nonce)).encode()
        h = hashlib.sha256(msg).digest()
        ok = all(b == 0 for b in h[:full_bytes])
        if ok and remaining_bits:
            ok = (h[full_bytes] & mask) == 0
        if ok:
            return nonce
        nonce += 1


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

def _read_file(path: str) -> str:
    p = Path(path)
    if not p.is_absolute():
        p = _PROJECT_ROOT / path
    if not p.exists():
        return f"ERROR: file not found: {p}"
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return f"ERROR: {e}"


def _write_file(path: str, content: str) -> str:
    p = Path(path)
    if not p.is_absolute():
        p = _PROJECT_ROOT / path
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return f"OK: wrote {len(content)} chars to {p}"
    except Exception as e:
        return f"ERROR: {e}"


def _list_directory(path: str = ".") -> str:
    p = Path(path)
    if not p.is_absolute():
        p = _PROJECT_ROOT / path
    if not p.exists():
        return f"ERROR: directory not found: {p}"
    try:
        entries = sorted(p.iterdir(), key=lambda x: (x.is_file(), x.name))
        return "\n".join(
            f"{'[DIR] ' if e.is_dir() else '[FILE]'} {e.name}" for e in entries
        ) or "(empty)"
    except Exception as e:
        return f"ERROR: {e}"


def _run_python(code: str) -> str:
    try:
        r = subprocess.run(
            [_VENV_PYTHON, "-c", code],
            capture_output=True, text=True, timeout=30, cwd=str(_PROJECT_ROOT),
        )
        parts = []
        if r.stdout:
            parts.append(f"STDOUT:\n{r.stdout[-4000:]}")
        if r.stderr:
            parts.append(f"STDERR:\n{r.stderr[-2000:]}")
        if r.returncode != 0:
            parts.append(f"exit_code={r.returncode}")
        return "\n".join(parts) or "(no output)"
    except subprocess.TimeoutExpired:
        return "ERROR: timeout after 30s"
    except Exception as e:
        return f"ERROR: {e}"


def _run_shell(command: str) -> str:
    try:
        r = subprocess.run(
            command, shell=True, capture_output=True, text=True,
            timeout=30, cwd=str(_PROJECT_ROOT),
        )
        parts = []
        if r.stdout:
            parts.append(r.stdout[-4000:])
        if r.stderr:
            parts.append(f"STDERR: {r.stderr[-2000:]}")
        if r.returncode != 0:
            parts.append(f"exit_code={r.returncode}")
        return "\n".join(parts) or "(no output)"
    except subprocess.TimeoutExpired:
        return "ERROR: timeout after 30s"
    except Exception as e:
        return f"ERROR: {e}"


_TOOL_FNS = {
    "read_file":      lambda a: _read_file(a.get("path", "")),
    "write_file":     lambda a: _write_file(a.get("path", ""), a.get("content", "")),
    "list_directory": lambda a: _list_directory(a.get("path", ".")),
    "run_python":     lambda a: _run_python(a.get("code", "")),
    "run_shell":      lambda a: _run_shell(a.get("command", "")),
}


# ---------------------------------------------------------------------------
# ReAct helpers
# ---------------------------------------------------------------------------

def _parse_tool_call(text: str):
    tool_m = re.search(r"TOOL:\s*(\w+)", text, re.IGNORECASE)
    input_m = re.search(r"INPUT:\s*(\{.*?\})", text, re.DOTALL | re.IGNORECASE)
    if not (tool_m and input_m):
        return None, None
    try:
        return tool_m.group(1).strip().lower(), json.loads(input_m.group(1))
    except json.JSONDecodeError:
        return tool_m.group(1).strip().lower(), {}


def _extract_final(text: str):
    m = re.search(r"FINAL:\s*(.*)", text, re.DOTALL | re.IGNORECASE)
    return m.group(1).strip() if m else None


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_SYSTEM = """\
You are an autonomous coding agent for the DeepFieldPro project.
Project root: C:/Users/Elie/DeepFieldPro
Stack: Python 3.12, Flask, SQLite, Windows, venv at .venv/

Tools available:
  read_file(path)            — read a file
  write_file(path, content)  — write/overwrite a file
  list_directory(path)       — list directory contents
  run_python(code)           — execute Python in the project venv
  run_shell(command)         — run a shell command

STRICT FORMAT:
  To call a tool:
    TOOL: <name>
    INPUT: {"arg": "value"}
  When done:
    FINAL: <answer>

Rules: one tool per response, never mix TOOL and FINAL.\
"""


# ---------------------------------------------------------------------------
# Async WebSocket chat core
# ---------------------------------------------------------------------------

async def _chat_once(
    prompt: str,
    cookie_header: str,
    session_key: str,
    timeout: int,
) -> tuple[bool, str]:
    """
    Open a fresh Copilot conversation and send one prompt.
    Returns (ok, text).
    """
    try:
        import websockets
    except ImportError:
        return False, "websockets not installed — run: pip install 'websockets>=14'"

    # 1. Create conversation via REST
    http_sess = requests.Session()
    http_sess.headers.update({
        "User-Agent": _UA,
        "Cookie": cookie_header,
        "Content-Type": "application/json",
        "Referer": "https://copilot.microsoft.com/",
        "Origin": "https://copilot.microsoft.com",
    })
    try:
        r = http_sess.post(_CONV_URL, json={}, timeout=10)
        r.raise_for_status()
        conv_id = r.json()["id"]
        # Merge any new cookies the server set
        if r.headers.get("Set-Cookie"):
            for c in http_sess.cookies:
                cookie_header = _merge_cookie(cookie_header, c.name, c.value)
    except Exception as e:
        return False, f"Failed to create conversation: {e}"

    # 2. Build WebSocket URL
    client_session_id = str(uuid.uuid4())
    ws_url = f"{_WS_URL}?api-version=2&clientSessionId={client_session_id}"
    if session_key:
        ws_url += f"&temporarySessionKey={session_key}"

    headers = {
        "Cookie": cookie_header,
        "Origin": _BASE_URL,
        "User-Agent": _UA,
        "Referer": f"https://copilot.microsoft.com/chats/{conv_id}",
    }

    response_parts: list[str] = []
    deadline = time.time() + timeout

    try:
        async with websockets.connect(
            ws_url, additional_headers=headers, open_timeout=15
        ) as ws:
            challenge_solved = False

            # 3. Handshake loop: wait for connected + optional challenge
            async def recv_with_timeout(t: float) -> dict | None:
                remaining = deadline - time.time()
                if remaining <= 0:
                    return None
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=min(t, remaining))
                    return json.loads(raw)
                except (asyncio.TimeoutError, Exception):
                    return None

            # Wait for connected
            evt = await recv_with_timeout(10)
            if not evt or evt.get("event") != "connected":
                return False, f"Expected 'connected' event, got: {evt}"

            # Wait briefly for possible challenge (1.5s)
            evt = await recv_with_timeout(1.5)
            if evt and evt.get("event") == "challenge":
                method = evt.get("method", "")
                param = evt.get("parameter", "")

                if method == "hashcash":
                    parts = param.split(":")
                    if len(parts) == 2:
                        token, diff_str = parts
                        difficulty = int(diff_str)
                        nonce = await asyncio.to_thread(_solve_hashcash, token, difficulty)
                        resp = json.dumps({
                            "event": "challengeResponse",
                            "method": "hashcash",
                            "token": str(nonce),
                        })
                        await ws.send(resp)
                        challenge_solved = True
                elif method == "copilot":
                    a = int(param)
                    token = str(round((a ** 3 / 100 + a * 25) % 22))
                    resp = json.dumps({
                        "event": "challengeResponse",
                        "method": "copilot",
                        "token": token,
                    })
                    await ws.send(resp)
                    challenge_solved = True
                # If challenge but unknown method: proceed anyway

            # 4. Send user message
            send_msg = json.dumps({
                "event": "send",
                "conversationId": conv_id,
                "content": [{"type": "text", "text": prompt}],
                "mode": "chat",
                "context": {},
            })
            await ws.send(send_msg)

            # 5. Collect response events
            while time.time() < deadline:
                remaining = deadline - time.time()
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=min(15, remaining))
                    data = json.loads(raw)
                except asyncio.TimeoutError:
                    break
                except Exception:
                    break

                event = data.get("event", "")
                if event == "appendText":
                    response_parts.append(data.get("text", ""))
                elif event in ("done", "disconnecting"):
                    break
                elif event == "error":
                    err = data.get("errorCode", "unknown")
                    if err != "invalid-event":
                        return False, f"Server error: {err}"

    except Exception as e:
        return False, f"WebSocket error: {e}"

    text = "".join(response_parts).strip()
    if not text:
        return False, "Empty response from Copilot"
    return True, text


# ---------------------------------------------------------------------------
# Async ReAct loop
# ---------------------------------------------------------------------------

def _merge_cookie(header: str, name: str, value: str) -> str:
    """Add/update a cookie in a cookie header string."""
    if f"{name}=" in header:
        return header  # already present
    return header.rstrip("; ") + f"; {name}={value}"


async def _run_async(
    prompt: str,
    cookie_header: str,
    session_key: str,
    timeout: int,
    max_rounds: int,
) -> WorkerResult:
    t0 = time.time()
    tool_calls_total = 0
    current_prompt = f"{_SYSTEM}\n\nTask: {prompt}"

    for _round in range(max_rounds):
        if time.time() - t0 > timeout:
            return WorkerResult(
                "", False, f"Timeout after {timeout}s",
                timing_s=round(time.time() - t0, 1),
                tool_calls=tool_calls_total,
            )

        ok, text = await _chat_once(
            current_prompt, cookie_header, session_key,
            timeout=min(60, timeout - (time.time() - t0)),
        )
        if not ok:
            return WorkerResult(
                "", False, text,
                timing_s=round(time.time() - t0, 1),
                tool_calls=tool_calls_total,
            )

        final = _extract_final(text)
        if final:
            return WorkerResult(
                text=final, ok=True,
                timing_s=round(time.time() - t0, 1),
                tool_calls=tool_calls_total,
            )

        tool_name, tool_args = _parse_tool_call(text)
        if tool_name and tool_name in _TOOL_FNS:
            result = _TOOL_FNS[tool_name](tool_args)
            tool_calls_total += 1
            current_prompt = (
                f"{_SYSTEM}\n\n"
                f"Original task: {prompt}\n\n"
                f"Previous action: {text[:500]}\n\n"
                f"Tool result for {tool_name}:\n{result}\n\n"
                "Continue. Call the next tool or output FINAL: <answer>."
            )
            continue

        # Plain answer with no markers — treat as final
        if text:
            return WorkerResult(
                text=text, ok=True,
                timing_s=round(time.time() - t0, 1),
                tool_calls=tool_calls_total,
            )

        return WorkerResult(
            "", False, "Empty response",
            timing_s=round(time.time() - t0, 1),
            tool_calls=tool_calls_total,
        )

    return WorkerResult(
        "", False, f"Exceeded {max_rounds} rounds",
        timing_s=round(time.time() - t0, 1),
        tool_calls=tool_calls_total,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _get_auth() -> tuple[str, str, str | None]:
    """
    Returns (cookie_header, session_key, error_msg).
    error_msg is None if we have enough to attempt a connection.

    Priority:
    1. COPILOT_COOKIE + COPILOT_SESSION_KEY  → full session
    2. COPILOT_COOKIE only                   → try to fetch session key live
    3. BING_U_COOKIE (legacy)                → last resort, likely anon-only
    """
    cookie = (
        os.getenv("COPILOT_COOKIE", "").strip()
        or os.getenv("BING_U_COOKIE", "").strip()
    )
    session_key = os.getenv("COPILOT_SESSION_KEY", "").strip()

    if not cookie:
        return "", "", (
            "COPILOT_COOKIE not set. To fix:\n"
            "  1. Sign in to https://copilot.microsoft.com in Edge\n"
            "  2. Send a message (activates session)\n"
            "  3. F12 → Network → WS tab → click 'chat?api-version=2'\n"
            "  4. Headers → copy the full Cookie: header value\n"
            "  5. Add to .env:  COPILOT_COOKIE=<paste here>"
        )

    # If no session key, try to fetch one from the API
    if not session_key:
        session_key = _fetch_session_key(cookie)

    return cookie, session_key, None


def _fetch_session_key(cookie_header: str) -> str:
    """Try to get a temporarySessionKey from the API. Returns '' on failure."""
    sess = requests.Session()
    sess.headers.update({
        "User-Agent": _UA,
        "Cookie": cookie_header,
        "Content-Type": "application/json",
        "Referer": "https://copilot.microsoft.com/",
        "Origin": "https://copilot.microsoft.com",
    })
    try:
        r = sess.post(
            f"{_BASE_URL}/c/api/user/sessions/temporary",
            json={}, timeout=10,
        )
        if r.status_code == 200:
            key = r.json().get("sessionKey", "")
            if key:
                print(f"[copilot-worker] Got session key ({len(key)} chars)")
                return key
        print(f"[copilot-worker] Session key fetch failed: {r.status_code} {r.text[:80]}")
    except Exception as e:
        print(f"[copilot-worker] Session key fetch error: {e}")
    return ""


def run_task(prompt: str, *, timeout: int = 120, max_tool_rounds: int = 15) -> WorkerResult:
    """Send prompt to Microsoft Copilot with a ReAct tool-calling loop."""
    cookie_header, session_key, err = _get_auth()
    if err:
        return WorkerResult("", False, err)
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    return asyncio.run(_run_async(prompt, cookie_header, session_key, timeout, max_tool_rounds))


def run_build_task(task: str, *, timeout: int = 300) -> WorkerResult:
    """Autonomous build/edit task — same as run_task but longer timeout."""
    return run_task(task, timeout=timeout)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    load_dotenv()

    cookie_header, session_key, err = _get_auth()
    if err:
        print(err, file=sys.stderr)
        sys.exit(1)

    prompt = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else (
        "List the files in the tools/ directory of this project."
    )
    print(f"[copilot-worker] cookie={len(cookie_header)}chars  session_key={bool(session_key)}  prompt={prompt!r}\n")
    r = run_task(prompt, timeout=60)
    print(f"ok={r.ok}  time={r.timing_s}s  tool_calls={r.tool_calls}")
    print("---")
    if r.ok:
        print(r.text)
    else:
        print("ERROR:", r.error, file=sys.stderr)
    sys.exit(0 if r.ok else 1)
