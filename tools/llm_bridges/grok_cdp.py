"""
Grok web bridge via Chrome DevTools Protocol (CDP).

# NOTE: Requires Chrome open at x.com/i/grok (or grok.x.com) on CDP port 9231
#       with the user logged into X (Twitter).
# Env vars: GROK_CDP_PORT (default 9231)

Architecture:
    Primary path — in-page fetch() to X's internal Grok GraphQL API:
        Extracts the X auth_token (cookie) and CSRF token (ct0 cookie/localStorage),
        then POSTs to the GrokConversation GraphQL endpoint via in-page fetch() so the
        request carries the full browser session (OAuth2Session) and bypasses bot checks.
        SSE response is read with a ReadableStream reader; chunks are written to
        window._ea_grok_buf for polling by the Python side.

    Fallback path — DOM injection:
        If the GraphQL endpoint returns an error (queryId rotated, endpoint changed),
        the bridge falls back to finding the Grok textarea, injecting the prompt, and
        polling the DOM for the assistant response text.

    Chrome must be launched with:
        chrome.exe --remote-debugging-port=9231 --remote-allow-origins=*

Usage:
    from tools.llm_bridges.grok_cdp import GrokCDPBridge

    bridge = GrokCDPBridge()
    if bridge.is_available():
        result = bridge.simple("Analyse the Dixon-Coles model for football betting.")
        print(result.text)

Notes:
    - The user must be logged into X (Twitter) on port 9231.
    - X rotates GraphQL queryIds fairly often. If the primary path stops working,
      inspect the Network tab for GrokConversation requests and update
      _GROK_QUERY_ID below.
    - X uses a public Bearer token for web requests; it's safe to embed here as it's
      the same one shipped in every X web-app bundle.
    - For a key-based Grok API, use the official xAI SDK instead.
"""

from __future__ import annotations

import json
import os
import socket
import time
import urllib.request
from typing import Iterator

from tools.llm_bridges.base import LLMBridge, LLMResult

_DEFAULT_PORT = 9231

# The X web-app's public Bearer token (same across all browsers — not a secret).
_X_BEARER = (
    "AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D"
    "1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"
)

# GraphQL queryId for GrokConversation — rotate this when X changes it.
_GROK_QUERY_ID = "dM3trWBlb2sF9GdGSqZQow"

# DOM selectors for the Grok input box
_INPUT_SELECTORS = [
    "textarea[data-testid='tweetTextarea_0']",
    "div[data-testid='DraftEditorPlaceholder']",
    "[role='textbox']",
    "textarea[placeholder]",
    "textarea",
]

# Grok response message selectors (X's class names are minified; match broadly)
_RESPONSE_SELECTORS = [
    "[data-testid='grokMessage']",
    "[class*='grok'][class*='message']",
    "[class*='GrokMessage']",
    "[class*='assistant']",
    "[class*='response']",
]

# Send / submit button selectors
_SEND_BUTTON_SELECTORS = [
    "button[data-testid='tweetButton']",
    "button[data-testid='sendButton']",
    "button[aria-label*='Send']",
    "button[aria-label*='Ask']",
    "button[type='submit']",
]


def _cdp_port() -> int:
    return int(os.environ.get("GROK_CDP_PORT", _DEFAULT_PORT))


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


def _get_grok_tab_ws(port: int) -> str:
    """Return the WebSocket debugger URL for the x.com/i/grok or grok.x.com tab."""
    raw = urllib.request.urlopen(f"http://localhost:{port}/json", timeout=5).read()
    targets = json.loads(raw)
    # Prefer exact Grok URL matches
    for t in targets:
        url = t.get("url", "")
        if ("x.com/i/grok" in url or "grok.x.com" in url) and t.get("type") == "page":
            return t["webSocketDebuggerUrl"]
    # Broad fallback: any x.com page (user might have navigated away slightly)
    for t in targets:
        url = t.get("url", "")
        if "x.com" in url and t.get("type") == "page":
            return t["webSocketDebuggerUrl"]
    available = [t.get("url", "") for t in targets]
    raise RuntimeError(
        f"No x.com/i/grok or grok.x.com tab found in CDP targets on port {port}. "
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
# Token extraction (X auth_token + CSRF)
# ---------------------------------------------------------------------------

_TOKEN_JS = """
(function() {
  let authToken = null;
  let csrfToken = null;

  // 1. Parse cookies — X stores auth_token and ct0 (CSRF) in cookies
  try {
    const cookies = document.cookie.split('; ').reduce((acc, c) => {
      const [k, ...v] = c.split('='); acc[k] = v.join('='); return acc;
    }, {});
    authToken = cookies['auth_token'] || null;
    csrfToken = cookies['ct0'] || null;
  } catch(e) {}

  // 2. Try localStorage for ct0 (some X versions store it there too)
  if (!csrfToken) {
    try { csrfToken = localStorage.getItem('ct0'); } catch(e) {}
  }
  if (!authToken) {
    try { authToken = localStorage.getItem('auth_token'); } catch(e) {}
  }

  // 3. Try to read from window.__NEXT_DATA__ or X's redux state
  if (!authToken || !csrfToken) {
    try {
      const nd = window.__NEXT_DATA__;
      if (nd) {
        const s = nd?.props?.initialState || nd?.props?.pageProps?.session;
        if (s) {
          authToken = authToken || s?.auth_token || s?.user?.auth_token || null;
          csrfToken = csrfToken || s?.ct0 || null;
        }
      }
    } catch(e) {}
  }

  return JSON.stringify({authToken: authToken, csrfToken: csrfToken});
})()
"""


def _get_tokens(ws) -> tuple[str | None, str | None]:
    """Return (auth_token, csrf_token) or (None, None) on failure."""
    raw = _js_sync(ws, _TOKEN_JS, wait=10)
    try:
        d = json.loads(raw)
        auth = d.get("authToken") or None
        csrf = d.get("csrfToken") or None
        return auth, csrf
    except Exception:
        return None, None


# ---------------------------------------------------------------------------
# Primary path: Grok GraphQL API via in-page fetch
# ---------------------------------------------------------------------------

# Background streaming — writes chunks to window._ea_grok_buf
_GROK_STREAM_START_JS_TPL = """
(function() {{
  window._ea_grok_buf  = [];
  window._ea_grok_done = false;
  window._ea_grok_err  = '';

  const BEARER   = {bearer_json};
  const CSRF     = {csrf_json};
  const QUERY_ID = {query_id_json};
  const MODEL    = {model_json};
  const PROMPT   = {prompt_json};

  (async () => {{
    try {{
      const resp = await fetch(
        'https://x.com/i/api/graphql/' + QUERY_ID + '/GrokConversation',
        {{
          method: 'POST',
          credentials: 'include',
          headers: {{
            'Content-Type': 'application/json',
            'Authorization': 'Bearer ' + BEARER,
            'X-Csrf-Token': CSRF,
            'X-Twitter-Auth-Type': 'OAuth2Session',
            'X-Twitter-Active-User': 'yes',
            'X-Twitter-Client-Language': 'en',
          }},
          body: JSON.stringify({{
            variables: {{
              conversationId: '',
              message: PROMPT,
              model: MODEL === 'grok-3' ? 'grok-latest'
                   : MODEL === 'grok-3-mini' ? 'grok-mini-latest'
                   : 'grok-latest',
              returnSearchResults: false,
              returnCitations: false,
            }},
            queryId: QUERY_ID
          }})
        }}
      );

      if (!resp.ok) {{
        window._ea_grok_err  = 'HTTP_ERR:' + resp.status + ':' + (await resp.text()).slice(0, 200);
        window._ea_grok_done = true;
        return;
      }}

      const reader  = resp.body.getReader();
      const decoder = new TextDecoder();
      let accumulated = '';

      while (true) {{
        const {{done, value}} = await reader.read();
        if (done) {{ window._ea_grok_done = true; return; }}

        const text = decoder.decode(value);
        const lines = text.split('\\n');

        for (const line of lines) {{
          if (!line.startsWith('data: ')) continue;
          const raw = line.slice(6).trim();
          if (!raw || raw === '[DONE]') {{ window._ea_grok_done = true; return; }}
          try {{
            const d = JSON.parse(raw);
            // X Grok SSE format varies; try multiple paths
            const chunk = d?.result?.message?.message
                       || d?.result?.message
                       || d?.data?.message
                       || null;
            if (chunk && typeof chunk === 'string') {{
              // Grok often sends the FULL accumulated text; extract delta
              if (chunk.length > accumulated.length) {{
                const delta = chunk.slice(accumulated.length);
                window._ea_grok_buf.push(delta);
                accumulated = chunk;
              }} else if (chunk.length === accumulated.length) {{
                // no change
              }} else {{
                // shorter than accumulated — treat as a fresh chunk
                window._ea_grok_buf.push(chunk);
                accumulated += chunk;
              }}
            }}
          }} catch(e) {{}}
        }}
      }}
    }} catch(e) {{
      window._ea_grok_err  = e.message;
      window._ea_grok_done = true;
    }}
  }})();

  return 'started';
}})()
"""

_STREAM_POLL_JS = (
    'JSON.stringify({'
    'c:window._ea_grok_buf.splice(0),'
    'd:window._ea_grok_done,'
    'e:window._ea_grok_err})'
)

# One-shot (non-streaming) variant for chat()
_GROK_ONESHOT_JS_TPL = """
(async () => {{
  const BEARER   = {bearer_json};
  const CSRF     = {csrf_json};
  const QUERY_ID = {query_id_json};
  const MODEL    = {model_json};
  const PROMPT   = {prompt_json};

  try {{
    const resp = await fetch(
      'https://x.com/i/api/graphql/' + QUERY_ID + '/GrokConversation',
      {{
        method: 'POST',
        credentials: 'include',
        headers: {{
          'Content-Type': 'application/json',
          'Authorization': 'Bearer ' + BEARER,
          'X-Csrf-Token': CSRF,
          'X-Twitter-Auth-Type': 'OAuth2Session',
          'X-Twitter-Active-User': 'yes',
          'X-Twitter-Client-Language': 'en',
        }},
        body: JSON.stringify({{
          variables: {{
            conversationId: '',
            message: PROMPT,
            model: MODEL === 'grok-3' ? 'grok-latest'
                 : MODEL === 'grok-3-mini' ? 'grok-mini-latest'
                 : 'grok-latest',
            returnSearchResults: false,
            returnCitations: false,
          }},
          queryId: QUERY_ID
        }})
      }}
    );

    if (!resp.ok) {{
      return 'HTTP_ERR:' + resp.status;
    }}

    const reader  = resp.body.getReader();
    const decoder = new TextDecoder();
    let accumulated = '';

    while (true) {{
      const {{done, value}} = await reader.read();
      if (done) break;
      const lines = decoder.decode(value).split('\\n');
      for (const line of lines) {{
        if (!line.startsWith('data: ')) continue;
        const raw = line.slice(6).trim();
        if (!raw || raw === '[DONE]') {{ return accumulated || 'EMPTY_RESPONSE'; }}
        try {{
          const d = JSON.parse(raw);
          const chunk = d?.result?.message?.message
                     || d?.result?.message
                     || d?.data?.message
                     || null;
          if (chunk && typeof chunk === 'string' && chunk.length > accumulated.length) {{
            accumulated = chunk;
          }}
        }} catch(e) {{}}
      }}
    }}

    return accumulated || 'EMPTY_RESPONSE';
  }} catch(e) {{
    return 'FETCH_ERR:' + e.message;
  }}
}})()
"""


# ---------------------------------------------------------------------------
# Fallback path: DOM injection
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
  // Heuristic: any visible send-looking button
  for (const btn of document.querySelectorAll('button')) {
    const r = btn.getBoundingClientRect();
    if (r.width === 0 || r.height === 0) continue;
    const aria  = (btn.getAttribute('aria-label') || '').toLowerCase();
    const title = (btn.getAttribute('title') || '').toLowerCase();
    const text  = (btn.innerText || '').trim().toLowerCase();
    if (aria.includes('send') || aria.includes('ask') ||
        title.includes('send') || text === 'send' || text === 'ask') {
      btn.dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true, view: window}));
      return 'clicked:fallback';
    }
  }
  // Last resort: Enter key
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
    '[aria-label*="Loading"]',
    '[aria-label*="Generating"]',
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


class GrokCDPBridge(LLMBridge):
    """
    Grok web bridge via Chrome DevTools Protocol.

    Drives a Chrome instance that has x.com/i/grok open (must be logged into X).
    Primary path: fires the GrokConversation GraphQL endpoint via in-page fetch()
    (carries the browser session, bypasses bot detection). SSE response is streamed
    and accumulated in window._ea_grok_buf for polling.
    Fallback path: DOM injection (textarea + send button) with polling.

    Chrome launch command:
        chrome.exe --remote-debugging-port=9231 --remote-allow-origins=*

    Note: X's GraphQL queryIds rotate. Update _GROK_QUERY_ID in this file
    if the primary path returns HTTP 400 or 404.
    """

    provider = "grok-cdp"
    default_model = "grok-3"
    models = ["grok-3", "grok-3-mini", "grok-2"]

    def is_available(self) -> bool:
        """True if Chrome is on CDP port and a Grok tab (x.com/i/grok or grok.x.com) exists."""
        port = _cdp_port()
        if not _port_open(port):
            return False
        try:
            _get_grok_tab_ws(port)
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
            ws_url = _get_grok_tab_ws(port)
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

            # Extract auth tokens
            auth_token, csrf_token = _get_tokens(ws)

            if auth_token and csrf_token:
                # Primary path: GraphQL API
                api_js = _GROK_ONESHOT_JS_TPL.format(
                    bearer_json=json.dumps(_X_BEARER),
                    csrf_json=json.dumps(csrf_token),
                    query_id_json=json.dumps(_GROK_QUERY_ID),
                    model_json=json.dumps(model),
                    prompt_json=json.dumps(prompt),
                )
                val, exc = _js_async(ws, api_js, wait=90)

                if not exc and val and not val.startswith(("FETCH_ERR:", "HTTP_ERR:", "EMPTY")):
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
        Stream Grok response chunks via CDP polling.
        Primary: async SSE via in-page fetch writing to window._ea_grok_buf.
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
            ws_url = _get_grok_tab_ws(port)
        except Exception as e:
            raise RuntimeError(f"CDP tab discovery failed: {e}") from e

        ws = _cdp_session(ws_url, port)
        api_succeeded = False
        try:
            auth_token, csrf_token = _get_tokens(ws)

            if auth_token and csrf_token:
                start_js = _GROK_STREAM_START_JS_TPL.format(
                    bearer_json=json.dumps(_X_BEARER),
                    csrf_json=json.dumps(csrf_token),
                    query_id_json=json.dumps(_GROK_QUERY_ID),
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
                    deadline = time.time() + 180
                    yielded_any = False
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
                                yielded_any = True

                        if data.get("d"):
                            err = data.get("e", "")
                            if err and not yielded_any:
                                break  # fall through to DOM
                            api_succeeded = True
                            return

                        time.sleep(0.1)

            if api_succeeded:
                return

            # DOM streaming fallback
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

    bridge = GrokCDPBridge()
    port = _cdp_port()
    print(f"[grok-cdp] checking port {port} …")
    available = bridge.is_available()
    print(f"[grok-cdp] is_available = {available}")

    if not available:
        print(
            f"[grok-cdp] Chrome not found on port {port} with x.com/i/grok tab.\n"
            f"  Start Chrome with:\n"
            f"  chrome.exe --remote-debugging-port={port} --remote-allow-origins=* "
            f"https://x.com/i/grok"
        )
        sys.exit(1)

    prompt = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "Reply with exactly: GROK_CDP_OK"
    print(f"[grok-cdp] sending prompt: {prompt!r}")
    result = bridge.simple(prompt)
    print(f"[grok-cdp] ok={result.ok}  time={result.timing_s}s  model={result.model}")
    if result.ok:
        print(f"[grok-cdp] response:\n{result.text}")
    else:
        print(f"[grok-cdp] error: {result.error}", file=sys.stderr)
    sys.exit(0 if result.ok else 1)
