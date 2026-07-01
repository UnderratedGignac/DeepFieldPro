"""
ChatGPT web bridge via Chrome DevTools Protocol (CDP).

# Requires: Chrome running at --remote-debugging-port=9224 with chatgpt.com open
# Env vars: CHATGPT_CDP_PORT (default 9224)

Architecture:
    This bridge finds the chatgpt.com tab in a running Chrome instance,
    extracts the auth token from the page's session endpoint via an in-page
    fetch() call (same-origin, bypasses bot detection), then submits prompts
    to the backend conversation API and reads the SSE stream for the response.

    Chrome must be launched with:
        chrome.exe --remote-debugging-port=9224 --remote-allow-origins=*

Usage:
    from tools.llm_bridges.chatgpt_cdp import ChatGPTCDPBridge

    bridge = ChatGPTCDPBridge()
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
import uuid
from typing import Iterator

from tools.llm_bridges.base import LLMBridge, LLMResult

_DEFAULT_PORT = 9224


def _cdp_port() -> int:
    return int(os.environ.get("CHATGPT_CDP_PORT", _DEFAULT_PORT))


# ---------------------------------------------------------------------------
# Low-level CDP helpers (mirrors qwen_bridge.py pattern)
# ---------------------------------------------------------------------------


def _port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        try:
            s.connect(("localhost", port))
            return True
        except OSError:
            return False


def _get_chatgpt_tab_ws(port: int) -> str:
    """Return the WebSocket debugger URL for the chatgpt.com tab."""
    raw = urllib.request.urlopen(f"http://localhost:{port}/json", timeout=5).read()
    targets = json.loads(raw)
    for t in targets:
        url = t.get("url", "")
        if "chatgpt.com" in url and t.get("type") == "page":
            return t["webSocketDebuggerUrl"]
    # Fallback: any target with chatgpt.com
    for t in targets:
        if "chatgpt.com" in t.get("url", ""):
            return t["webSocketDebuggerUrl"]
    available = [t.get("url", "") for t in targets]
    raise RuntimeError(
        f"No chatgpt.com tab found in CDP targets on port {port}. "
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


def _js_async(ws, expression: str, wait: float = 30) -> tuple[str, str | None]:
    """
    Evaluate an async JS expression (awaitPromise=True).
    Returns (value_str, exception_text_or_None).
    """
    result = _send(
        ws,
        "Runtime.evaluate",
        {
            "expression": expression,
            "returnByValue": True,
            "awaitPromise": True,
        },
        wait=wait,
    )
    exc = result.get("exceptionDetails")
    exc_text = str(exc) if exc else None
    val = result.get("result", {}).get("value")
    return (str(val) if val is not None else ""), exc_text


def _js_sync(ws, expression: str, wait: float = 10) -> str:
    """Evaluate synchronous JS and return a string value."""
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
    val = result.get("result", {}).get("value")
    if val is None:
        return ""
    return str(val)


# ---------------------------------------------------------------------------
# Token extraction
# ---------------------------------------------------------------------------

_TOKEN_JS = """
(async () => {
  // Attempt 1: __NEXT_DATA__ session
  try {
    const nd = window.__NEXT_DATA__;
    const tok = nd?.props?.pageProps?.accessToken
             || nd?.props?.initialState?.user?.session?.accessToken;
    if (tok) return tok;
  } catch(e) {}

  // Attempt 2: fetch the session endpoint (same-origin)
  try {
    const r = await fetch('https://chatgpt.com/api/auth/session', {credentials: 'include'});
    if (r.ok) {
      const d = await r.json();
      if (d?.accessToken) return d.accessToken;
    }
  } catch(e) {}

  return 'ERROR:no_token';
})()
"""


def _get_token(ws) -> str | None:
    val, exc = _js_async(ws, _TOKEN_JS, wait=20)
    if exc or val.startswith("ERROR:"):
        return None
    if val and len(val) > 20:
        return val.strip()
    return None


# ---------------------------------------------------------------------------
# Conversation request builder
# ---------------------------------------------------------------------------


def _build_payload(user_text: str, model: str) -> dict:
    return {
        "action": "next",
        "messages": [
            {
                "id": str(uuid.uuid4()),
                "author": {"role": "user"},
                "content": {"content_type": "text", "parts": [user_text]},
                "metadata": {},
            }
        ],
        "model": model,
        "parent_message_id": str(uuid.uuid4()),
        "conversation_id": None,
    }


# ---------------------------------------------------------------------------
# In-page fetch + SSE stream reader
# ---------------------------------------------------------------------------

_STREAM_JS_TPL = """
(async () => {{
  const TOKEN = {token_json};
  const PAYLOAD = {payload_json};

  let resp;
  try {{
    resp = await fetch('https://chatgpt.com/backend-api/conversation', {{
      method: 'POST',
      credentials: 'include',
      headers: {{
        'Content-Type': 'application/json',
        'Authorization': 'Bearer ' + TOKEN,
        'Accept': 'text/event-stream'
      }},
      body: JSON.stringify(PAYLOAD)
    }});
  }} catch(e) {{
    return 'FETCH_ERR:' + e.message;
  }}

  if (!resp.ok) {{
    return 'HTTP_ERR:' + resp.status + ':' + (await resp.text()).slice(0, 300);
  }}

  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let fullText = '';

  while (true) {{
    const {{done, value}} = await reader.read();
    if (done) break;
    const lines = decoder.decode(value).split('\\n');
    for (const line of lines) {{
      if (!line.startsWith('data: ')) continue;
      const raw = line.slice(6).trim();
      if (raw === '[DONE]') {{
        window._ea_chatgpt_result = fullText;
        return fullText;
      }}
      try {{
        const d = JSON.parse(raw);
        const parts = d?.message?.content?.parts;
        if (Array.isArray(parts) && parts.length > 0 && parts[0]) {{
          fullText = parts[0];
        }}
      }} catch(e) {{}}
    }}
  }}
  window._ea_chatgpt_result = fullText;
  return fullText || 'EMPTY_RESPONSE';
}})()
"""

# Streaming variant: writes chunks to window._ea_chatgpt_buf
_STREAM_START_JS_TPL = """
(function() {{
  window._ea_chatgpt_buf   = [];
  window._ea_chatgpt_done  = false;
  window._ea_chatgpt_err   = '';
  window._ea_chatgpt_result = '';

  const TOKEN   = {token_json};
  const PAYLOAD = {payload_json};

  (async () => {{
    try {{
      const resp = await fetch('https://chatgpt.com/backend-api/conversation', {{
        method: 'POST',
        credentials: 'include',
        headers: {{
          'Content-Type': 'application/json',
          'Authorization': 'Bearer ' + TOKEN,
          'Accept': 'text/event-stream'
        }},
        body: JSON.stringify(PAYLOAD)
      }});

      if (!resp.ok) {{
        window._ea_chatgpt_err  = 'HTTP_ERR:' + resp.status;
        window._ea_chatgpt_done = true;
        return;
      }}

      const reader  = resp.body.getReader();
      const decoder = new TextDecoder();
      let prev = '';

      while (true) {{
        const {{done, value}} = await reader.read();
        if (done) {{ window._ea_chatgpt_done = true; return; }}
        const lines = decoder.decode(value).split('\\n');
        for (const line of lines) {{
          if (!line.startsWith('data: ')) continue;
          const raw = line.slice(6).trim();
          if (raw === '[DONE]') {{ window._ea_chatgpt_done = true; return; }}
          try {{
            const d     = JSON.parse(raw);
            const parts = d?.message?.content?.parts;
            if (Array.isArray(parts) && parts.length > 0 && parts[0] !== undefined) {{
              const current = String(parts[0]);
              if (current.length > prev.length) {{
                window._ea_chatgpt_buf.push(current.slice(prev.length));
                prev = current;
              }}
            }}
          }} catch(e) {{}}
        }}
      }}
    }} catch(e) {{
      window._ea_chatgpt_err  = e.message;
      window._ea_chatgpt_done = true;
    }}
  }})();

  return 'started';
}})()
"""

_STREAM_POLL_JS = (
    'JSON.stringify({'
    'c:window._ea_chatgpt_buf.splice(0),'
    'd:window._ea_chatgpt_done,'
    'e:window._ea_chatgpt_err})'
)


# ---------------------------------------------------------------------------
# Public bridge class
# ---------------------------------------------------------------------------


class ChatGPTCDPBridge(LLMBridge):
    """
    ChatGPT web bridge via Chrome DevTools Protocol.

    Drives a Chrome instance that has chatgpt.com open (must be logged in).
    All HTTP calls are made inside the page context via Runtime.evaluate +
    fetch(), so they carry the browser's cookies and bypass bot-detection.

    Chrome launch command:
        chrome.exe --remote-debugging-port=9224 --remote-allow-origins=*
    """

    provider = "chatgpt-cdp"
    default_model = "gpt-4o"
    models = ["gpt-4o", "gpt-4o-mini", "o1-mini"]

    # ------------------------------------------------------------------ #
    # LLMBridge interface
    # ------------------------------------------------------------------ #

    def is_available(self) -> bool:
        """True if Chrome is listening on the CDP port and chatgpt.com tab exists."""
        port = _cdp_port()
        if not _port_open(port):
            return False
        try:
            _get_chatgpt_tab_ws(port)
            return True
        except Exception:
            return False

    def chat(self, messages: list[dict], model: str = "") -> LLMResult:
        """Send messages and return the full response as LLMResult."""
        model = model or self.default_model
        prompt = _messages_to_prompt(messages)
        t0 = time.time()
        port = _cdp_port()

        if not _port_open(port):
            return LLMResult(
                ok=False,
                text="",
                error=f"Chrome CDP port {port} not open — start Chrome with "
                      f"--remote-debugging-port={port}",
                provider=self.provider,
                model=model,
            )

        try:
            ws_url = _get_chatgpt_tab_ws(port)
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
            token = _get_token(ws)
            if not token:
                return LLMResult(
                    ok=False, text="",
                    error="Could not extract ChatGPT auth token — is the user logged in?",
                    timing_s=round(time.time() - t0, 2),
                    provider=self.provider, model=model,
                )

            payload = _build_payload(prompt, model)
            js = _STREAM_JS_TPL.format(
                token_json=json.dumps(token),
                payload_json=json.dumps(payload),
            )
            val, exc = _js_async(ws, js, wait=120)

            if exc:
                return LLMResult(
                    ok=False, text="", error=f"JS exception: {exc}",
                    timing_s=round(time.time() - t0, 2),
                    provider=self.provider, model=model,
                )
            if val.startswith(("FETCH_ERR:", "HTTP_ERR:")):
                return LLMResult(
                    ok=False, text="", error=val,
                    timing_s=round(time.time() - t0, 2),
                    provider=self.provider, model=model,
                )
            if not val or val == "EMPTY_RESPONSE":
                return LLMResult(
                    ok=False, text="", error="Empty response from ChatGPT",
                    timing_s=round(time.time() - t0, 2),
                    provider=self.provider, model=model,
                )

            return LLMResult(
                ok=True, text=val.strip(),
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
        Stream text chunks from ChatGPT via CDP polling.
        Yields str chunks as they arrive. Raises RuntimeError on failure.
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
            ws_url = _get_chatgpt_tab_ws(port)
        except Exception as e:
            raise RuntimeError(f"CDP tab discovery failed: {e}") from e

        ws = _cdp_session(ws_url, port)
        try:
            token = _get_token(ws)
            if not token:
                raise RuntimeError(
                    "Could not extract ChatGPT auth token — is the user logged in?"
                )

            payload = _build_payload(prompt, model)
            start_js = _STREAM_START_JS_TPL.format(
                token_json=json.dumps(token),
                payload_json=json.dumps(payload),
            )

            r = _send(
                ws,
                "Runtime.evaluate",
                {"expression": start_js, "returnByValue": True, "awaitPromise": False},
                wait=10,
            )
            v = str(r.get("result", {}).get("value", ""))
            if v != "started":
                raise RuntimeError(f"Stream start returned unexpected value: {v!r}")

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
                        raise RuntimeError(f"ChatGPT stream error: {err}")
                    return

                time.sleep(0.1)

            raise RuntimeError("ChatGPT stream timed out after 180s")

        finally:
            try:
                ws.close()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _messages_to_prompt(messages: list[dict]) -> str:
    """
    Flatten a list of chat messages into a single prompt string.
    System messages are prefixed; multi-turn is joined with blank lines.
    For single user messages, returns the content directly.
    """
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
# Smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    bridge = ChatGPTCDPBridge()
    port = _cdp_port()
    print(f"[chatgpt-cdp] checking port {port} …")
    available = bridge.is_available()
    print(f"[chatgpt-cdp] is_available = {available}")

    if not available:
        print(
            f"[chatgpt-cdp] Chrome not found on port {port} with chatgpt.com tab.\n"
            f"  Start Chrome with:\n"
            f"  chrome.exe --remote-debugging-port={port} --remote-allow-origins=* "
            f"https://chatgpt.com"
        )
        sys.exit(1)

    prompt = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else (
        "Reply with exactly: CHATGPT_CDP_OK"
    )
    print(f"[chatgpt-cdp] sending prompt: {prompt!r}")
    result = bridge.simple(prompt)
    print(f"[chatgpt-cdp] ok={result.ok}  time={result.timing_s}s  model={result.model}")
    if result.ok:
        print(f"[chatgpt-cdp] response:\n{result.text}")
    else:
        print(f"[chatgpt-cdp] error: {result.error}", file=sys.stderr)
    sys.exit(0 if result.ok else 1)
