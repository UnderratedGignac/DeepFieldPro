"""
Claude.ai web bridge via Chrome DevTools Protocol (CDP).

# Requires: Chrome running at --remote-debugging-port=9227 with claude.ai open
# Env vars: CLAUDE_CDP_PORT (default 9227)

Architecture:
    Finds the claude.ai tab in a running Chrome instance, extracts the
    organisation UUID from the URL or a same-origin API call, then creates a
    new conversation and streams the response — all via in-page fetch() calls
    that carry the browser's session cookies (bypasses bot detection).

    Chrome must be launched with:
        chrome.exe --remote-debugging-port=9227 --remote-allow-origins=*

Usage:
    from tools.llm_bridges.claude_cdp import ClaudeCDPBridge

    bridge = ClaudeCDPBridge()
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

_DEFAULT_PORT = 9227


def _cdp_port() -> int:
    return int(os.environ.get("CLAUDE_CDP_PORT", _DEFAULT_PORT))


# ---------------------------------------------------------------------------
# Low-level CDP helpers (mirrors chatgpt_cdp.py pattern)
# ---------------------------------------------------------------------------


def _port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        try:
            s.connect(("localhost", port))
            return True
        except OSError:
            return False


def _get_claude_tab_ws(port: int) -> str:
    """Return the WebSocket debugger URL for the claude.ai tab."""
    raw = urllib.request.urlopen(f"http://localhost:{port}/json", timeout=5).read()
    targets = json.loads(raw)
    for t in targets:
        url = t.get("url", "")
        if "claude.ai" in url and t.get("type") == "page":
            return t["webSocketDebuggerUrl"]
    # Fallback: any target matching
    for t in targets:
        if "claude.ai" in t.get("url", ""):
            return t["webSocketDebuggerUrl"]
    available = [t.get("url", "") for t in targets]
    raise RuntimeError(
        f"No claude.ai tab found in CDP targets on port {port}. "
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
    """Evaluate an async JS expression (awaitPromise=True).
    Returns (value_str, exception_text_or_None)."""
    result = _send(
        ws,
        "Runtime.evaluate",
        {
            "expression": expression,
            "returnByValue": True,
            "awaitPromise": True,
            "timeout": 60000,
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
# Org-ID extraction
# ---------------------------------------------------------------------------

_ORG_ID_JS = """
(async () => {
  // 1. Try current URL pathname
  const urlMatch = window.location.pathname.match(/\\/([a-f0-9-]{36})\\//);
  if (urlMatch) return urlMatch[1];

  // 2. Fetch from accounts API (same-origin, cookies included)
  try {
    const r = await fetch('https://claude.ai/api/auth/claude_accounts', {credentials: 'include'});
    if (r.ok) {
      const d = await r.json();
      const org = d?.organizations?.[0]?.uuid
               || d?.memberships?.[0]?.organization?.uuid;
      if (org) return org;
    }
  } catch(e) {}

  // 3. Try /api/organizations
  try {
    const r2 = await fetch('https://claude.ai/api/organizations', {credentials: 'include'});
    if (r2.ok) {
      const orgs = await r2.json();
      if (Array.isArray(orgs) && orgs.length > 0) return orgs[0].uuid || orgs[0].id;
      if (orgs?.uuid) return orgs.uuid;
    }
  } catch(e) {}

  return null;
})()
"""


def _get_org_id(ws) -> str | None:
    val, exc = _js_async(ws, _ORG_ID_JS, wait=20)
    if exc:
        return None
    if val and val not in ("None", "null", "undefined", "") and len(val) > 8:
        return val.strip()
    return None


# ---------------------------------------------------------------------------
# Two-step conversation API (create conv → stream completion)
# ---------------------------------------------------------------------------

_CHAT_JS_TPL = """
(async () => {{
  const ORG_ID = {org_id_json};
  const MODEL  = {model_json};
  const PROMPT = {prompt_json};

  // Step 1: create a fresh conversation
  let convId;
  try {{
    const convResp = await fetch(
      'https://claude.ai/api/organizations/' + ORG_ID + '/chat_conversations',
      {{
        method: 'POST',
        credentials: 'include',
        headers: {{'Content-Type': 'application/json'}},
        body: JSON.stringify({{uuid: crypto.randomUUID(), name: ''}})
      }}
    );
    if (!convResp.ok) {{
      return 'CONV_ERR:' + convResp.status + ':' + (await convResp.text()).slice(0, 200);
    }}
    const conv = await convResp.json();
    convId = conv.uuid || conv.id;
    if (!convId) return 'CONV_ERR:no_uuid_in_response';
  }} catch(e) {{
    return 'CONV_ERR:' + e.message;
  }}

  // Step 2: stream the completion
  let resp;
  try {{
    resp = await fetch(
      'https://claude.ai/api/organizations/' + ORG_ID +
      '/chat_conversations/' + convId + '/completion',
      {{
        method: 'POST',
        credentials: 'include',
        headers: {{'Content-Type': 'application/json'}},
        body: JSON.stringify({{
          attachments: [],
          files: [],
          model: MODEL,
          rendering_mode: 'raw',
          prompt: PROMPT
        }})
      }}
    );
  }} catch(e) {{
    return 'FETCH_ERR:' + e.message;
  }}

  if (!resp.ok) {{
    let body = '';
    try {{ body = (await resp.text()).slice(0, 300); }} catch(e) {{}}
    return 'HTTP_ERR:' + resp.status + ':' + body;
  }}

  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let fullText = '';

  while (true) {{
    let chunk;
    try {{ chunk = await reader.read(); }} catch(e) {{ break; }}
    if (chunk.done) break;
    const lines = decoder.decode(chunk.value).split('\\n');
    for (const line of lines) {{
      if (!line.startsWith('data: ')) continue;
      const raw = line.slice(6).trim();
      if (raw === '[DONE]') {{
        window._ea_claude_result = fullText;
        return fullText;
      }}
      try {{
        const d = JSON.parse(raw);
        if (d?.type === 'content_block_delta' && d?.delta?.type === 'text_delta') {{
          fullText += d.delta.text || '';
        }}
        // Also handle older format
        if (d?.completion) fullText += d.completion;
      }} catch(e) {{}}
    }}
  }}
  window._ea_claude_result = fullText;
  return fullText || 'EMPTY_RESPONSE';
}})()
"""

# Streaming variant — fires async then returns immediately; chunks go to window._ea_claude_buf
_STREAM_START_JS_TPL = """
(function() {{
  window._ea_claude_buf    = [];
  window._ea_claude_done   = false;
  window._ea_claude_err    = '';
  window._ea_claude_result = '';

  const ORG_ID = {org_id_json};
  const MODEL  = {model_json};
  const PROMPT = {prompt_json};

  (async () => {{
    try {{
      // Step 1: create conversation
      const convResp = await fetch(
        'https://claude.ai/api/organizations/' + ORG_ID + '/chat_conversations',
        {{
          method: 'POST',
          credentials: 'include',
          headers: {{'Content-Type': 'application/json'}},
          body: JSON.stringify({{uuid: crypto.randomUUID(), name: ''}})
        }}
      );
      if (!convResp.ok) {{
        window._ea_claude_err  = 'CONV_ERR:' + convResp.status;
        window._ea_claude_done = true;
        return;
      }}
      const conv = await convResp.json();
      const convId = conv.uuid || conv.id;
      if (!convId) {{
        window._ea_claude_err  = 'CONV_ERR:no_uuid';
        window._ea_claude_done = true;
        return;
      }}

      // Step 2: stream
      const resp = await fetch(
        'https://claude.ai/api/organizations/' + ORG_ID +
        '/chat_conversations/' + convId + '/completion',
        {{
          method: 'POST',
          credentials: 'include',
          headers: {{'Content-Type': 'application/json'}},
          body: JSON.stringify({{
            attachments: [],
            files: [],
            model: MODEL,
            rendering_mode: 'raw',
            prompt: PROMPT
          }})
        }}
      );

      if (!resp.ok) {{
        window._ea_claude_err  = 'HTTP_ERR:' + resp.status;
        window._ea_claude_done = true;
        return;
      }}

      const reader  = resp.body.getReader();
      const decoder = new TextDecoder();

      while (true) {{
        let chunk;
        try {{ chunk = await reader.read(); }} catch(e) {{ break; }}
        if (chunk.done) {{ window._ea_claude_done = true; return; }}
        const lines = decoder.decode(chunk.value).split('\\n');
        for (const line of lines) {{
          if (!line.startsWith('data: ')) continue;
          const raw = line.slice(6).trim();
          if (raw === '[DONE]') {{ window._ea_claude_done = true; return; }}
          try {{
            const d = JSON.parse(raw);
            let delta = '';
            if (d?.type === 'content_block_delta' && d?.delta?.type === 'text_delta') {{
              delta = d.delta.text || '';
            }} else if (d?.completion) {{
              delta = d.completion;
            }}
            if (delta) {{
              window._ea_claude_buf.push(delta);
              window._ea_claude_result += delta;
            }}
          }} catch(e) {{}}
        }}
      }}
    }} catch(e) {{
      window._ea_claude_err  = e.message;
      window._ea_claude_done = true;
    }}
  }})();

  return 'started';
}})()
"""

_STREAM_POLL_JS = (
    'JSON.stringify({'
    'c:window._ea_claude_buf.splice(0),'
    'd:window._ea_claude_done,'
    'e:window._ea_claude_err})'
)


# ---------------------------------------------------------------------------
# Public bridge class
# ---------------------------------------------------------------------------


class ClaudeCDPBridge(LLMBridge):
    """
    Claude.ai web bridge via Chrome DevTools Protocol.

    Drives a Chrome instance that has claude.ai open (must be logged in).
    All HTTP calls are made inside the page context via Runtime.evaluate + fetch(),
    so they carry the browser's session cookies, bypassing bot detection.

    Chrome launch command:
        chrome.exe --remote-debugging-port=9227 --remote-allow-origins=*
    """

    provider = "claude-cdp"
    default_model = "claude-3-5-sonnet-20241022"
    models = [
        "claude-3-5-sonnet-20241022",
        "claude-3-5-haiku-20241022",
        "claude-3-opus-20240229",
    ]

    # ------------------------------------------------------------------ #
    # LLMBridge interface
    # ------------------------------------------------------------------ #

    def is_available(self) -> bool:
        """True if Chrome is listening on the CDP port and a claude.ai tab exists."""
        port = _cdp_port()
        if not _port_open(port):
            return False
        try:
            _get_claude_tab_ws(port)
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
                error=(
                    f"Chrome CDP port {port} not open — start Chrome with "
                    f"--remote-debugging-port={port}"
                ),
                provider=self.provider,
                model=model,
            )

        try:
            ws_url = _get_claude_tab_ws(port)
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

            org_id = _get_org_id(ws)
            if not org_id:
                return LLMResult(
                    ok=False, text="",
                    error=(
                        "Could not find org ID — navigate to claude.ai/new in Chrome "
                        "on port 9227"
                    ),
                    timing_s=round(time.time() - t0, 2),
                    provider=self.provider, model=model,
                )

            js = _CHAT_JS_TPL.format(
                org_id_json=json.dumps(org_id),
                model_json=json.dumps(model),
                prompt_json=json.dumps(prompt),
            )
            val, exc = _js_async(ws, js, wait=120)

            if exc:
                return LLMResult(
                    ok=False, text="", error=f"JS exception: {exc}",
                    timing_s=round(time.time() - t0, 2),
                    provider=self.provider, model=model,
                )
            if val.startswith(("FETCH_ERR:", "HTTP_ERR:", "CONV_ERR:")):
                return LLMResult(
                    ok=False, text="", error=val,
                    timing_s=round(time.time() - t0, 2),
                    provider=self.provider, model=model,
                )
            if not val or val == "EMPTY_RESPONSE":
                return LLMResult(
                    ok=False, text="", error="Empty response from Claude",
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
        Stream text chunks from Claude.ai via CDP polling.
        Fires the fetch asynchronously, then polls window._ea_claude_buf every 100ms.
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
            ws_url = _get_claude_tab_ws(port)
        except Exception as e:
            raise RuntimeError(f"CDP tab discovery failed: {e}") from e

        ws = _cdp_session(ws_url, port)
        try:
            org_id = _get_org_id(ws)
            if not org_id:
                raise RuntimeError(
                    "Could not find org ID — navigate to claude.ai/new in Chrome "
                    "on port 9227"
                )

            start_js = _STREAM_START_JS_TPL.format(
                org_id_json=json.dumps(org_id),
                model_json=json.dumps(model),
                prompt_json=json.dumps(prompt),
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
                        raise RuntimeError(f"Claude stream error: {err}")
                    return

                time.sleep(0.1)

            raise RuntimeError("Claude stream timed out after 180s")

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

    bridge = ClaudeCDPBridge()
    port = _cdp_port()
    print(f"[claude-cdp] checking port {port} ...")
    available = bridge.is_available()
    print(f"[claude-cdp] is_available = {available}")

    if not available:
        print(
            f"[claude-cdp] Chrome not found on port {port} with claude.ai tab.\n"
            f"  Start Chrome with:\n"
            f"  chrome.exe --remote-debugging-port={port} --remote-allow-origins=* "
            f"https://claude.ai/new"
        )
        sys.exit(1)

    prompt = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else (
        "Reply with exactly: CLAUDE_CDP_OK"
    )
    print(f"[claude-cdp] sending prompt: {prompt!r}")
    result = bridge.simple(prompt)
    print(f"[claude-cdp] ok={result.ok}  time={result.timing_s}s  model={result.model}")
    if result.ok:
        print(f"[claude-cdp] response:\n{result.text}")
    else:
        print(f"[claude-cdp] error: {result.error}", file=sys.stderr)
    sys.exit(0 if result.ok else 1)
