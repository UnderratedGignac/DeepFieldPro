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
    _fast_path: bool = True,
) -> QwenResult:
    """
    Send `prompt` to the Qwen desktop app and return its response.

    Tries chat_via_fetch() first (fast, ~5s, in-browser SSE).
    Falls back to the DOM-based UI path (slower, ~60s) if the fetch path fails.
    Requires Qwen running with CDP port 9223 or launch_if_closed=True.
    """
    # Fast path: in-browser fetch (bypasses DOM scraping, ~5x faster)
    if _fast_path and _port_open(CDP_PORT):
        try:
            fast = chat_via_fetch(prompt, timeout=min(timeout, 90))
            if fast.ok:
                return fast
            # Non-fatal: fall through to DOM path
        except Exception:
            pass
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


def extract_session(timeout: int = 60) -> dict | None:
    """
    Connect to the running Qwen desktop app (CDP port 9223), extract all
    chat.qwen.ai cookies, and capture bx-ua + bx-umidtoken by enabling
    Network request interception and sending a probe message.

    Returns {cookie, bx_ua, bx_umid} and writes them to .env, or None on failure.
    Qwen.exe must be running with --remote-debugging-port=9223.
    """
    from pathlib import Path
    import re

    ENV_PATH = Path(__file__).parent.parent / ".env"

    if not _port_open(CDP_PORT):
        if not Path(QWEN_EXE).exists():
            print(f"[cdp-extract] Qwen.exe not found at {QWEN_EXE}")
            return None
        print(f"[cdp-extract] launching Qwen with CDP on port {CDP_PORT} …")
        subprocess.run(["taskkill", "/IM", "Qwen.exe", "/F"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(1)
        subprocess.Popen(
            [QWEN_EXE, f"--remote-debugging-port={CDP_PORT}", "--remote-allow-origins=*"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        if not _wait_port(CDP_PORT, timeout=30):
            print("[cdp-extract] CDP port did not open within 30s")
            return None
        time.sleep(4)  # let webview load

    try:
        ws_url = _get_webview_ws()
    except Exception as e:
        print(f"[cdp-extract] CDP target error: {e}")
        return None

    try:
        import websocket as _ws_mod
    except ImportError:
        print("[cdp-extract] websocket-client not installed")
        return None

    ws = _cdp_session(ws_url)
    t0 = time.time()

    try:
        # 1. Get all cookies for the qwen.ai domain
        result = _send(ws, "Network.getAllCookies", wait=10)
        all_cookies = result.get("cookies", [])
        qwen_cookies = [c for c in all_cookies if "qwen.ai" in c.get("domain", "")]
        cookie_str = "; ".join(f"{c['name']}={c['value']}" for c in qwen_cookies)
        print(f"[cdp-extract] got {len(qwen_cookies)} qwen.ai cookies")

        # 2. Enable Network domain + requestWillBeSentExtraInfo to capture request headers
        _send(ws, "Network.enable", wait=5)

        # 3. Send a probe message to trigger the completions API call
        _send(ws, "Page.navigate", {"url": _HOME_URL})
        time.sleep(3)

        # Wait for textarea
        deadline = time.time() + 15
        while time.time() < deadline:
            time.sleep(0.8)
            if _js(ws, f"!!document.querySelector('{_TEXTAREA_SEL}')") == "true":
                break

        _send(ws, "Input.insertText", {"text": "hi"})
        time.sleep(0.3)
        _key_event(ws, "Enter", "Enter", 13)

        # 4. Poll for requestWillBeSentExtraInfo events that contain bx-ua
        bx_ua = ""
        bx_umid = ""
        deadline2 = time.time() + 30
        while time.time() < deadline2 and not bx_ua:
            try:
                ws.settimeout(1.0)
                msg = json.loads(ws.recv())
            except Exception:
                continue
            method = msg.get("method", "")
            if method == "Network.requestWillBeSentExtraInfo":
                hdrs = msg.get("params", {}).get("headers", {})
                # Headers come in lowercase from CDP
                candidate = hdrs.get("bx-ua", "") or hdrs.get("Bx-Ua", "")
                if candidate:
                    bx_ua = candidate
                    bx_umid = hdrs.get("bx-umidtoken", "") or hdrs.get("Bx-Umidtoken", "")
                    print(f"[cdp-extract] captured bx-ua ({len(bx_ua)}b)")
                    break

        # Only accept bx-ua if it looks real (>500b); short values are background requests
        if len(bx_ua) < 500:
            if bx_ua:
                print(f"[cdp-extract] bx-ua too short ({len(bx_ua)}b) — keeping existing .env value")
            else:
                print("[cdp-extract] bx-ua not seen — keeping existing .env value")
            from dotenv import load_dotenv
            load_dotenv()
            import os as _os
            bx_ua = _os.getenv("QWEN_WEB_BX_UA", "")
            bx_umid = _os.getenv("QWEN_WEB_BX_UMID", "")

    finally:
        try:
            ws.close()
        except Exception:
            pass

    if not cookie_str:
        print("[cdp-extract] no cookies found")
        return None

    session = {"cookie": cookie_str, "bx_ua": bx_ua, "bx_umid": bx_umid}

    # Write to .env
    env_text = ENV_PATH.read_text(encoding="utf-8") if ENV_PATH.exists() else ""

    def _set(text, key, value):
        pattern = rf"^{re.escape(key)}=.*$"
        replacement = f"{key}={value}"
        if re.search(pattern, text, flags=re.MULTILINE):
            return re.sub(pattern, replacement, text, flags=re.MULTILINE)
        return text + f"\n{replacement}"

    env_text = _set(env_text, "QWEN_WEB_COOKIE", cookie_str)
    if bx_ua and len(bx_ua) > 500:
        env_text = _set(env_text, "QWEN_WEB_BX_UA", bx_ua)
    if bx_umid and len(bx_umid) > 20:
        env_text = _set(env_text, "QWEN_WEB_BX_UMID", bx_umid)

    ENV_PATH.write_text(env_text, encoding="utf-8")

    # Also update current process env so callers see it immediately
    import os
    os.environ["QWEN_WEB_COOKIE"] = cookie_str
    if bx_ua and len(bx_ua) > 500:
        os.environ["QWEN_WEB_BX_UA"] = bx_ua
    if bx_umid and len(bx_umid) > 20:
        os.environ["QWEN_WEB_BX_UMID"] = bx_umid

    print(f"[cdp-extract] .env updated — cookie={len(cookie_str)}b  time={round(time.time()-t0,1)}s")
    return session


def chat_via_fetch(
    prompt: str,
    *,
    timeout: int = 90,
    model: str = "qwen3.7-max",
    chat_id: str | None = None,
) -> QwenResult:
    """
    Send a prompt to Qwen by running fetch() INSIDE the Qwen app's webview via CDP.

    Same-origin: the SDK's TianMaDun patcher auto-injects bx-ua/cookies — no bot
    detection. JWT is read from localStorage. Uses an existing chat_id (avoids the
    "chat is not exist" error from random UUIDs). Response streams via SSE; terminates
    when delta.status === "finished" or the reader closes.

    Qwen.exe must be running with --remote-debugging-port=9223.
    """
    t0 = time.time()

    if not _port_open(CDP_PORT):
        if not Path(QWEN_EXE).exists():
            return QwenResult("", False, f"Qwen.exe not found: {QWEN_EXE}")
        subprocess.run(["taskkill", "/IM", "Qwen.exe", "/F"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(1)
        subprocess.Popen(
            [QWEN_EXE, f"--remote-debugging-port={CDP_PORT}", "--remote-allow-origins=*"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        if not _wait_port(CDP_PORT, timeout=30):
            return QwenResult("", False, "CDP port did not open within 30s")
        time.sleep(4)

    try:
        ws_url = _get_webview_ws()
    except Exception as e:
        return QwenResult("", False, f"CDP target error: {e}",
                          timing_s=round(time.time() - t0, 1))

    try:
        import websocket as _ws_mod  # noqa
    except ImportError:
        return QwenResult("", False, "websocket-client not installed")

    ws = _cdp_session(ws_url)

    # Embed prompt + model + optional pinned chat_id as JSON literals
    prompt_json = json.dumps(prompt)
    model_json  = json.dumps(model)
    pinned_json = json.dumps(chat_id)  # null → JS null → will fetch latest

    js_code = f"""
(async () => {{
  // 1. Get JWT from localStorage (valid ~30 days)
  const jwt = localStorage.getItem('token') || '';
  if (!jwt) return 'ERROR:no_jwt';

  // 2. Resolve chat_id — use pinned value if provided, else fetch the latest
  let chatId = {pinned_json};
  if (!chatId) {{
    try {{
      const r = await fetch('/api/v2/chats/?page=1&page_size=3');
      const d = await r.json();
      chatId = (d.data || [])[0]?.id;
    }} catch(e) {{ return 'ERROR:no_chat_id:' + e.message; }}
    if (!chatId) return 'ERROR:no_chat_id:empty';
  }}

  // 3. Build the completions body (exact format from DevTools capture 2026-06-19)
  const ts = Math.floor(Date.now() / 1000);
  const msgFid = crypto.randomUUID();
  const MODEL = {model_json};
  const PROMPT = {prompt_json};

  const body = JSON.stringify({{
    stream: true, incremental_output: true, version: '2.1',
    chat_id: chatId, chat_mode: 'normal', model: MODEL,
    parent_id: null, timestamp: ts,
    messages: [{{
      fid: msgFid, parentId: null, childrenIds: [],
      role: 'user', content: PROMPT,
      user_action: 'chat', files: [], timestamp: ts,
      models: [MODEL], chat_type: 't2t',
      feature_config: {{
        thinking_enabled: false, output_schema: 'phase',
        research_mode: 'normal', auto_thinking: false,
        thinking_mode: 'Fast', auto_search: false
      }},
      extra: {{ meta: {{ subChatType: 't2t' }} }},
      sub_chat_type: 't2t'
    }}]
  }});

  // 4. POST — SDK patches window.fetch so bx-ua is injected automatically
  let resp;
  try {{
    resp = await fetch('/api/v2/chat/completions?chat_id=' + chatId, {{
      method: 'POST',
      headers: {{
        'content-type': 'application/json',
        'Authorization': 'Bearer ' + jwt,
        'source': 'desktop',
        'version': '0.2.66'
      }},
      body: body
    }});
  }} catch(e) {{ return 'FETCH_ERR:' + e.message; }}

  if (!resp.ok) {{
    return 'HTTP_ERR:' + resp.status + ':' + (await resp.text()).slice(0, 300);
  }}

  // 5. Read SSE stream
  //    Format: data: {{"choices":[{{"delta":{{"content":"...","status":"typing"|"finished",...}}}}],...}}
  //    Termination: delta.status === "finished"  OR  reader.done
  const reader = resp.body.getReader();
  const dec = new TextDecoder();
  let out = '';

  while (true) {{
    const {{done, value}} = await reader.read();
    if (done) break;
    for (const line of dec.decode(value).split('\\n')) {{
      if (!line.startsWith('data:')) continue;
      const raw = line.slice(5).trim();
      if (raw === '[DONE]') return out;
      try {{
        const d = JSON.parse(raw);
        const delta = d?.choices?.[0]?.delta;
        if (!delta) continue;
        if (delta.content) out += delta.content;
        if (delta.status === 'finished') return out;
      }} catch(e) {{}}
    }}
  }}
  return out || 'EMPTY_RESPONSE';
}})()
"""

    try:
        result = _send(
            ws,
            "Runtime.evaluate",
            {
                "expression": js_code,
                "returnByValue": True,
                "awaitPromise": True,
            },
            wait=timeout,
        )
    except Exception as e:
        try:
            ws.close()
        except Exception:
            pass
        return QwenResult("", False, f"CDP eval error: {e}",
                          timing_s=round(time.time() - t0, 1))

    try:
        ws.close()
    except Exception:
        pass

    exc = result.get("exceptionDetails")
    if exc:
        return QwenResult("", False, f"JS exception: {exc}",
                          timing_s=round(time.time() - t0, 1))

    val = result.get("result", {}).get("value") or ""
    val = str(val).strip()

    if val.startswith(("ERROR:", "FETCH_ERR:", "HTTP_ERR:")):
        return QwenResult("", False, val, timing_s=round(time.time() - t0, 1))

    if not val or val == "EMPTY_RESPONSE":
        return QwenResult("", False, "Empty response from model",
                          timing_s=round(time.time() - t0, 1))

    # Strip "No matching skill" preamble the server prepends for skill-enabled chats
    text = val
    if text.startswith(("⚠", "⚠️")):
        nl = text.find("\n\n")
        if nl != -1:
            text = text[nl + 2:]

    return QwenResult(text=text.strip(), ok=True, timing_s=round(time.time() - t0, 1))


def new_chat() -> str:
    """
    Create a new chat in the Qwen desktop app and return its chat_id.
    Tries the REST API first; falls back to clicking the New Chat UI button.
    Raises RuntimeError on failure.
    """
    if not _port_open(CDP_PORT):
        raise RuntimeError(f"Qwen CDP port {CDP_PORT} not open — is Qwen running?")

    ws_url = _get_webview_ws()
    ws = _cdp_session(ws_url)

    js = """
(async () => {
  const jwt = localStorage.getItem('token') || '';
  if (!jwt) return 'ERROR:no_jwt';

  // Try POST to the chats API (several body variants)
  const variants = [
    {chat_type: 't2t'},
    {name: 'ElieAtch', chat_type: 't2t'},
    {chat_mode: 'normal'},
    {},
  ];
  for (const body of variants) {
    try {
      const resp = await fetch('/api/v2/chats/', {
        method: 'POST',
        headers: {
          'content-type': 'application/json',
          'Authorization': 'Bearer ' + jwt,
          'source': 'desktop',
          'version': '0.2.66'
        },
        body: JSON.stringify(body)
      });
      const txt = await resp.text();
      if (!resp.ok) continue;
      const d = JSON.parse(txt);
      const id = d?.data?.id || d?.id;
      if (id) return id;
    } catch(e) {}
  }

  // Fallback: click the New Chat button in the sidebar
  const allEls = [...document.querySelectorAll('button, [role="button"], a, div, span')];
  const btn = allEls.find(el => {
    if (!el.offsetParent) return false;   // skip hidden
    const txt = (el.innerText || el.textContent || '').trim();
    return /^(new\\s*chat|新对话|新建对话|新建)$/i.test(txt);
  });
  if (btn) {
    btn.click();
    await new Promise(r => setTimeout(r, 1800));
    const r2 = await fetch('/api/v2/chats/?page=1&page_size=1');
    const d2 = await r2.json();
    const id2 = (d2.data || [])[0]?.id;
    if (id2) return id2;
  }

  return 'ERROR:could_not_create';
})()
"""
    try:
        result = _send(ws, "Runtime.evaluate",
                       {"expression": js, "returnByValue": True, "awaitPromise": True},
                       wait=20)
    finally:
        try: ws.close()
        except Exception: pass

    val = result.get("result", {}).get("value") or ""
    val = str(val).strip()
    if val.startswith("ERROR:") or not val:
        raise RuntimeError(f"new_chat failed: {val}")
    return val


def chat_via_fetch_stream(
    prompt: str,
    *,
    timeout: int = 90,
    model: str = "qwen3.7-max",
    chat_id: str | None = None,
):
    """
    Stream a Qwen response via CDP polling. Yields str text chunks as they arrive.
    Keeps the CDP WebSocket open and polls window._ea_buf every ~80 ms.
    Raises RuntimeError on connection failure or stream error.
    """
    if not _port_open(CDP_PORT):
        raise RuntimeError(f"CDP port {CDP_PORT} not open — is Qwen running?")

    ws_url = _get_webview_ws()
    try:
        import websocket as _ws_mod  # noqa
    except ImportError:
        raise RuntimeError("websocket-client not installed")

    ws = _cdp_session(ws_url)

    prompt_json = json.dumps(prompt)
    model_json  = json.dumps(model)
    pinned_json = json.dumps(chat_id)

    start_js = f"""
(function() {{
  window._ea_buf = [];
  window._ea_done = false;
  window._ea_err  = '';

  (async () => {{
    try {{
      const jwt = localStorage.getItem('token') || '';
      if (!jwt) {{ window._ea_err = 'no_jwt'; window._ea_done = true; return; }}

      let chatId = {pinned_json};
      if (!chatId) {{
        const r = await fetch('/api/v2/chats/?page=1&page_size=1');
        const d = await r.json();
        chatId = (d.data || [])[0]?.id;
      }}
      if (!chatId) {{ window._ea_err = 'no_chat_id'; window._ea_done = true; return; }}

      const ts      = Math.floor(Date.now() / 1000);
      const msgFid  = crypto.randomUUID();
      const MODEL   = {model_json};
      const PROMPT  = {prompt_json};

      const body = JSON.stringify({{
        stream: true, incremental_output: true, version: '2.1',
        chat_id: chatId, chat_mode: 'normal', model: MODEL,
        parent_id: null, timestamp: ts,
        messages: [{{
          fid: msgFid, parentId: null, childrenIds: [],
          role: 'user', content: PROMPT,
          user_action: 'chat', files: [], timestamp: ts,
          models: [MODEL], chat_type: 't2t',
          feature_config: {{
            thinking_enabled: false, output_schema: 'phase',
            research_mode: 'normal', auto_thinking: false,
            thinking_mode: 'Fast', auto_search: false
          }},
          extra: {{ meta: {{ subChatType: 't2t' }} }},
          sub_chat_type: 't2t'
        }}]
      }});

      const resp = await fetch('/api/v2/chat/completions?chat_id=' + chatId, {{
        method: 'POST',
        headers: {{
          'content-type': 'application/json',
          'Authorization': 'Bearer ' + jwt,
          'source': 'desktop',
          'version': '0.2.66'
        }},
        body: body
      }});

      if (!resp.ok) {{
        window._ea_err = 'HTTP_' + resp.status + ':' + (await resp.text()).slice(0, 200);
        window._ea_done = true;
        return;
      }}

      const reader = resp.body.getReader();
      const dec    = new TextDecoder();
      while (true) {{
        const {{done, value}} = await reader.read();
        if (done) {{ window._ea_done = true; return; }}
        for (const line of dec.decode(value).split('\\n')) {{
          if (!line.startsWith('data:')) continue;
          const raw = line.slice(5).trim();
          if (raw === '[DONE]') {{ window._ea_done = true; return; }}
          try {{
            const d     = JSON.parse(raw);
            const delta = d?.choices?.[0]?.delta;
            if (delta?.content)          window._ea_buf.push(delta.content);
            if (delta?.status === 'finished') {{ window._ea_done = true; return; }}
          }} catch(e) {{}}
        }}
      }}
    }} catch(e) {{
      window._ea_err  = e.message;
      window._ea_done = true;
    }}
  }})();

  return 'started';
}})()
""".strip()

    poll_js = (
        'JSON.stringify({'
        'c:window._ea_buf.splice(0),'
        'd:window._ea_done,'
        'e:window._ea_err})'
    )

    try:
        r = _send(ws, "Runtime.evaluate", {
            "expression": start_js,
            "returnByValue": True,
            "awaitPromise": False,
        }, wait=10)
        v = str(r.get("result", {}).get("value", ""))
        if v != "started":
            raise RuntimeError(f"Stream start: {v!r}")

        deadline = time.time() + timeout
        while time.time() < deadline:
            pr  = _send(ws, "Runtime.evaluate",
                        {"expression": poll_js, "returnByValue": True}, wait=5)
            raw = pr.get("result", {}).get("value") or '{"c":[],"d":false,"e":""}'
            try:
                data = json.loads(raw)
            except Exception:
                data = {"c": [], "d": False, "e": "poll_parse_err"}

            for chunk in data.get("c", []):
                if chunk:
                    yield chunk

            if data.get("d"):
                if data.get("e"):
                    raise RuntimeError(data["e"])
                return

            time.sleep(0.08)

        raise RuntimeError(f"Stream timeout after {timeout}s")

    finally:
        try: ws.close()
        except Exception: pass


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

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    if "--extract-session" in sys.argv:
        print("[bridge] extracting session from running Qwen app …")
        sess = extract_session(timeout=60)
        if sess:
            print(f"[bridge] cookie={len(sess['cookie'])}b  bx_ua={len(sess['bx_ua'])}b")
            print("[bridge] .env updated — ready to use")
            sys.exit(0)
        else:
            print("[bridge] extraction failed", file=sys.stderr)
            sys.exit(1)

    prompt = (
        " ".join(a for a in sys.argv[1:] if not a.startswith("--"))
        or "Say the word ONLINE and nothing else."
    )
    print(f"[master] -> Qwen: {prompt!r}")
    result = run_task(prompt, timeout=90)
    print(f"[qwen]   ok={result.ok}  time={result.timing_s}s")
    if result.ok:
        print(f"[qwen]   response:\n{result.text}")
    else:
        print(f"[qwen]   error: {result.error}", file=sys.stderr)
    sys.exit(0 if result.ok else 1)
