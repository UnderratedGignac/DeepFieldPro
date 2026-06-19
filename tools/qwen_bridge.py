"""
Qwen slave bridge — drives the Qwen Electron desktop app via raw CDP WebSocket.

Architecture:
    Master (Claude Code / orchestrator)
        |
        v  subprocess: Qwen.exe --remote-debugging-port=9223 --remote-allow-origins=*
    Qwen Electron (webview: chat.qwen.ai)
        |
        v  raw CDP WebSocket
           Page.navigate -> fresh chat home page
           Input.dispatchMouseEvent -> focus textarea
           Input.insertText -> type the prompt
           Input.dispatchKeyEvent Enter -> submit
           Poll .chat-content.innerText for stable AI response
    Response text extracted -> returned to master

Usage:
    from tools.qwen_bridge import run_task, QwenResult

    result = run_task("Explain the Dixon-Coles model in 2 sentences")
    print(result.text)

Requirements:
    - Qwen desktop app installed at the path in QWEN_EXE
    - websocket-client: .venv\\Scripts\\pip install websocket-client
    - User logged into Qwen (done once interactively)
"""

import json
import socket
import subprocess
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path

QWEN_EXE = r"C:\Users\Elie\AppData\Local\Programs\Qwen\Qwen.exe"
CDP_PORT = 9223
CDP_HTTP = f"http://localhost:{CDP_PORT}"
_HOME_URL = "https://chat.qwen.ai/"

# CSS selectors — verified via DOM inspection 2026-06-19
_TEXTAREA_SEL = "textarea.message-input-textarea"
_RESPONSE_SEL = ".chat-content"

_DISCLAIMER_PREFIXES = (
    "Fast\nAI-generated content",
    "AI-generated content may not be accurate",
)


@dataclass
class QwenResult:
    text: str
    ok: bool
    error: str = ""
    timing_s: float = 0.0


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        try:
            s.connect(("localhost", port))
            return True
        except OSError:
            return False


def _wait_port(port: int, timeout: int = 30) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _port_open(port):
            return True
        time.sleep(0.5)
    return False


def _get_webview_ws() -> str:
    """Return the WebSocket URL for the chat.qwen.ai webview target."""
    raw = urllib.request.urlopen(f"{CDP_HTTP}/json", timeout=5).read()
    targets = json.loads(raw)
    for t in targets:
        if "chat.qwen.ai" in t.get("url", "") and t.get("type") == "webview":
            return t["webSocketDebuggerUrl"]
    for t in targets:
        if "chat.qwen.ai" in t.get("url", ""):
            return t["webSocketDebuggerUrl"]
    raise RuntimeError(
        f"chat.qwen.ai webview not found in CDP targets: {[t.get('url') for t in targets]}"
    )


def _cdp_session(ws_url: str):
    import websocket

    return websocket.create_connection(ws_url, timeout=10, header={"Origin": CDP_HTTP})


def _send(ws, method: str, params: dict | None = None, wait: float = 10) -> dict:
    """Send one CDP command and return its result dict."""
    if not hasattr(_send, "_id"):
        _send._id = 0
    _send._id += 1
    msg_id = _send._id

    ws.send(json.dumps({"id": msg_id, "method": method, "params": params or {}}))
    deadline = time.time() + wait
    while time.time() < deadline:
        try:
            ws.settimeout(min(2.0, max(0.1, deadline - time.time())))
            r = json.loads(ws.recv())
            if r.get("id") == msg_id:
                return r.get("result", {})
            # Event or other response — skip and keep waiting
        except Exception:
            pass  # recv timeout or parse error; keep looping until deadline
    return {}


def _js(ws, expression: str, wait: float = 10) -> str:
    """Evaluate JS and return string value (bool/None normalised to string)."""
    result = _send(
        ws,
        "Runtime.evaluate",
        {
            "expression": expression,
            "returnByValue": True,
            "awaitPromise": False,
        },
        wait=wait,
    )
    val = result.get("result", {}).get("value", "")
    if val is None:
        return ""
    if isinstance(val, bool):
        return "true" if val else "false"
    return str(val) if not isinstance(val, str) else val


def _mouse_click(ws, x: float, y: float) -> None:
    """Dispatch a real left-click at (x, y) in CSS pixels."""
    for etype in ("mousePressed", "mouseReleased"):
        _send(
            ws,
            "Input.dispatchMouseEvent",
            {
                "type": etype,
                "x": x,
                "y": y,
                "button": "left",
                "clickCount": 1,
            },
        )
        time.sleep(0.04)


def _key_event(ws, key: str, code: str, vk: int, modifiers: int = 0) -> None:
    for etype in ("keyDown", "keyUp"):
        _send(
            ws,
            "Input.dispatchKeyEvent",
            {
                "type": etype,
                "key": key,
                "code": code,
                "nativeVirtualKeyCode": vk,
                "windowsVirtualKeyCode": vk,
                "modifiers": modifiers,
            },
        )
        time.sleep(0.04)


def _enable_mcp(ws) -> bool:
    """
    Click + → MCP to activate MCP tools for this chat.
    Mirrors the timing that was confirmed working in the diagnostic script.
    Returns True if the MCP chip confirmed active.
    """
    # 1. JS-click the + (mode-select-open) button
    result = _js(
        ws,
        """
    (function(){
        var el = document.querySelector('.mode-select-open');
        if (!el) return 'NO_PLUS';
        el.dispatchEvent(new MouseEvent('click', {bubbles:true, cancelable:true, view:window}));
        return 'ok';
    })()
    """,
    )
    if result != "ok":
        return False

    # 2. Wait 1s for the Ant Design dropdown to render (same as confirmed debug timing)
    time.sleep(1.0)

    # 3. Find the "MCP" LI and JS-click it
    result = _js(
        ws,
        """
    (function(){
        var items = document.querySelectorAll('li, [role="menuitem"]');
        for (var i = 0; i < items.length; i++) {
            var el = items[i];
            var r = el.getBoundingClientRect();
            if (r.width === 0 || r.height === 0) continue;
            if ((el.innerText || '').trim() === 'MCP') {
                el.dispatchEvent(new MouseEvent('click', {bubbles:true, cancelable:true, view:window}));
                return 'clicked';
            }
        }
        return 'NOT_FOUND';
    })()
    """,
    )
    if result != "clicked":
        return False

    # 4. Wait 0.8s for the chip to appear
    time.sleep(0.8)

    # 5. Confirm MCP chip is in the input bar
    chip = _js(
        ws, "(document.querySelector('.message-input') || {innerText:''}).innerText"
    )
    return "MCP" in chip


def _auto_approve_mcp(ws) -> bool:
    """
    If Qwen shows a 'Allow in this chat' MCP permission dialog, click it.
    Called every polling cycle. Returns True if a dialog was approved.
    """
    result = _js(
        ws,
        """
    (function(){
        var btns = document.querySelectorAll('button');
        for (var i = 0; i < btns.length; i++) {
            var txt = (btns[i].innerText || '').trim();
            if (txt === 'Allow in this chat' || txt === 'Allow once') {
                btns[i].dispatchEvent(new MouseEvent('click', {bubbles:true, cancelable:true, view:window}));
                return 'approved';
            }
        }
        return '';
    })()
    """,
    )
    return result == "approved"


def _chat_text(ws) -> str:
    return _js(
        ws,
        f"""
    (function(){{
        var e = document.querySelectorAll('{_RESPONSE_SEL}');
        return e.length ? e[e.length-1].innerText : '';
    }})()
    """,
    ).strip()


def _extract_response(raw: str, prompt: str) -> str:
    """
    Extract AI response from full .chat-content innerText.

    Multi-turn conversations accumulate in one element:
        <prompt1>\\n\\n<response1>\\n\\n<prompt2>\\n\\n<response2>\\n<disclaimer>

    Also handles Qwen Studio A/B comparison format:
        Which response do you prefer? ...
        Response 1
        <text>
        I prefer this response
        Response 2
        <text>
        I prefer this response
    """
    import re

    text = raw.strip()
    prompt_s = prompt.strip()

    # Strip the leading user prompt (last occurrence, handles multi-turn)
    idx = text.rfind(prompt_s)
    if idx != -1:
        text = text[idx + len(prompt_s) :].lstrip("\n")

    # Handle Qwen Studio A/B comparison UI — take Response 1 text
    if "Which response do you prefer?" in text:
        m = re.search(r"Response 1\n(.*?)\nI prefer this response", text, re.DOTALL)
        if m:
            text = m.group(1).strip()

    # Strip Qwen Studio "no matching skill" metadata prefix (first line only)
    if text.startswith(("⚠", "⚠️")):  # ⚠ or ⚠️
        nl = text.find("\n")
        if nl != -1:
            text = text[nl + 1 :].lstrip("\n")

    # Strip trailing disclaimer lines
    for prefix in _DISCLAIMER_PREFIXES:
        didx = text.find("\n" + prefix)
        if didx != -1:
            text = text[:didx]
        elif text.startswith(prefix):
            text = ""

    return text.strip()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run_task(
    prompt: str,
    *,
    timeout: int = 120,
    launch_if_closed: bool = True,
) -> QwenResult:
    """
    Send `prompt` to the Qwen desktop app and return its response.

    The bridge navigates to a fresh chat page each call so conversations don't
    bleed into each other. Requires Qwen to be running with CDP port 9223 or
    `launch_if_closed=True`.
    """
    t0 = time.time()

    # 1. Ensure Qwen is running with the CDP debug port.
    #    If it's already running WITHOUT the debug port, Electron's single-instance
    #    lock will prevent a new instance — kill first, then relaunch.
    if not _port_open(CDP_PORT):
        if not launch_if_closed:
            return QwenResult(
                "", False, f"CDP port {CDP_PORT} not open and launch_if_closed=False"
            )
        if not Path(QWEN_EXE).exists():
            return QwenResult("", False, f"Qwen.exe not found: {QWEN_EXE}")

        # Kill any existing Qwen process (single-instance lock workaround)
        subprocess.run(
            ["taskkill", "/IM", "Qwen.exe", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        time.sleep(1)

        subprocess.Popen(
            [
                QWEN_EXE,
                f"--remote-debugging-port={CDP_PORT}",
                "--remote-allow-origins=*",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if not _wait_port(CDP_PORT, timeout=30):
            return QwenResult("", False, "Qwen CDP port did not open within 30s")
        time.sleep(4)  # let the webview finish initial load

    # 2. Connect to the chat.qwen.ai webview via raw CDP WebSocket
    try:
        ws_url = _get_webview_ws()
    except Exception as e:
        return QwenResult(
            "",
            False,
            f"CDP target discovery failed: {e}",
            timing_s=round(time.time() - t0, 1),
        )

    try:
        import websocket as _ws_mod  # noqa: F401
    except ImportError:
        return QwenResult(
            "",
            False,
            "websocket-client not installed: "
            "run `.venv\\Scripts\\pip install websocket-client`",
        )

    try:
        ws = _cdp_session(ws_url)
    except Exception as e:
        return QwenResult(
            "",
            False,
            f"CDP WebSocket connect failed: {e}",
            timing_s=round(time.time() - t0, 1),
        )

    try:
        # 3. Navigate to a fresh chat home page (clears conversation history)
        _send(ws, "Page.navigate", {"url": _HOME_URL})

        # 4. Wait for the textarea to appear (up to 15s)
        deadline_ta = time.time() + 15
        while time.time() < deadline_ta:
            time.sleep(0.8)
            if _js(ws, f"!!document.querySelector('{_TEXTAREA_SEL}')") == "true":
                break
        else:
            return QwenResult(
                "",
                False,
                "Textarea not found after navigation — is Qwen logged in?",
                timing_s=round(time.time() - t0, 1),
            )

        time.sleep(1.0)  # let React finish mounting all input widgets

        # 5a. Enable MCP tools (+ → MCP dropdown click) before each chat
        mcp_ok = _enable_mcp(ws)
        if not mcp_ok:
            # Non-fatal: MCP may still work if tools are default-enabled
            pass
        time.sleep(0.2)

        # 5b. Click the textarea to focus it (use CSS pixel coords; scale=1.0 confirmed working)
        ta_rect_json = _js(
            ws,
            f"JSON.stringify(document.querySelector('{_TEXTAREA_SEL}')?.getBoundingClientRect())",
        )
        try:
            ta_rect = json.loads(ta_rect_json)
            ta_cx = ta_rect["left"] + ta_rect["width"] / 2
            ta_cy = ta_rect["top"] + ta_rect["height"] / 2
        except Exception:
            ta_cx, ta_cy = 600.0, 300.0  # fallback centre of typical layout

        _mouse_click(ws, ta_cx, ta_cy)
        time.sleep(0.2)

        # 6. Clear any pre-existing text (Ctrl+A, Delete)
        _key_event(ws, "a", "KeyA", 65, modifiers=2)  # Ctrl+A
        _key_event(ws, "Delete", "Delete", 46)

        # 7. Type the prompt via native OS input (Input.insertText)
        _send(ws, "Input.insertText", {"text": prompt})
        time.sleep(0.3)

        # Verify the text landed in the textarea
        ta_val = _js(ws, f"document.querySelector('{_TEXTAREA_SEL}')?.value||''")
        if prompt not in ta_val:
            return QwenResult(
                "",
                False,
                f"Prompt not in textarea after typing (got: {ta_val[:50]!r})",
                timing_s=round(time.time() - t0, 1),
            )

        # 8. Submit with Enter key
        _key_event(ws, "Enter", "Enter", 13)
        time.sleep(0.5)

        # 9. Poll .chat-content for a stable AI response.
        #    _extract_response returns "" when the AI hasn't replied yet (only the prompt
        #    + disclaimer are visible), so we keep polling until it's non-empty and stable.
        deadline = time.time() + timeout
        last_text = ""
        stable_count = 0

        while time.time() < deadline:
            time.sleep(2)
            _auto_approve_mcp(ws)  # dismiss any MCP permission dialogs silently
            raw = _chat_text(ws)
            if not raw:
                continue

            cleaned = _extract_response(raw, prompt)
            if not cleaned:
                continue  # response not in DOM yet

            if cleaned == last_text:
                stable_count += 1
                if stable_count >= 2:
                    return QwenResult(
                        text=cleaned,
                        ok=True,
                        timing_s=round(time.time() - t0, 1),
                    )
            else:
                stable_count = 0
                last_text = cleaned

        return QwenResult(
            "",
            False,
            f"No stable response within {timeout}s",
            timing_s=round(time.time() - t0, 1),
        )

    except Exception as e:
        return QwenResult("", False, str(e), timing_s=round(time.time() - t0, 1))
    finally:
        try:
            ws.close()
        except Exception:
            pass


def run_build_task(task: str, timeout: int = 300) -> QwenResult:
    """
    Dispatch an autonomous build/edit task to Qwen.

    Qwen has Filesystem and code-interpreter MCP tools enabled, so it can
    read files, write files, and execute code directly — treat it like AGY.
    """
    full_prompt = (
        "You are an autonomous coding agent with MCP tools available:\n"
        "- Filesystem: read and write any file\n"
        "- code-interpreter: execute Python/shell code\n\n"
        "Project: DeepFieldPro at C:/Users/Elie/DeepFieldPro "
        "(Python 3.12, Flask, SQLite, Windows, venv at .venv/)\n\n"
        "Complete the following task autonomously using your tools. "
        "After finishing, give a brief summary of what you changed and why:\n\n" + task
    )
    return run_task(full_prompt, timeout=timeout)


# ---------------------------------------------------------------------------
# CLI smoke test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys

    # Reconfigure stdout to UTF-8 so Qwen's Unicode responses print correctly
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    prompt = (
        " ".join(sys.argv[1:])
        if len(sys.argv) > 1
        else "Say the word ONLINE and nothing else."
    )
    print(f"[master] -> Qwen: {prompt!r}")
    result = run_task(prompt, timeout=90)
    print(f"[qwen]   ok={result.ok}  time={result.timing_s}s")
    if result.ok:
        print(f"[qwen]   response:\n{result.text}")
    else:
        print(f"[qwen]   error: {result.error}", file=sys.stderr)
    sys.exit(0 if result.ok else 1)
