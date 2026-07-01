"""
Mistral chat web bridge via Chrome DevTools Protocol (CDP).

# NOTE: Requires Chrome open at chat.mistral.ai on CDP port 9230 (logged in).
# Env vars: MISTRAL_CHAT_CDP_PORT (default 9230)

Architecture:
    Primary path — in-page fetch() to Mistral's internal conversation API:
        1. POST /api/conversations  to create a new conversation.
        2. POST /api/conversations/{id}/chat  to send the user message.
        3. Read the response body (plain JSON or chunked).
        All requests run inside the page via CDP Runtime.evaluate so they carry
        the browser's session cookies and bypass bot detection.

    Fallback path — DOM injection (same technique as gemini_cdp.py):
        If the API calls fail (endpoint changed, auth structure changed, etc.),
        the bridge falls back to finding the textarea/contenteditable input,
        injecting the prompt with execCommand, clicking send, and polling the
        DOM for the assistant reply.

    Chrome must be launched with:
        chrome.exe --remote-debugging-port=9230 --remote-allow-origins=*

Usage:
    from tools.llm_bridges.mistral_cdp import MistralCDPBridge

    bridge = MistralCDPBridge()
    if bridge.is_available():
        result = bridge.simple("Explain the Dixon-Coles football model.")
        print(result.text)

Notes:
    - The user must be logged into chat.mistral.ai in Chrome on port 9230.
    - Mistral's internal API is not publicly documented; selectors and endpoints
      may change between UI deployments. Check the Network tab and update the
      constants below if the bridge stops working.
    - For production use with an API key, prefer tools/llm_bridges/mistral_api.py.
"""

from __future__ import annotations

import json
import os
import socket
import time
import urllib.request
from typing import Iterator

from tools.llm_bridges.base import LLMBridge, LLMResult

_DEFAULT_PORT = 9230

# DOM selectors for the Mistral chat input
_INPUT_SELECTORS = [
    "textarea[placeholder]",
    "div[contenteditable='true']",
    "[data-testid='chat-input']",
    "textarea",
]

# Response message containers
_RESPONSE_SELECTORS = [
    "[class*='message'][class*='assistant']",
    "[class*='response']",
    "[class*='bot-message']",
    "[class*='assistant-message']",
    "[class*='ai-message']",
]

# Send button selectors
_SEND_BUTTON_SELECTORS = [
    "button[aria-label*='Send']",
    "button[aria-label*='send']",
    "button[type='submit']",
    "[data-testid='send-button']",
    "button.send-button",
]


def _cdp_port() -> int:
    return int(os.environ.get("MISTRAL_CHAT_CDP_PORT", _DEFAULT_PORT))


# ---------------------------------------------------------------------------
# Low-level CDP helpers
# ---------------------------------------------------------------------------


def _port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        try:
            s.connect(("localhost", port))
            return True
        except OSError:
            return False


def _get_mistral_tab_ws(port: int) -> str:
    """Return the WebSocket debugger URL for the chat.mistral.ai tab."""
    raw = urllib.request.urlopen(f"http://localhost:{port}/json", timeout=5).read()
    targets = json.loads(raw)
    for t in targets:
        url = t.get("url", "")
        if "chat.mistral.ai" in url and t.get("type") == "page":
            return t["webSocketDebuggerUrl"]
    for t in targets:
        if "mistral.ai" in t.get("url", ""):
            return t["webSocketDebuggerUrl"]
    available = [t.get("url", "") for t in targets]
    raise RuntimeError(
        f"No chat.mistral.ai tab found in CDP targets on port {port}. "
        f"Open tabs: {available}"
    )


def _cdp_session(ws_url: str, port: int):
    import websocket  # websocket-client

    return websocket.create_connection(
        ws_url, timeout=15, header={"Origin": f"http://localhost:{port}"}
    )


def _send(ws, method: str, params: dict | None = None, wait: float = 15) -> dict:
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
        except Exception:
            pass
    return {}


def _js_sync(ws, expression: str, wait: float = 10) -> str:
    """Evaluate synchronous JS and return a string value."""
    result = _send(
        ws,
        "Runtime.evaluate",
        {"expression": expression, "returnByValue": True, "awaitPromise": False},
        wait=wait,
    )
    val = result.get("result", {}).get("value")
    if val is None:
        return ""
    return str(val)


def _js_async(ws, expression: str, wait: float = 30) -> tuple[str, str | None]:
    """Evaluate an async JS expression (awaitPromise=True).
    Returns (value_str, exception_text_or_None)."""
    result = _send(
        ws,
        "Runtime.evaluate",
        {"expression": expression, "returnByValue": True, "awaitPromise": True},
        wait=wait,
    )
    exc = result.get("exceptionDetails")
    exc_text = str(exc) if exc else None
    val = result.get("result", {}).get("value")
    return (str(val) if val is not None else ""), exc_text


# ---------------------------------------------------------------------------
# Token extraction
# ---------------------------------------------------------------------------

_TOKEN_JS = """
(async () => {
  let token = null;

  // 1. Scan localStorage for JWT tokens (start with 'ey')
  try {
    for (const key of Object.keys(localStorage)) {
      const val = localStorage.getItem(key);
      if (val && val.startsWith('ey') && val.length > 50) {
        token = val;
        break;
      }
    }
  } catch(e) {}

  // 2. Check well-known cookie names
  if (!token) {
    try {
      const cookies = document.cookie.split('; ').reduce((acc, c) => {
        const [k, ...v] = c.split('='); acc[k] = v.join('='); return acc;
      }, {});
      token = cookies['access_token'] || cookies['session'] || cookies['cf_clearance'] || null;
    } catch(e) {}
  }

  // 3. Try fetching the session endpoint (same-origin, carries cookies)
  if (!token) {
    try {
      const r = await fetch('/api/auth/session', {credentials: 'include'});
      if (r.ok) {
        const d = await r.json();
        token = d?.accessToken || d?.token || d?.access_token || null;
      }
    } catch(e) {}
  }

  // 4. Try /api/auth/user
  if (!token) {
    try {
      const r = await fetch('/api/auth/user', {credentials: 'include'});
      if (r.ok) {
        const d = await r.json();
        token = d?.accessToken || d?.token || null;
      }
    } catch(e) {}
  }

  return token || 'ERROR:no_token';
})()
"""


def _get_token(ws) -> str | None:
    val, exc = _js_async(ws, _TOKEN_JS, wait=20)
    if exc or not val or val.startswith("ERROR:"):
        return None
    if len(val) > 20:
        return val.strip()
    return None


# ---------------------------------------------------------------------------
# Primary path: internal API via in-page fetch
# ---------------------------------------------------------------------------

_API_CHAT_JS_TPL = """
(async () => {{
  const MODEL = {model_json};
  const PROMPT = {prompt_json};

  // Step 1: Create a new conversation
  let convId = null;
  try {{
    const cr = await fetch('/api/conversations', {{
      method: 'POST',
      credentials: 'include',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{model: MODEL, messages: []}})
    }});
    if (cr.ok) {{
      const cd = await cr.json();
      convId = cd.id || cd.conversationId || null;
    }}
  }} catch(e) {{}}

  // Step 2: Send message (per-conversation endpoint)
  if (convId) {{
    try {{
      const mr = await fetch('/api/conversations/' + convId + '/chat', {{
        method: 'POST',
        credentials: 'include',
        headers: {{'Content-Type': 'application/json'}},
        body: JSON.stringify({{
          message: {{content: PROMPT, role: 'user'}},
          model: MODEL
        }})
      }});
      if (mr.ok) {{
        const md = await mr.json();
        const text = md?.message?.content
                  || md?.content
                  || md?.text
                  || md?.choices?.[0]?.message?.content
                  || null;
        if (text) {{ window._ea_mistral_result = text; return text; }}
      }}
    }} catch(e) {{}}
  }}

  // Step 3: Fallback — OpenAI-compat endpoint
  try {{
    const or_ = await fetch('/api/v1/chat/completions', {{
      method: 'POST',
      credentials: 'include',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{
        model: MODEL,
        messages: [{{role: 'user', content: PROMPT}}],
        stream: false
      }})
    }});
    if (or_.ok) {{
      const od = await or_.json();
      const text = od?.choices?.[0]?.message?.content || null;
      if (text) {{ window._ea_mistral_result = text; return text; }}
    }}
  }} catch(e) {{}}

  return 'API_FAILED';
}})()
"""

# Background streaming variant — writes into window._ea_mistral_buf
_API_STREAM_START_JS_TPL = """
(function() {{
  window._ea_mistral_buf  = [];
  window._ea_mistral_done = false;
  window._ea_mistral_err  = '';

  const MODEL  = {model_json};
  const PROMPT = {prompt_json};

  (async () => {{
    try {{
      // Attempt per-conversation streaming
      let convId = null;
      const cr = await fetch('/api/conversations', {{
        method: 'POST', credentials: 'include',
        headers: {{'Content-Type': 'application/json'}},
        body: JSON.stringify({{model: MODEL, messages: []}})
      }});
      if (cr.ok) {{
        const cd = await cr.json();
        convId = cd.id || cd.conversationId || null;
      }}

      let resp = null;
      if (convId) {{
        resp = await fetch('/api/conversations/' + convId + '/chat', {{
          method: 'POST', credentials: 'include',
          headers: {{'Content-Type': 'application/json'}},
          body: JSON.stringify({{
            message: {{content: PROMPT, role: 'user'}},
            model: MODEL, stream: true
          }})
        }});
      }}

      // Fallback to OAI-compat streaming
      if (!resp || !resp.ok) {{
        resp = await fetch('/api/v1/chat/completions', {{
          method: 'POST', credentials: 'include',
          headers: {{'Content-Type': 'application/json', 'Accept': 'text/event-stream'}},
          body: JSON.stringify({{
            model: MODEL,
            messages: [{{role: 'user', content: PROMPT}}],
            stream: true
          }})
        }});
      }}

      if (!resp || !resp.ok) {{
        window._ea_mistral_err  = 'HTTP_ERR:' + (resp ? resp.status : 'no_resp');
        window._ea_mistral_done = true;
        return;
      }}

      const reader  = resp.body.getReader();
      const decoder = new TextDecoder();
      let prev = '';

      while (true) {{
        const {{done, value}} = await reader.read();
        if (done) {{ window._ea_mistral_done = true; return; }}
        const lines = decoder.decode(value).split('\\n');
        for (const line of lines) {{
          if (!line.startsWith('data: ')) continue;
          const raw = line.slice(6).trim();
          if (raw === '[DONE]') {{ window._ea_mistral_done = true; return; }}
          try {{
            const d = JSON.parse(raw);
            const delta = d?.choices?.[0]?.delta?.content
                       || d?.message?.content
                       || null;
            if (delta) {{
              window._ea_mistral_buf.push(delta);
              prev += delta;
            }}
          }} catch(e) {{}}
        }}
      }}
    }} catch(e) {{
      window._ea_mistral_err  = e.message;
      window._ea_mistral_done = true;
    }}
  }})();

  return 'started';
}})()
"""

_STREAM_POLL_JS = (
    'JSON.stringify({'
    'c:window._ea_mistral_buf.splice(0),'
    'd:window._ea_mistral_done,'
    'e:window._ea_mistral_err})'
)


# ---------------------------------------------------------------------------
# Fallback path: DOM injection (mirrors gemini_cdp.py)
# ---------------------------------------------------------------------------

_SET_INPUT_JS_TPL = """
(function() {{
  const selectors = {selectors_json};
  let el = null;
  for (const sel of selectors) {{
    el = document.querySelector(sel);
    if (el) break;
  }}
  if (!el) return 'NO_INPUT';

  el.focus();

  if (el.tagName === 'TEXTAREA') {{
    el.value = '';
    el.dispatchEvent(new Event('input', {{bubbles: true}}));
    if (document.execCommand) {{
      document.execCommand('selectAll', false, null);
      document.execCommand('insertText', false, {prompt_json});
    }} else {{
      el.value = {prompt_json};
      el.dispatchEvent(new Event('input', {{bubbles: true}}));
      el.dispatchEvent(new Event('change', {{bubbles: true}}));
    }}
  }} else {{
    el.innerHTML = '';
    if (document.execCommand) {{
      document.execCommand('selectAll', false, null);
      document.execCommand('delete', false, null);
      document.execCommand('insertText', false, {prompt_json});
    }} else {{
      el.textContent = {prompt_json};
      el.dispatchEvent(new InputEvent('input', {{
        bubbles: true, cancelable: true,
        inputType: 'insertText', data: {prompt_json}
      }}));
    }}
  }}

  return 'ok:' + (el.textContent || el.value || '').length;
}})()
"""

_CLICK_SEND_JS = """
(function() {
  const selectors = """ + json.dumps(_SEND_BUTTON_SELECTORS) + """;
  for (const sel of selectors) {
    const btn = document.querySelector(sel);
    if (btn) {
      btn.dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true, view: window}));
      return 'clicked:' + sel;
    }
  }
  // Heuristic: any visible button with send/submit semantics
  for (const btn of document.querySelectorAll('button')) {
    const r = btn.getBoundingClientRect();
    if (r.width === 0 || r.height === 0) continue;
    const aria  = (btn.getAttribute('aria-label') || '').toLowerCase();
    const title = (btn.getAttribute('title') || '').toLowerCase();
    const text  = (btn.innerText || '').trim().toLowerCase();
    if (aria.includes('send') || title.includes('send') || text === 'send') {
      btn.dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true, view: window}));
      return 'clicked:fallback';
    }
  }
  // Last resort: Enter on active element
  const active = document.activeElement;
  if (active) {
    active.dispatchEvent(new KeyboardEvent('keydown', {
      key: 'Enter', code: 'Enter', keyCode: 13, which: 13,
      bubbles: true, cancelable: true
    }));
    return 'enter_key';
  }
  return 'NO_SEND_BUTTON';
})()
"""

_COUNT_RESPONSES_JS = """
(function() {
  let max = 0;
  const selectors = """ + json.dumps(_RESPONSE_SELECTORS) + """;
  for (const sel of selectors) {
    const c = document.querySelectorAll(sel).length;
    if (c > max) max = c;
  }
  return max;
})()
"""

_READ_RESPONSE_JS = """
(function() {
  const selectors = """ + json.dumps(_RESPONSE_SELECTORS) + """;
  let lastEl = null;
  for (const sel of selectors) {
    const els = document.querySelectorAll(sel);
    if (els.length > 0) { lastEl = els[els.length - 1]; break; }
  }
  if (!lastEl) return '';
  return (lastEl.innerText || lastEl.textContent || '').trim();
})()
"""

_IS_GENERATING_JS = """
(function() {
  const indicators = [
    '[class*="loading"]',
    '[class*="thinking"]',
    '[class*="spinner"]',
    '[class*="generating"]',
    '[aria-label*="thinking"]',
    '[aria-label*="generating"]',
  ];
  for (const sel of indicators) {
    const el = document.querySelector(sel);
    if (el) {
      const r = el.getBoundingClientRect();
      if (r.width > 0 && r.height > 0) return 'true';
    }
  }
  return 'false';
})()
"""


def _dom_send_and_wait(ws, prompt: str, timeout: int = 120) -> tuple[bool, str]:
    """DOM-injection fallback: inject prompt, click send, poll for response."""
    set_js = _SET_INPUT_JS_TPL.format(
        selectors_json=json.dumps(_INPUT_SELECTORS),
        prompt_json=json.dumps(prompt),
    )
    set_result = _js_sync(ws, set_js, wait=10)
    if not set_result.startswith("ok:"):
        return False, f"DOM: could not set input text: {set_result}"

    prev_count_str = _js_sync(ws, _COUNT_RESPONSES_JS, wait=5)
    prev_count = int(prev_count_str) if prev_count_str.isdigit() else 0

    time.sleep(0.5)
    _js_sync(ws, _CLICK_SEND_JS, wait=5)
    time.sleep(1.0)

    deadline = time.time() + timeout
    last_text = ""
    stable_count = 0
    new_response_seen = False

    while time.time() < deadline:
        time.sleep(1.5)
        cur_count_str = _js_sync(ws, _COUNT_RESPONSES_JS, wait=5)
        cur_count = int(cur_count_str) if cur_count_str.isdigit() else 0
        if cur_count > prev_count:
            new_response_seen = True
        if not new_response_seen:
            continue

        text = _js_sync(ws, _READ_RESPONSE_JS, wait=5).strip()
        if not text:
            continue

        generating = _js_sync(ws, _IS_GENERATING_JS, wait=3) == "true"
        if text == last_text and not generating:
            stable_count += 1
            if stable_count >= 2:
                return True, text
        else:
            stable_count = 0
            last_text = text

    if last_text:
        return True, last_text
    return False, f"DOM: no response within {timeout}s"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _messages_to_prompt(messages: list[dict]) -> str:
    if not messages:
        return ""
    if len(messages) == 1 and messages[0].get("role") == "user":
        return str(messages[0].get("content", ""))
    parts: list[str] = []
    for m in messages:
        role = m.get("role", "user")
        content = str(m.get("content", ""))
        if role == "system":
            parts.append(f"[System]: {content}")
        elif role == "assistant":
            parts.append(f"[Assistant]: {content}")
        else:
            parts.append(content)
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Public bridge class
# ---------------------------------------------------------------------------


class MistralCDPBridge(LLMBridge):
    """
    Mistral chat web bridge via Chrome DevTools Protocol.

    Drives a Chrome instance that has chat.mistral.ai open (must be logged in).
    Primary path: fires Mistral's internal conversation API via in-page fetch()
    (same-origin, carries cookies, bypasses bot detection).
    Fallback path: DOM injection (textarea + send button) polled for response.

    Chrome launch command:
        chrome.exe --remote-debugging-port=9230 --remote-allow-origins=*
    """

    provider = "mistral-cdp"
    default_model = "mistral-large-latest"
    models = [
        "mistral-large-latest",
        "mistral-small-latest",
        "open-mistral-7b",
        "codestral-latest",
    ]

    def is_available(self) -> bool:
        """True if Chrome is listening on the CDP port and chat.mistral.ai tab exists."""
        port = _cdp_port()
        if not _port_open(port):
            return False
        try:
            _get_mistral_tab_ws(port)
            return True
        except Exception:
            return False

    def chat(self, messages: list[dict], model: str = "") -> LLMResult:
        model = model or self.default_model
        prompt = _messages_to_prompt(messages)
        t0 = time.time()
        port = _cdp_port()

        if not _port_open(port):
            return LLMResult(
                ok=False, text="",
                error=(
                    f"Chrome CDP port {port} not open — start Chrome with "
                    f"--remote-debugging-port={port}"
                ),
                provider=self.provider, model=model,
            )

        try:
            ws_url = _get_mistral_tab_ws(port)
        except Exception as e:
            return LLMResult(
                ok=False, text="", error=str(e),
                timing_s=round(time.time() - t0, 2),
                provider=self.provider, model=model,
            )

        try:
            import websocket  # noqa: F401
        except ImportError:
            return LLMResult(
                ok=False, text="",
                error="websocket-client not installed: pip install websocket-client",
                provider=self.provider, model=model,
            )

        ws = None
        try:
            ws = _cdp_session(ws_url, port)

            # Primary path: internal API
            api_js = _API_CHAT_JS_TPL.format(
                model_json=json.dumps(model),
                prompt_json=json.dumps(prompt),
            )
            val, exc = _js_async(ws, api_js, wait=90)

            if not exc and val and val not in ("API_FAILED", "None", ""):
                return LLMResult(
                    ok=True, text=val.strip(),
                    timing_s=round(time.time() - t0, 2),
                    provider=self.provider, model=model,
                )

            # Fallback: DOM injection
            ok, text = _dom_send_and_wait(ws, prompt)
            return LLMResult(
                ok=ok,
                text=text if ok else "",
                error="" if ok else text,
                timing_s=round(time.time() - t0, 2),
                provider=self.provider, model=model,
            )

        except Exception as e:
            return LLMResult(
                ok=False, text="", error=str(e),
                timing_s=round(time.time() - t0, 2),
                provider=self.provider, model=model,
            )
        finally:
            if ws:
                try:
                    ws.close()
                except Exception:
                    pass

    def stream(self, messages: list[dict], model: str = "") -> Iterator[str]:
        """
        Stream Mistral response chunks via CDP polling.
        Primary: async SSE via in-page fetch writing to window._ea_mistral_buf.
        Fallback: DOM polling (incremental text diffs).
        Yields str chunks. Raises RuntimeError on hard failure.
        """
        model = model or self.default_model
        prompt = _messages_to_prompt(messages)
        port = _cdp_port()

        if not _port_open(port):
            raise RuntimeError(
                f"Chrome CDP port {port} not open — start Chrome with "
                f"--remote-debugging-port={port}"
            )

        try:
            ws_url = _get_mistral_tab_ws(port)
        except Exception as e:
            raise RuntimeError(f"CDP tab discovery failed: {e}") from e

        ws = _cdp_session(ws_url, port)
        try:
            start_js = _API_STREAM_START_JS_TPL.format(
                model_json=json.dumps(model),
                prompt_json=json.dumps(prompt),
            )
            r = _send(
                ws,
                "Runtime.evaluate",
                {"expression": start_js, "returnByValue": True, "awaitPromise": False},
                wait=10,
            )
            started = str(r.get("result", {}).get("value", ""))

            if started == "started":
                # API streaming path: poll window._ea_mistral_buf
                deadline = time.time() + 180
                while time.time() < deadline:
                    pr = _send(
                        ws,
                        "Runtime.evaluate",
                        {"expression": _STREAM_POLL_JS, "returnByValue": True},
                        wait=5,
                    )
                    raw = pr.get("result", {}).get("value") or '{"c":[],"d":false,"e":""}'
                    try:
                        data = json.loads(raw)
                    except Exception:
                        data = {"c": [], "d": False, "e": "poll_parse_err"}

                    for chunk in data.get("c", []):
                        if chunk:
                            yield chunk

                    if data.get("d"):
                        err = data.get("e", "")
                        if err:
                            # Don't raise — fall through to DOM fallback if nothing yielded
                            break
                        return

                    time.sleep(0.1)

            # DOM streaming fallback: inject and poll incremental text diffs
            set_js = _SET_INPUT_JS_TPL.format(
                selectors_json=json.dumps(_INPUT_SELECTORS),
                prompt_json=json.dumps(prompt),
            )
            set_result = _js_sync(ws, set_js, wait=10)
            if not set_result.startswith("ok:"):
                return  # nothing we can do

            prev_count_str = _js_sync(ws, _COUNT_RESPONSES_JS, wait=5)
            prev_count = int(prev_count_str) if prev_count_str.isdigit() else 0

            time.sleep(0.5)
            _js_sync(ws, _CLICK_SEND_JS, wait=5)
            time.sleep(1.0)

            deadline = time.time() + 180
            last_text = ""
            new_response_seen = False
            stable_count = 0

            while time.time() < deadline:
                time.sleep(0.5)
                cur_count_str = _js_sync(ws, _COUNT_RESPONSES_JS, wait=5)
                cur_count = int(cur_count_str) if cur_count_str.isdigit() else 0
                if cur_count > prev_count:
                    new_response_seen = True
                if not new_response_seen:
                    continue

                text = _js_sync(ws, _READ_RESPONSE_JS, wait=5).strip()
                if not text:
                    continue

                if len(text) > len(last_text):
                    yield text[len(last_text):]
                    last_text = text

                generating = _js_sync(ws, _IS_GENERATING_JS, wait=3) == "true"
                if text == last_text and not generating:
                    stable_count += 1
                    if stable_count >= 2:
                        return
                else:
                    stable_count = 0

        finally:
            try:
                ws.close()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    bridge = MistralCDPBridge()
    port = _cdp_port()
    print(f"[mistral-cdp] checking port {port} …")
    available = bridge.is_available()
    print(f"[mistral-cdp] is_available = {available}")

    if not available:
        print(
            f"[mistral-cdp] Chrome not found on port {port} with chat.mistral.ai tab.\n"
            f"  Start Chrome with:\n"
            f"  chrome.exe --remote-debugging-port={port} --remote-allow-origins=* "
            f"https://chat.mistral.ai"
        )
        sys.exit(1)

    prompt = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "Reply with exactly: MISTRAL_CDP_OK"
    print(f"[mistral-cdp] sending prompt: {prompt!r}")
    result = bridge.simple(prompt)
    print(f"[mistral-cdp] ok={result.ok}  time={result.timing_s}s  model={result.model}")
    if result.ok:
        print(f"[mistral-cdp] response:\n{result.text}")
    else:
        print(f"[mistral-cdp] error: {result.error}", file=sys.stderr)
    sys.exit(0 if result.ok else 1)
