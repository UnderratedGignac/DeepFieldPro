"""
Kimi (Moonshot AI) web bridge via Chrome DevTools Protocol (CDP).

Architecture:
    Drives the Kimi web UI in a CDP-connected Chrome tab.  Uses DOM automation
    (execCommand + click) to send messages and polls the DOM for the assistant
    response — the same path the real Kimi frontend uses internally (gRPC-Web,
    not accessible as plain JSON REST from a same-origin fetch).

    Chrome must be launched with:
        chrome.exe --remote-debugging-port=9232 --remote-allow-origins=*
                   https://www.kimi.com/?chat_enter_method=new_chat

Usage:
    from tools.llm_bridges.kimi_cdp import KimiCDPBridge

    bridge = KimiCDPBridge()
    if bridge.is_available():
        result = bridge.simple("Explain the Dixon-Coles model in one paragraph.")
        print(result.text)
"""

from __future__ import annotations

import json
import os
import socket
import sys
import time
import urllib.request
from pathlib import Path
from typing import Iterator

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from tools.llm_bridges.base import LLMBridge, LLMResult

_DEFAULT_PORT = 9232

# ── CDP helpers ────────────────────────────────────────────────────────────────

def _cdp_port() -> int:
    return int(os.environ.get("KIMI_CDP_PORT", _DEFAULT_PORT))


def _port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        try:
            s.connect(("localhost", port))
            return True
        except OSError:
            return False


def _get_kimi_tab_ws(port: int) -> str:
    raw = urllib.request.urlopen(f"http://localhost:{port}/json", timeout=5).read()
    targets = json.loads(raw)
    for t in targets:
        url = t.get("url", "")
        if ("kimi.com" in url or "moonshot.cn" in url) and t.get("type") == "page":
            return t["webSocketDebuggerUrl"]
    for t in targets:
        if "kimi.com" in t.get("url", "") or "moonshot.cn" in t.get("url", ""):
            return t["webSocketDebuggerUrl"]
    available = [t.get("url", "") for t in targets]
    raise RuntimeError(
        f"No kimi.com tab found in CDP targets on port {port}. "
        f"Open tabs: {available}"
    )


def _cdp_session(ws_url: str, port: int):
    import websocket
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
            "timeout": 90000,
        },
        wait=wait,
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


# ── Message preparation ────────────────────────────────────────────────────────

def _messages_to_prompt(messages: list[dict]) -> str:
    """
    Flatten OpenAI-style messages into a single text prompt suitable for Kimi's UI.
    System messages become a prefixed header; alternating user/assistant turns are
    formatted as a readable transcript.
    """
    parts = []
    system = next((m["content"] for m in messages if m.get("role") == "system"), None)
    if system:
        parts.append(f"[SYSTEM CONTEXT]\n{system}\n[/SYSTEM CONTEXT]\n")

    non_system = [m for m in messages if m.get("role") != "system"]
    if len(non_system) == 1 and non_system[0].get("role") == "user":
        # Single user message — send as-is (most common case)
        if system:
            parts.append(non_system[0]["content"])
        else:
            return non_system[0]["content"]
    else:
        for m in non_system:
            role = m.get("role", "user")
            prefix = "User" if role == "user" else "Assistant"
            parts.append(f"{prefix}: {m['content']}")

    return "\n\n".join(parts)


# ── DOM automation ─────────────────────────────────────────────────────────────

_TYPE_INTO_CURRENT_JS = """
(async () => {{
  const TEXT = {text_json};

  const findInput = () => {{
    for (const sel of ['div.chat-input-editor', 'div[contenteditable="true"]', 'textarea']) {{
      const el = document.querySelector(sel);
      if (el && el.offsetWidth > 0) return el;
    }}
    return null;
  }};

  let inp = null;
  for (let i = 0; i < 10; i++) {{
    inp = findInput();
    if (inp) break;
    await new Promise(r => setTimeout(r, 300));
  }}
  if (!inp) return JSON.stringify({{error: 'input_not_found'}});

  inp.focus();
  document.execCommand('selectAll');
  document.execCommand('insertText', false, TEXT);
  await new Promise(r => setTimeout(r, 150));

  const countAssistant = () => document.querySelectorAll('.segment.segment-assistant, .chat-content-item-assistant').length;
  const beforeCount = countAssistant();

  let sent = false;
  for (const sel of ['.send-button-container', 'button[type="submit"]']) {{
    const btn = document.querySelector(sel);
    if (btn && btn.offsetWidth > 0) {{ btn.click(); sent = true; break; }}
  }}
  if (!sent) {{
    inp.dispatchEvent(new KeyboardEvent('keydown', {{key:'Enter',code:'Enter',keyCode:13,bubbles:true}}));
    inp.dispatchEvent(new KeyboardEvent('keyup',   {{key:'Enter',code:'Enter',keyCode:13,bubbles:true}}));
  }}

  return JSON.stringify({{ok: true, beforeCount}});
}})()
"""


# ── Public bridge class ────────────────────────────────────────────────────────

class KimiCDPBridge(LLMBridge):
    """
    Kimi (Moonshot AI) web bridge via Chrome DevTools Protocol.

    Drives the Kimi web UI in a Chrome tab using DOM automation.
    Chrome must be launched with:
        chrome.exe --remote-debugging-port=9232 --remote-allow-origins=* https://www.kimi.com
    """

    provider = "kimi-cdp"
    default_model = "kimi-latest"
    models = [
        "kimi-latest",
        "kimi-k2-0711-preview",
        "moonshot-v1-auto",
        "moonshot-v1-8k",
        "moonshot-v1-32k",
        "moonshot-v1-128k",
    ]

    def is_available(self) -> bool:
        port = _cdp_port()
        if not _port_open(port):
            return False
        try:
            _get_kimi_tab_ws(port)
            return True
        except Exception:
            return False

    def _navigate_and_wait(self, ws, url: str, timeout: float = 15.0) -> None:
        """Navigate via CDP Page.navigate and wait for DOMContentLoaded."""
        _send(ws, "Page.enable", {}, wait=5)
        _send(ws, "Page.navigate", {"url": url}, wait=10)
        # Poll until the input element appears (up to timeout seconds)
        CHECK_INPUT = (
            "(function(){"
            "const el=document.querySelector('div.chat-input-editor,div[contenteditable=\"true\"],textarea');"
            "return (el&&el.offsetWidth>0)?'ready':'waiting';"
            "})()"
        )
        deadline = time.time() + timeout
        while time.time() < deadline:
            r = _js_sync(ws, CHECK_INPUT, wait=3)
            if r == "ready":
                return
            time.sleep(0.5)
        # Not found but continue — the type JS will report the error

    def chat(self, messages: list[dict], model: str = "") -> LLMResult:
        model = model or self.default_model
        t0 = time.time()
        port = _cdp_port()

        if not _port_open(port):
            return LLMResult(
                ok=False, text="",
                error=f"Chrome CDP port {port} not open — launch with: "
                      f"python tools/launch_cdp.py kimi",
                provider=self.provider, model=model,
            )

        try:
            ws_url = _get_kimi_tab_ws(port)
        except Exception as e:
            return LLMResult(ok=False, text="", error=str(e),
                             timing_s=round(time.time()-t0, 2),
                             provider=self.provider, model=model)

        try:
            import websocket  # noqa
        except ImportError:
            return LLMResult(ok=False, text="",
                             error="pip install websocket-client",
                             provider=self.provider, model=model)

        ws = None
        try:
            ws = _cdp_session(ws_url, port)
            prompt = _messages_to_prompt(messages)

            # Count existing assistant messages BEFORE sending (no navigation —
            # see stream() docstring for why we avoid Page.navigate here)
            COUNT_JS = "document.querySelectorAll('.segment.segment-assistant,.chat-content-item-assistant').length"
            before_str = _js_sync(ws, COUNT_JS, wait=5)
            before_count = int(before_str) if before_str.isdigit() else 0

            # Type and send via DOM on the currently open chat
            type_js = _TYPE_INTO_CURRENT_JS.format(text_json=json.dumps(prompt))
            type_val, type_exc = _js_async(ws, type_js, wait=15)
            if type_exc:
                return LLMResult(ok=False, text="",
                                 error=f"type/send JS error: {type_exc[:200]}",
                                 timing_s=round(time.time()-t0, 2),
                                 provider=self.provider, model=model)
            try:
                type_data = json.loads(type_val)
                if "error" in type_data:
                    return LLMResult(ok=False, text="",
                                     error=f"type/send: {type_data['error']}",
                                     timing_s=round(time.time()-t0, 2),
                                     provider=self.provider, model=model)
            except Exception:
                pass

            # Poll DOM for response; exit on text stability (no loading indicator —
            # Kimi class names can persist after streaming ends).
            POLL_JS = (
                f"(function(){{"
                f"const segs=document.querySelectorAll('.segment.segment-assistant,.chat-content-item-assistant');"
                f"if(segs.length<={before_count})return JSON.stringify({{waiting:true}});"
                f"const el=segs[segs.length-1];"
                f"const txt=(el.innerText||el.textContent||'').trim();"
                f"return JSON.stringify({{text:txt}});"
                f"}})()"
            )

            deadline = time.time() + 120
            last_text = ""
            stable_rounds = 0

            while time.time() < deadline:
                pr = _send(ws, "Runtime.evaluate",
                           {"expression": POLL_JS, "returnByValue": True}, wait=5)
                raw = pr.get("result", {}).get("value") or '{"waiting":true}'
                try:
                    data = json.loads(raw)
                except Exception:
                    data = {"waiting": True}

                if data.get("waiting"):
                    time.sleep(0.3)
                    continue

                text = data.get("text", "")

                if text == last_text and len(text) > 0:
                    stable_rounds += 1
                    if stable_rounds >= 5:
                        return LLMResult(ok=True, text=text,
                                         timing_s=round(time.time()-t0, 2),
                                         provider=self.provider, model=model)
                else:
                    stable_rounds = 0
                last_text = text
                time.sleep(0.3)

            # Return whatever we have
            if last_text:
                return LLMResult(ok=True, text=last_text,
                                 timing_s=round(time.time()-t0, 2),
                                 provider=self.provider, model=model)
            return LLMResult(ok=False, text="",
                             error="Timed out waiting for Kimi response",
                             timing_s=round(time.time()-t0, 2),
                             provider=self.provider, model=model)

        except Exception as e:
            return LLMResult(ok=False, text="", error=str(e),
                             timing_s=round(time.time()-t0, 2),
                             provider=self.provider, model=model)
        finally:
            if ws:
                try: ws.close()
                except Exception: pass

    def stream(self, messages: list[dict], model: str = "") -> Iterator[str]:
        """
        Stream the Kimi response as DOM text deltas (polled every 300ms).
        Yields new characters as they appear; stops when text stabilizes.

        Uses the existing kimi.com tab without navigating away — navigation would
        flush the CDP event buffer and confuse message-ID matching.  Each call
        appends a message to the current conversation.
        """
        model = model or self.default_model
        port = _cdp_port()

        if not _port_open(port):
            raise RuntimeError(
                f"Chrome CDP port {port} not open — launch with: "
                f"python tools/launch_cdp.py kimi"
            )

        try:
            ws_url = _get_kimi_tab_ws(port)
        except Exception as e:
            raise RuntimeError(f"CDP tab discovery failed: {e}") from e

        ws = _cdp_session(ws_url, port)
        try:
            prompt = _messages_to_prompt(messages)

            # Count existing assistant messages BEFORE sending (no navigation)
            COUNT_JS = "document.querySelectorAll('.segment.segment-assistant,.chat-content-item-assistant').length"
            before_str = _js_sync(ws, COUNT_JS, wait=5)
            before_count = int(before_str) if before_str.isdigit() else 0

            # Type and click send via DOM on the currently open chat
            type_js = _TYPE_INTO_CURRENT_JS.format(text_json=json.dumps(prompt))
            _js_async(ws, type_js, wait=15)

            # Poll DOM for response.  Exit purely on text stability (no loading
            # indicator — Kimi class names can persist after streaming ends).
            POLL_JS = (
                f"(function(){{"
                f"const segs=document.querySelectorAll('.segment.segment-assistant,.chat-content-item-assistant');"
                f"if(segs.length<={before_count})return JSON.stringify({{waiting:true}});"
                f"const el=segs[segs.length-1];"
                f"const txt=(el.innerText||el.textContent||'').trim();"
                f"return JSON.stringify({{text:txt}});"
                f"}})()"
            )

            yielded_len = 0
            last_text = ""
            stable_rounds = 0
            deadline = time.time() + 120

            while time.time() < deadline:
                pr = _send(ws, "Runtime.evaluate",
                           {"expression": POLL_JS, "returnByValue": True}, wait=5)
                raw = pr.get("result", {}).get("value") or '{"waiting":true}'
                try:
                    data = json.loads(raw)
                except Exception:
                    data = {"waiting": True}

                if data.get("waiting"):
                    time.sleep(0.3)
                    continue

                text = data.get("text", "")

                if len(text) > yielded_len:
                    yield text[yielded_len:]
                    yielded_len = len(text)

                # Exit when text hasn't changed for 5 consecutive polls (~1.5s)
                if text == last_text and len(text) > 0:
                    stable_rounds += 1
                    if stable_rounds >= 5:
                        return
                else:
                    stable_rounds = 0
                last_text = text
                time.sleep(0.3)

            raise RuntimeError("Kimi stream timed out after 120s")

        finally:
            try:
                ws.close()
            except Exception:
                pass


# ── Smoke test ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    bridge = KimiCDPBridge()
    port = _cdp_port()
    print(f"[kimi-cdp] checking port {port} ...")
    available = bridge.is_available()
    print(f"[kimi-cdp] is_available = {available}")

    if not available:
        print(
            f"[kimi-cdp] Chrome not found on port {port} with kimi.com tab.\n"
            f"  Start Chrome with:\n"
            f"    python tools/launch_cdp.py kimi\n"
            f"  Then log in to kimi.com and re-run this test."
        )
        sys.exit(1)

    prompt = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "Reply with exactly: KIMI_CDP_OK"
    print(f"[kimi-cdp] sending: {prompt!r}")
    print("[kimi-cdp] streaming response:")
    try:
        for chunk in bridge.stream([{"role": "user", "content": prompt}]):
            print(chunk, end="", flush=True)
        print()
        print("[kimi-cdp] stream OK")
    except Exception as e:
        print(f"\n[kimi-cdp] error: {e}", file=sys.stderr)
        sys.exit(1)
