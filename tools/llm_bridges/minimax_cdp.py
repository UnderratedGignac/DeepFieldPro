"""
MiniMax Chat web bridge via Chrome DevTools Protocol (CDP).

# Requires: Chrome at port 9229 with chat.minimax.io or hailuoai.com open
# Env vars: MINIMAX_CHAT_CDP_PORT (default 9229)

Architecture:
    Extracts an auth token from the page's localStorage/cookies/__NEXT_DATA__,
    then calls the MiniMax internal chat API via in-page fetch() (same-origin,
    bypasses bot detection). Tries multiple endpoint variants automatically.

    Chrome must be launched with:
        chrome.exe --remote-debugging-port=9229 --remote-allow-origins=*

Usage:
    from tools.llm_bridges.minimax_cdp import MinimaxCDPBridge

    bridge = MinimaxCDPBridge()
    if bridge.is_available():
        result = bridge.simple("Explain the Dixon-Coles football model.")
        print(result.text)
"""

from __future__ import annotations

import json
import os
import socket
import time
import urllib.request
from typing import Iterator

from tools.llm_bridges.base import LLMBridge, LLMResult

_DEFAULT_PORT = 9229

# Candidate API paths tried in order
_MINIMAX_ENDPOINTS = [
    "/v1/text/chatcompletion_v2",
    "/api/v2/text/chat",
    "/api/chat/completions",
    "/v1/chat/completions",
]


def _cdp_port() -> int:
    return int(os.environ.get("MINIMAX_CHAT_CDP_PORT", _DEFAULT_PORT))


# ---------------------------------------------------------------------------
# Low-level CDP helpers
# ---------------------------------------------------------------------------


def _port_open(port: int) -> bool:
    try:
        s = socket.create_connection(("localhost", port), timeout=1)
        s.close()
        return True
    except Exception:
        return False


def _find_tab(port: int, url_contains: str) -> dict | None:
    try:
        raw = urllib.request.urlopen(f"http://localhost:{port}/json", timeout=3).read()
        tabs = json.loads(raw)
        for t in tabs:
            if url_contains in t.get("url", ""):
                return t
    except Exception:
        return None
    return None


def _cdp_eval(ws_url: str, js: str, await_promise: bool = False, timeout_ms: int = 60000):
    import websocket  # websocket-client

    ws = websocket.create_connection(ws_url, timeout=15)
    ws.send(
        json.dumps(
            {
                "id": 1,
                "method": "Runtime.evaluate",
                "params": {
                    "expression": js,
                    "awaitPromise": await_promise,
                    "returnByValue": True,
                    "timeout": timeout_ms,
                },
            }
        )
    )
    result = json.loads(ws.recv())
    ws.close()
    return result.get("result", {}).get("result", {}).get("value")


def _get_minimax_tab_ws(port: int) -> str:
    """Return the WebSocket debugger URL for the minimax.io or hailuoai.com tab."""
    raw = urllib.request.urlopen(f"http://localhost:{port}/json", timeout=5).read()
    targets = json.loads(raw)
    # Prefer page-type targets
    for t in targets:
        url = t.get("url", "")
        if ("minimax.io" in url or "hailuoai.com" in url) and t.get("type") == "page":
            return t["webSocketDebuggerUrl"]
    # Fallback: any matching target
    for t in targets:
        url = t.get("url", "")
        if "minimax.io" in url or "hailuoai.com" in url:
            return t["webSocketDebuggerUrl"]
    available = [t.get("url", "") for t in targets]
    raise RuntimeError(
        f"No minimax.io or hailuoai.com tab found on CDP port {port}. "
        f"Open tabs: {available}"
    )


def _cdp_session(ws_url: str, port: int):
    import websocket  # websocket-client

    return websocket.create_connection(
        ws_url, timeout=15, header={"Origin": f"http://localhost:{port}"}
    )


def _send(ws, method: str, params: dict | None = None, wait: float = 15) -> dict:
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


def _js_async(ws, expression: str, wait: float = 90) -> tuple[str, str | None]:
    result = _send(
        ws,
        "Runtime.evaluate",
        {
            "expression": expression,
            "returnByValue": True,
            "awaitPromise": True,
            "timeout": int(wait * 1000),
        },
        wait=wait + 5,
    )
    exc = result.get("exceptionDetails")
    exc_text = str(exc) if exc else None
    val = result.get("result", {}).get("value")
    return (str(val) if val is not None else ""), exc_text


def _js_sync(ws, expression: str, wait: float = 10) -> str:
    result = _send(
        ws,
        "Runtime.evaluate",
        {"expression": expression, "returnByValue": True, "awaitPromise": False},
        wait=wait,
    )
    val = result.get("result", {}).get("value")
    return str(val) if val is not None else ""


# ---------------------------------------------------------------------------
# Token extraction
# ---------------------------------------------------------------------------

_TOKEN_JS = """
(function() {
  // Try localStorage
  let token = localStorage.getItem('token') ||
              localStorage.getItem('accessToken') ||
              localStorage.getItem('Authorization') ||
              localStorage.getItem('auth_token') ||
              localStorage.getItem('user_token');

  // Try sessionStorage
  if (!token) {
    token = sessionStorage.getItem('token') ||
            sessionStorage.getItem('accessToken');
  }

  // Try cookies
  if (!token) {
    const cookies = document.cookie.split('; ').reduce((acc, c) => {
      const [k, ...v] = c.split('=');
      acc[k.trim()] = v.join('=');
      return acc;
    }, {});
    token = cookies['token'] || cookies['accessToken'] ||
            cookies['Authorization'] || cookies['auth_token'];
  }

  // Try __NEXT_DATA__
  if (!token) {
    try {
      const nd = window.__NEXT_DATA__;
      token = nd?.props?.pageProps?.token ||
              nd?.props?.pageProps?.accessToken ||
              nd?.props?.pageProps?.userInfo?.token ||
              nd?.props?.initialProps?.pageProps?.token;
    } catch(e) {}
  }

  // Try React fiber state (hailuoai pattern)
  if (!token) {
    try {
      const rootEl = document.getElementById('__NEXT_DATA__');
      if (rootEl) {
        const nd = JSON.parse(rootEl.textContent || '{}');
        token = nd?.props?.pageProps?.token;
      }
    } catch(e) {}
  }

  return token || null;
})()
"""


# ---------------------------------------------------------------------------
# MiniMax Chat API — async chat JS (tries multiple endpoints)
# ---------------------------------------------------------------------------

_MINIMAX_CHAT_JS_TPL = """
(async () => {{
  window._ea_minimax_result = '';
  window._ea_minimax_done = false;
  window._ea_minimax_err = '';

  const token = {token_json};
  if (!token) {{
    window._ea_minimax_err = 'NO_TOKEN';
    window._ea_minimax_done = true;
    return 'NO_TOKEN';
  }}

  const payload = {{
    model: {model_json},
    messages: {messages_json},
    stream: false,
    max_tokens: 4096
  }};

  const endpoints = {endpoints_json};
  let lastErr = '';

  for (const ep of endpoints) {{
    try {{
      const resp = await fetch(ep, {{
        method: 'POST',
        headers: {{
          'Content-Type': 'application/json',
          'Authorization': 'Bearer ' + token
        }},
        body: JSON.stringify(payload)
      }});

      if (!resp.ok) {{
        lastErr = 'HTTP_ERR:' + ep + ':' + resp.status;
        continue;
      }}

      const data = await resp.json();

      // Standard OpenAI-like response
      const content = data?.choices?.[0]?.message?.content ||
                      data?.choices?.[0]?.delta?.content ||
                      data?.reply ||
                      data?.result?.output?.text ||
                      data?.data?.choices?.[0]?.messages?.[0]?.text;

      if (content) {{
        window._ea_minimax_result = content;
        window._ea_minimax_done = true;
        return content;
      }}

      // Try to extract from MiniMax-specific response shape
      if (data?.base_resp?.status_code === 0) {{
        const mmContent = data?.choices?.[0]?.messages?.[0]?.text || '';
        if (mmContent) {{
          window._ea_minimax_result = mmContent;
          window._ea_minimax_done = true;
          return mmContent;
        }}
      }}

      lastErr = 'EMPTY_RESPONSE:' + ep + ':' + JSON.stringify(data).slice(0, 200);
    }} catch(e) {{
      lastErr = 'FETCH_ERR:' + ep + ':' + e.message;
    }}
  }}

  window._ea_minimax_err = lastErr;
  window._ea_minimax_done = true;
  return lastErr;
}})()
"""

# Streaming variant — SSE from the chat API, buffered into window._ea_minimax_buf
_MINIMAX_STREAM_START_JS_TPL = """
(function() {{
  window._ea_minimax_buf = [];
  window._ea_minimax_done = false;
  window._ea_minimax_err = '';
  window._ea_minimax_result = '';

  const token = {token_json};
  if (!token) {{
    window._ea_minimax_err = 'NO_TOKEN';
    window._ea_minimax_done = true;
    return 'no_token';
  }}

  const payload = {{
    model: {model_json},
    messages: {messages_json},
    stream: true,
    max_tokens: 4096
  }};

  const endpoints = {endpoints_json};

  (async () => {{
    let lastErr = '';
    for (const ep of endpoints) {{
      try {{
        const resp = await fetch(ep, {{
          method: 'POST',
          headers: {{
            'Content-Type': 'application/json',
            'Authorization': 'Bearer ' + token
          }},
          body: JSON.stringify(payload)
        }});

        if (!resp.ok) {{
          lastErr = 'HTTP_ERR:' + ep + ':' + resp.status;
          continue;
        }}

        const reader = resp.body.getReader();
        const dec = new TextDecoder();
        let accumulated = '';

        while (true) {{
          const {{done, value}} = await reader.read();
          if (done) {{ window._ea_minimax_done = true; return; }}
          const lines = dec.decode(value).split('\\n');
          for (const line of lines) {{
            if (line.startsWith('data: ')) {{
              const raw = line.slice(6).trim();
              if (raw === '[DONE]') {{ window._ea_minimax_done = true; return; }}
              try {{
                const d = JSON.parse(raw);
                // OpenAI-like SSE
                const chunk = d?.choices?.[0]?.delta?.content || '';
                // MiniMax-specific SSE
                const mmChunk = d?.choices?.[0]?.messages?.[0]?.text || '';
                const text = chunk || mmChunk;
                if (text) {{
                  // MiniMax sends full accumulated text in some modes — emit diff
                  if (text.length > accumulated.length && text.startsWith(accumulated)) {{
                    const delta = text.slice(accumulated.length);
                    window._ea_minimax_buf.push(delta);
                    accumulated = text;
                  }} else if (!text.startsWith(accumulated)) {{
                    // Delta mode
                    window._ea_minimax_buf.push(text);
                    accumulated += text;
                  }}
                  window._ea_minimax_result = accumulated;
                }}
                if (d?.choices?.[0]?.finish_reason === 'stop') {{
                  window._ea_minimax_done = true;
                  return;
                }}
              }} catch(e) {{}}
            }}
          }}
        }}
      }} catch(e) {{
        lastErr = 'FETCH_ERR:' + ep + ':' + e.message;
      }}
    }}
    window._ea_minimax_err = lastErr || 'ALL_ENDPOINTS_FAILED';
    window._ea_minimax_done = true;
  }})();

  return 'started';
}})()
"""

_MINIMAX_STREAM_POLL_JS = (
    "JSON.stringify({"
    "c:window._ea_minimax_buf.splice(0),"
    "d:window._ea_minimax_done,"
    "e:window._ea_minimax_err})"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _messages_to_openai_format(messages: list[dict]) -> list[dict]:
    """Ensure messages are in OpenAI {role, content} format."""
    result = []
    for m in messages:
        role = m.get("role", "user")
        content = str(m.get("content", ""))
        if role not in ("system", "user", "assistant"):
            role = "user"
        result.append({"role": role, "content": content})
    return result


def _messages_to_prompt(messages: list[dict]) -> str:
    """Flatten messages for simple() — returns single user string."""
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


class MinimaxCDPBridge(LLMBridge):
    """
    MiniMax Chat web bridge via Chrome DevTools Protocol.

    Drives a Chrome instance that has chat.minimax.io or hailuoai.com open
    (must be logged in). Extracts the auth token from the page, then calls
    the internal MiniMax API via in-page fetch() — same-origin, bypasses
    bot-detection.

    Chrome launch command:
        chrome.exe --remote-debugging-port=9229 --remote-allow-origins=*
    """

    provider = "minimax-cdp"
    default_model = "MiniMax-Text-01"
    models = [
        "MiniMax-Text-01",
        "abab6.5s-chat",
        "abab6.5g-chat",
    ]

    def is_available(self) -> bool:
        """True if Chrome CDP port is open AND a minimax.io or hailuoai.com tab exists."""
        port = _cdp_port()
        if not _port_open(port):
            return False
        try:
            _get_minimax_tab_ws(port)
            return True
        except Exception:
            return False

    def chat(self, messages: list[dict], model: str = "") -> LLMResult:
        """Send messages and return the full response as LLMResult."""
        model = model or self.default_model
        t0 = time.time()
        port = _cdp_port()

        if not _port_open(port):
            return LLMResult(
                ok=False,
                text="",
                error=(
                    f"Chrome CDP port {port} not open — start Chrome with "
                    f"--remote-debugging-port={port}"
                ),
                provider=self.provider,
                model=model,
            )

        try:
            ws_url = _get_minimax_tab_ws(port)
        except Exception as e:
            return LLMResult(
                ok=False,
                text="",
                error=str(e),
                timing_s=round(time.time() - t0, 2),
                provider=self.provider,
                model=model,
            )

        try:
            import websocket  # noqa: F401
        except ImportError:
            return LLMResult(
                ok=False,
                text="",
                error="websocket-client not installed: pip install websocket-client",
                provider=self.provider,
                model=model,
            )

        ws = None
        try:
            ws = _cdp_session(ws_url, port)

            # Extract token first
            token_val = _js_sync(ws, _TOKEN_JS, wait=10)
            if not token_val or token_val in ("None", "null", "undefined", ""):
                return LLMResult(
                    ok=False,
                    text="",
                    error=(
                        "Not logged in to chat.minimax.io — open the site and sign in on port "
                        + str(port)
                    ),
                    timing_s=round(time.time() - t0, 2),
                    provider=self.provider,
                    model=model,
                )

            oai_messages = _messages_to_openai_format(messages)
            js = _MINIMAX_CHAT_JS_TPL.format(
                token_json=json.dumps(token_val),
                model_json=json.dumps(model),
                messages_json=json.dumps(oai_messages),
                endpoints_json=json.dumps(_MINIMAX_ENDPOINTS),
            )
            val, exc = _js_async(ws, js, wait=120)

            if exc:
                return LLMResult(
                    ok=False,
                    text="",
                    error=f"JS exception: {exc}",
                    timing_s=round(time.time() - t0, 2),
                    provider=self.provider,
                    model=model,
                )
            if val and val.startswith(
                ("NO_TOKEN", "HTTP_ERR:", "FETCH_ERR:", "EMPTY_RESPONSE:", "ALL_ENDPOINTS_FAILED")
            ):
                return LLMResult(
                    ok=False,
                    text="",
                    error=val,
                    timing_s=round(time.time() - t0, 2),
                    provider=self.provider,
                    model=model,
                )
            if not val or val.strip() in ("None", "null", ""):
                return LLMResult(
                    ok=False,
                    text="",
                    error="Empty response from MiniMax",
                    timing_s=round(time.time() - t0, 2),
                    provider=self.provider,
                    model=model,
                )

            return LLMResult(
                ok=True,
                text=val.strip(),
                timing_s=round(time.time() - t0, 2),
                provider=self.provider,
                model=model,
            )

        except Exception as e:
            return LLMResult(
                ok=False,
                text="",
                error=str(e),
                timing_s=round(time.time() - t0, 2),
                provider=self.provider,
                model=model,
            )
        finally:
            if ws:
                try:
                    ws.close()
                except Exception:
                    pass

    def stream(self, messages: list[dict], model: str = "") -> Iterator[str]:
        """
        Stream MiniMax Chat response chunks via CDP polling.
        Yields str chunks as they arrive. Raises RuntimeError on failure.
        """
        model = model or self.default_model
        port = _cdp_port()

        if not _port_open(port):
            raise RuntimeError(
                f"Chrome CDP port {port} not open — start Chrome with "
                f"--remote-debugging-port={port}"
            )

        try:
            ws_url = _get_minimax_tab_ws(port)
        except Exception as e:
            raise RuntimeError(f"CDP tab discovery failed: {e}") from e

        ws = _cdp_session(ws_url, port)
        try:
            # Extract token
            token_val = _js_sync(ws, _TOKEN_JS, wait=10)
            if not token_val or token_val in ("None", "null", "undefined", ""):
                raise RuntimeError(
                    f"Not logged in to chat.minimax.io — open the site and sign in on port {port}"
                )

            oai_messages = _messages_to_openai_format(messages)
            start_js = _MINIMAX_STREAM_START_JS_TPL.format(
                token_json=json.dumps(token_val),
                model_json=json.dumps(model),
                messages_json=json.dumps(oai_messages),
                endpoints_json=json.dumps(_MINIMAX_ENDPOINTS),
            )
            r = _send(
                ws,
                "Runtime.evaluate",
                {"expression": start_js, "returnByValue": True, "awaitPromise": False},
                wait=10,
            )
            v = str(r.get("result", {}).get("value", ""))
            if v not in ("started",):
                raise RuntimeError(f"Stream start returned unexpected value: {v!r}")

            deadline = time.time() + 180
            while time.time() < deadline:
                pr = _send(
                    ws,
                    "Runtime.evaluate",
                    {"expression": _MINIMAX_STREAM_POLL_JS, "returnByValue": True},
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
                        raise RuntimeError(f"MiniMax stream error: {err}")
                    return

                time.sleep(0.1)

            raise RuntimeError("MiniMax Chat stream timed out after 180s")

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

    bridge = MinimaxCDPBridge()
    port = _cdp_port()
    print(f"[minimax-cdp] checking port {port} …")
    available = bridge.is_available()
    print(f"[minimax-cdp] is_available = {available}")

    if not available:
        print(
            f"[minimax-cdp] Chrome not found on port {port} with minimax.io or hailuoai.com tab.\n"
            f"  Start Chrome with:\n"
            f"  chrome.exe --remote-debugging-port={port} --remote-allow-origins=* "
            f"https://chat.minimax.io"
        )
        sys.exit(1)

    prompt = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "Reply with exactly: MINIMAX_CDP_OK"
    model = bridge.default_model
    print(f"[minimax-cdp] model={model}  prompt={prompt!r}")
    result = bridge.simple(prompt, model=model)
    print(f"[minimax-cdp] ok={result.ok}  time={result.timing_s}s")
    if result.ok:
        print(f"[minimax-cdp] response:\n{result.text}")
    else:
        print(f"[minimax-cdp] error: {result.error}", file=sys.stderr)
    sys.exit(0 if result.ok else 1)
