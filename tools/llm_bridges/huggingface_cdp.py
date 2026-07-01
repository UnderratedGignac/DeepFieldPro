"""
HuggingFace Chat web bridge via Chrome DevTools Protocol (CDP).

# Requires: Chrome at port 9228 with huggingface.co/chat open
# Env vars: HF_CHAT_CDP_PORT (default 9228)

Architecture:
    Uses the HuggingFace Chat internal web API (no API key needed — relies on
    browser cookies for auth). The bridge injects JavaScript into the live
    huggingface.co/chat tab via CDP to:
      1. POST /chat/conversation to create a new conversation (picks the model).
      2. POST /chat/conversation/{id} with the user message and reads the SSE
         stream response in-page.

    Chrome must be launched with:
        chrome.exe --remote-debugging-port=9228 --remote-allow-origins=*

Usage:
    from tools.llm_bridges.huggingface_cdp import HuggingFaceCDPBridge

    bridge = HuggingFaceCDPBridge()
    if bridge.is_available():
        result = bridge.simple("What is Dixon-Coles?")
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

_DEFAULT_PORT = 9228


def _cdp_port() -> int:
    return int(os.environ.get("HF_CHAT_CDP_PORT", _DEFAULT_PORT))


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


def _get_hf_tab_ws(port: int) -> str:
    """Return the WebSocket debugger URL for the huggingface.co/chat tab."""
    raw = urllib.request.urlopen(f"http://localhost:{port}/json", timeout=5).read()
    targets = json.loads(raw)
    for t in targets:
        url = t.get("url", "")
        if "huggingface.co/chat" in url and t.get("type") == "page":
            return t["webSocketDebuggerUrl"]
    for t in targets:
        if "huggingface.co/chat" in t.get("url", ""):
            return t["webSocketDebuggerUrl"]
    available = [t.get("url", "") for t in targets]
    raise RuntimeError(
        f"No huggingface.co/chat tab found on CDP port {port}. Open tabs: {available}"
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
# HuggingFace Chat API — async chat JS
# ---------------------------------------------------------------------------

_HF_CHAT_JS_TPL = """
(async () => {{
  window._ea_hf_result = '';
  window._ea_hf_done = false;
  window._ea_hf_err = '';

  try {{
    // Step 1: Create a new conversation with the chosen model
    const createResp = await fetch('https://huggingface.co/chat/conversation', {{
      method: 'POST',
      credentials: 'include',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{model: {model_json}}})
    }});
    if (!createResp.ok) {{
      window._ea_hf_err = 'CREATE_ERR:' + createResp.status + ':' + (await createResp.text()).slice(0, 200);
      window._ea_hf_done = true;
      return window._ea_hf_err;
    }}
    const {{conversationId}} = await createResp.json();
    if (!conversationId) {{
      window._ea_hf_err = 'NO_CONV_ID';
      window._ea_hf_done = true;
      return window._ea_hf_err;
    }}

    // Step 2: Send the message and read SSE stream
    const msgResp = await fetch('https://huggingface.co/chat/conversation/' + conversationId, {{
      method: 'POST',
      credentials: 'include',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{
        inputs: {prompt_json},
        id: crypto.randomUUID(),
        is_retry: false,
        is_continue: false,
        web_search_id: ''
      }})
    }});
    if (!msgResp.ok) {{
      window._ea_hf_err = 'MSG_ERR:' + msgResp.status + ':' + (await msgResp.text()).slice(0, 200);
      window._ea_hf_done = true;
      return window._ea_hf_err;
    }}

    const reader = msgResp.body.getReader();
    const dec = new TextDecoder();
    let text = '';
    while (true) {{
      const {{done, value}} = await reader.read();
      if (done) break;
      const lines = dec.decode(value).split('\\n');
      for (const line of lines) {{
        if (line.startsWith('data: ')) {{
          try {{
            const d = JSON.parse(line.slice(6));
            if (d.type === 'stream') text += d.token?.text || '';
            if (d.type === 'finalAnswer') text = d.text || text;
          }} catch(e) {{}}
        }}
      }}
    }}
    window._ea_hf_result = text;
    window._ea_hf_done = true;
    return text;

  }} catch(e) {{
    window._ea_hf_err = 'JS_ERR:' + e.message;
    window._ea_hf_done = true;
    return window._ea_hf_err;
  }}
}})()
"""

# Streaming variant — fires async in background, polls via _ea_hf_buf
_HF_STREAM_START_JS_TPL = """
(function() {{
  window._ea_hf_buf = [];
  window._ea_hf_done = false;
  window._ea_hf_err = '';
  window._ea_hf_result = '';

  (async () => {{
    try {{
      const createResp = await fetch('https://huggingface.co/chat/conversation', {{
        method: 'POST',
        credentials: 'include',
        headers: {{'Content-Type': 'application/json'}},
        body: JSON.stringify({{model: {model_json}}})
      }});
      if (!createResp.ok) {{
        window._ea_hf_err = 'CREATE_ERR:' + createResp.status;
        window._ea_hf_done = true;
        return;
      }}
      const {{conversationId}} = await createResp.json();
      if (!conversationId) {{
        window._ea_hf_err = 'NO_CONV_ID';
        window._ea_hf_done = true;
        return;
      }}

      const msgResp = await fetch('https://huggingface.co/chat/conversation/' + conversationId, {{
        method: 'POST',
        credentials: 'include',
        headers: {{'Content-Type': 'application/json'}},
        body: JSON.stringify({{
          inputs: {prompt_json},
          id: crypto.randomUUID(),
          is_retry: false,
          is_continue: false,
          web_search_id: ''
        }})
      }});
      if (!msgResp.ok) {{
        window._ea_hf_err = 'MSG_ERR:' + msgResp.status;
        window._ea_hf_done = true;
        return;
      }}

      const reader = msgResp.body.getReader();
      const dec = new TextDecoder();
      let accumulated = '';
      while (true) {{
        const {{done, value}} = await reader.read();
        if (done) {{ window._ea_hf_done = true; return; }}
        const lines = dec.decode(value).split('\\n');
        for (const line of lines) {{
          if (line.startsWith('data: ')) {{
            try {{
              const d = JSON.parse(line.slice(6));
              if (d.type === 'stream' && d.token?.text) {{
                const chunk = d.token.text;
                accumulated += chunk;
                window._ea_hf_buf.push(chunk);
              }}
              if (d.type === 'finalAnswer') {{
                window._ea_hf_result = d.text || accumulated;
              }}
            }} catch(e) {{}}
          }}
        }}
      }}
    }} catch(e) {{
      window._ea_hf_err = 'JS_ERR:' + e.message;
      window._ea_hf_done = true;
    }}
  }})();

  return 'started';
}})()
"""

_HF_STREAM_POLL_JS = (
    "JSON.stringify({"
    "c:window._ea_hf_buf.splice(0),"
    "d:window._ea_hf_done,"
    "e:window._ea_hf_err})"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _messages_to_prompt(messages: list[dict]) -> str:
    """Flatten chat messages into a single HF-compatible prompt string."""
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


class HuggingFaceCDPBridge(LLMBridge):
    """
    HuggingFace Chat web bridge via Chrome DevTools Protocol.

    Drives a Chrome instance that has huggingface.co/chat open (must be logged in).
    All HTTP calls are made inside the page context via Runtime.evaluate +
    fetch(), so they carry the browser's cookies and bypass bot-detection.

    Chrome launch command:
        chrome.exe --remote-debugging-port=9228 --remote-allow-origins=*
    """

    provider = "huggingface-cdp"
    default_model = "meta-llama/Llama-3.1-70B-Instruct"
    models = [
        "meta-llama/Llama-3.1-70B-Instruct",
        "meta-llama/Llama-3.2-3B-Instruct",
        "Qwen/Qwen2.5-72B-Instruct",
        "mistralai/Mistral-7B-Instruct-v0.3",
        "CohereForAI/c4ai-command-r-plus-08-2024",
    ]

    def is_available(self) -> bool:
        """True if Chrome CDP port is open AND a huggingface.co/chat tab exists."""
        port = _cdp_port()
        if not _port_open(port):
            return False
        try:
            _get_hf_tab_ws(port)
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
            ws_url = _get_hf_tab_ws(port)
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
            js = _HF_CHAT_JS_TPL.format(
                model_json=json.dumps(model),
                prompt_json=json.dumps(prompt),
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
                ("CREATE_ERR:", "MSG_ERR:", "NO_CONV_ID", "JS_ERR:")
            ):
                return LLMResult(
                    ok=False,
                    text="",
                    error=val,
                    timing_s=round(time.time() - t0, 2),
                    provider=self.provider,
                    model=model,
                )
            if not val or val.strip() == "None":
                return LLMResult(
                    ok=False,
                    text="",
                    error="Empty response from HuggingFace Chat",
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
        Stream HuggingFace Chat response chunks via CDP polling.
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
            ws_url = _get_hf_tab_ws(port)
        except Exception as e:
            raise RuntimeError(f"CDP tab discovery failed: {e}") from e

        ws = _cdp_session(ws_url, port)
        try:
            start_js = _HF_STREAM_START_JS_TPL.format(
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
                    {"expression": _HF_STREAM_POLL_JS, "returnByValue": True},
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
                        raise RuntimeError(f"HuggingFace stream error: {err}")
                    return

                time.sleep(0.1)

            raise RuntimeError("HuggingFace Chat stream timed out after 180s")

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

    bridge = HuggingFaceCDPBridge()
    port = _cdp_port()
    print(f"[huggingface-cdp] checking port {port} …")
    available = bridge.is_available()
    print(f"[huggingface-cdp] is_available = {available}")

    if not available:
        print(
            f"[huggingface-cdp] Chrome not found on port {port} with huggingface.co/chat tab.\n"
            f"  Start Chrome with:\n"
            f"  chrome.exe --remote-debugging-port={port} --remote-allow-origins=* "
            f"https://huggingface.co/chat"
        )
        sys.exit(1)

    prompt = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "Reply with exactly: HF_CDP_OK"
    model = bridge.default_model
    print(f"[huggingface-cdp] model={model}  prompt={prompt!r}")
    result = bridge.simple(prompt, model=model)
    print(f"[huggingface-cdp] ok={result.ok}  time={result.timing_s}s")
    if result.ok:
        print(f"[huggingface-cdp] response:\n{result.text}")
    else:
        print(f"[huggingface-cdp] error: {result.error}", file=sys.stderr)
    sys.exit(0 if result.ok else 1)
