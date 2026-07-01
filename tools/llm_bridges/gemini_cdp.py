"""
Gemini web bridge via Chrome DevTools Protocol (CDP).

# NOTE: This bridge works best with Gemini open in Chrome at port 9225.
# Requires: Chrome running at --remote-debugging-port=9225 with gemini.google.com open
# Env vars: GEMINI_CDP_PORT (default 9225)

Architecture:
    Primary path — in-page JS injection:
        Finds the Gemini chat textarea in the DOM, injects the prompt, triggers
        the send button, then polls the response container for stable text.
        This is the most reliable approach because Gemini's internal API uses
        complex protobuf-over-HTTP/2 that changes frequently.

    The bridge connects to a running Chrome instance via CDP, locates the
    gemini.google.com tab, and drives it entirely through Runtime.evaluate
    JavaScript calls — no external HTTP requests, no API keys needed.

    Chrome must be launched with:
        chrome.exe --remote-debugging-port=9225 --remote-allow-origins=*

Usage:
    from tools.llm_bridges.gemini_cdp import GeminiCDPBridge

    bridge = GeminiCDPBridge()
    if bridge.is_available():
        result = bridge.simple("Explain the Dixon-Coles football model.")
        print(result.text)

Notes:
    - The user must be logged into Google in Chrome at port 9225.
    - Gemini's DOM selectors can change between deployments. If the bridge
      stops working, inspect the page and update _INPUT_SELECTORS / _RESPONSE_SEL.
    - stream() yields chunks by polling the DOM as text accumulates.
    - For production use-cases with an API key, prefer the direct Gemini API
      (tools/openrouter_worker.py or a direct google-generativeai call) — this
      bridge is a fallback for when no key is available.
"""

from __future__ import annotations

import json
import os
import socket
import time
import urllib.request
from typing import Iterator

from tools.llm_bridges.base import LLMBridge, LLMResult

_DEFAULT_PORT = 9225

# DOM selectors — verified against gemini.google.com as of mid-2025.
# Gemini uses a `rich-textarea` web component wrapping a contenteditable div.
# Update these if the page structure changes.
_INPUT_SELECTORS = [
    "rich-textarea .ql-editor",        # Quill-based rich text editor (most common)
    "rich-textarea div[contenteditable='true']",
    "div.ql-editor[contenteditable='true']",
    "textarea[placeholder]",           # fallback for older Gemini UI
]

# Response container — Gemini renders model output in a model-response element
_RESPONSE_SELECTORS = [
    "model-response .markdown",
    "model-response",
    "[data-response-index] .response-content",
    ".response-content",
    "message-content",
]

# Send button selectors
_SEND_BUTTON_SELECTORS = [
    "button[aria-label='Send message']",
    "button[data-test-id='send-button']",
    "button.send-button",
    "mat-icon[fonticon='send']",        # Material icon send button
]


def _cdp_port() -> int:
    return int(os.environ.get("GEMINI_CDP_PORT", _DEFAULT_PORT))


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


def _get_gemini_tab_ws(port: int) -> str:
    """Return the WebSocket debugger URL for the gemini.google.com tab."""
    raw = urllib.request.urlopen(f"http://localhost:{port}/json", timeout=5).read()
    targets = json.loads(raw)
    for t in targets:
        url = t.get("url", "")
        if "gemini.google.com" in url and t.get("type") == "page":
            return t["webSocketDebuggerUrl"]
    # Fallback: any target matching
    for t in targets:
        if "gemini.google.com" in t.get("url", ""):
            return t["webSocketDebuggerUrl"]
    available = [t.get("url", "") for t in targets]
    raise RuntimeError(
        f"No gemini.google.com tab found in CDP targets on port {port}. "
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


def _js(ws, expression: str, wait: float = 10) -> str:
    """Evaluate synchronous JS and return string value."""
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
    """Evaluate async JS (awaitPromise=True). Returns (value_str, exception_or_None)."""
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
# DOM interaction helpers
# ---------------------------------------------------------------------------

_FIND_INPUT_JS = """
(function() {
  const selectors = """ + json.dumps(_INPUT_SELECTORS) + """;
  for (const sel of selectors) {
    const el = document.querySelector(sel);
    if (el) return sel;
  }
  // Try custom elements (rich-textarea shadow DOM)
  const rt = document.querySelector('rich-textarea');
  if (rt && rt.shadowRoot) {
    const inner = rt.shadowRoot.querySelector('[contenteditable]');
    if (inner) return '__shadow_rt';
  }
  return '';
})()
"""

_SET_INPUT_JS_TPL = """
(function() {{
  const selectors = {selectors_json};
  let el = null;
  for (const sel of selectors) {{
    el = document.querySelector(sel);
    if (el) break;
  }}

  // Also check rich-textarea shadow DOM
  if (!el) {{
    const rt = document.querySelector('rich-textarea');
    if (rt && rt.shadowRoot) {{
      el = rt.shadowRoot.querySelector('[contenteditable]');
    }}
  }}

  if (!el) return 'NO_INPUT';

  // Focus the element
  el.focus();

  // Clear existing content
  if (el.tagName === 'TEXTAREA') {{
    el.value = '';
    el.dispatchEvent(new Event('input', {{bubbles: true}}));
  }} else {{
    // contenteditable
    el.innerHTML = '';
    el.dispatchEvent(new Event('input', {{bubbles: true}}));
  }}

  // Set content via execCommand (works for contenteditable)
  if (document.execCommand) {{
    document.execCommand('selectAll', false, null);
    document.execCommand('delete', false, null);
    document.execCommand('insertText', false, {prompt_json});
  }} else if (el.tagName === 'TEXTAREA') {{
    el.value = {prompt_json};
    el.dispatchEvent(new Event('input', {{bubbles: true}}));
    el.dispatchEvent(new Event('change', {{bubbles: true}}));
  }} else {{
    el.textContent = {prompt_json};
    el.dispatchEvent(new InputEvent('input', {{
      bubbles: true, cancelable: true,
      inputType: 'insertText', data: {prompt_json}
    }}));
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

  // Fallback: look for any visible button near the input area
  const btns = document.querySelectorAll('button');
  for (const btn of btns) {
    const r = btn.getBoundingClientRect();
    if (r.width === 0 || r.height === 0) continue;
    const aria = (btn.getAttribute('aria-label') || '').toLowerCase();
    const title = (btn.getAttribute('title') || '').toLowerCase();
    const text = (btn.innerText || '').trim().toLowerCase();
    if (aria.includes('send') || title.includes('send') || text === 'send') {
      btn.dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true, view: window}));
      return 'clicked:fallback';
    }
  }

  // Last resort: Enter key on the active element
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

_READ_RESPONSE_JS = """
(function() {
  const selectors = """ + json.dumps(_RESPONSE_SELECTORS) + """;
  // Find the LAST response element (most recent)
  let lastEl = null;
  for (const sel of selectors) {
    const els = document.querySelectorAll(sel);
    if (els.length > 0) {
      lastEl = els[els.length - 1];
      break;
    }
  }
  if (!lastEl) return '';
  return (lastEl.innerText || lastEl.textContent || '').trim();
})()
"""

# Check if Gemini is still generating (streaming indicator present)
_IS_GENERATING_JS = """
(function() {
  // Look for common streaming/thinking indicators
  const indicators = [
    '.loading-indicator',
    '[aria-label="Gemini is thinking"]',
    '[aria-label*="thinking"]',
    '[aria-label*="generating"]',
    '.response-generating',
    'pendingMessage',
    '[data-is-generating="true"]',
  ];
  for (const sel of indicators) {
    if (document.querySelector(sel)) return 'true';
  }
  // Check for animated elements
  const animated = document.querySelector('[class*="loading"], [class*="thinking"], [class*="spinner"]');
  if (animated) {
    const r = animated.getBoundingClientRect();
    if (r.width > 0 && r.height > 0) return 'true';
  }
  return 'false';
})()
"""

# Count of response elements — used to detect when a new response appears
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


# ---------------------------------------------------------------------------
# Core send-and-wait logic
# ---------------------------------------------------------------------------


def _send_prompt_and_wait(
    ws,
    prompt: str,
    timeout: int = 120,
) -> tuple[bool, str]:
    """
    Inject prompt into the Gemini textarea, click send, and wait for the response.
    Returns (ok, text_or_error).
    """
    # 1. Check input is present
    found_sel = _js(ws, _FIND_INPUT_JS)
    if not found_sel:
        return False, "Gemini input element not found — is gemini.google.com loaded?"

    # 2. Count existing responses so we can detect the new one
    prev_count_str = _js(ws, _COUNT_RESPONSES_JS, wait=5)
    prev_count = int(prev_count_str) if prev_count_str.isdigit() else 0

    # 3. Inject the prompt text
    set_js = _SET_INPUT_JS_TPL.format(
        selectors_json=json.dumps(_INPUT_SELECTORS),
        prompt_json=json.dumps(prompt),
    )
    set_result = _js(ws, set_js, wait=10)
    if not set_result.startswith("ok:"):
        return False, f"Could not set input text: {set_result}"

    # Brief pause to let React/Angular observe the input change
    time.sleep(0.5)

    # 4. Click send
    click_result = _js(ws, _CLICK_SEND_JS, wait=5)
    if click_result == "NO_SEND_BUTTON":
        # Try Ctrl+Enter as last resort
        _send(
            ws,
            "Input.dispatchKeyEvent",
            {"type": "keyDown", "key": "Enter", "code": "Enter",
             "windowsVirtualKeyCode": 13, "nativeVirtualKeyCode": 13, "modifiers": 2},
        )
        time.sleep(0.1)
        _send(
            ws,
            "Input.dispatchKeyEvent",
            {"type": "keyUp", "key": "Enter", "code": "Enter",
             "windowsVirtualKeyCode": 13, "nativeVirtualKeyCode": 13, "modifiers": 2},
        )

    time.sleep(1.0)  # let the request fire

    # 5. Poll for response
    deadline = time.time() + timeout
    last_text = ""
    stable_count = 0
    new_response_seen = False

    while time.time() < deadline:
        time.sleep(1.5)

        # Check if a new response element appeared
        cur_count_str = _js(ws, _COUNT_RESPONSES_JS, wait=5)
        cur_count = int(cur_count_str) if cur_count_str.isdigit() else 0
        if cur_count > prev_count:
            new_response_seen = True

        if not new_response_seen:
            continue  # still waiting for Gemini to start responding

        # Read the latest response text
        text = _js(ws, _READ_RESPONSE_JS, wait=5).strip()
        if not text:
            continue

        # Check if still generating
        generating = _js(ws, _IS_GENERATING_JS, wait=3) == "true"

        if text == last_text and not generating:
            stable_count += 1
            if stable_count >= 2:
                return True, text
        else:
            stable_count = 0
            last_text = text

    if last_text:
        # We got partial content — return it
        return True, last_text
    return False, f"No response within {timeout}s"


# ---------------------------------------------------------------------------
# Public bridge class
# ---------------------------------------------------------------------------


class GeminiCDPBridge(LLMBridge):
    """
    Gemini web bridge via Chrome DevTools Protocol.

    Drives a Chrome instance that has gemini.google.com open (must be logged in).
    Injects prompts into the chat textarea, clicks send, and reads the DOM response.

    This is the fallback path — prefer the Gemini API (via NVIDIA NIM / OpenRouter)
    when an API key is available.

    Chrome launch command:
        chrome.exe --remote-debugging-port=9225 --remote-allow-origins=*
    """

    provider = "gemini-cdp"
    default_model = "gemini-2.0-flash"
    models = ["gemini-2.0-flash", "gemini-1.5-pro"]

    # ------------------------------------------------------------------ #
    # LLMBridge interface
    # ------------------------------------------------------------------ #

    def is_available(self) -> bool:
        """True if Chrome is listening on the CDP port and gemini.google.com tab exists."""
        port = _cdp_port()
        if not _port_open(port):
            return False
        try:
            _get_gemini_tab_ws(port)
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
            ws_url = _get_gemini_tab_ws(port)
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
            ok, text = _send_prompt_and_wait(ws, prompt)
            return LLMResult(
                ok=ok,
                text=text if ok else "",
                error="" if ok else text,
                timing_s=round(time.time() - t0, 2),
                provider=self.provider,
                model=model,
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
        Stream Gemini response chunks by polling the DOM as text accumulates.
        Yields str chunks. Raises RuntimeError on failure.

        Note: Gemini's web UI doesn't expose a true SSE stream; this polls the
        response DOM element every ~500ms and yields incremental text diffs.
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
            ws_url = _get_gemini_tab_ws(port)
        except Exception as e:
            raise RuntimeError(f"CDP tab discovery failed: {e}") from e

        ws = _cdp_session(ws_url, port)
        try:
            # Count existing responses
            prev_count_str = _js(ws, _COUNT_RESPONSES_JS, wait=5)
            prev_count = int(prev_count_str) if prev_count_str.isdigit() else 0

            # Inject and send
            set_js = _SET_INPUT_JS_TPL.format(
                selectors_json=json.dumps(_INPUT_SELECTORS),
                prompt_json=json.dumps(prompt),
            )
            set_result = _js(ws, set_js, wait=10)
            if not set_result.startswith("ok:"):
                raise RuntimeError(f"Could not set input text: {set_result}")

            time.sleep(0.5)
            _js(ws, _CLICK_SEND_JS, wait=5)
            time.sleep(1.0)

            # Poll and yield diffs
            deadline = time.time() + 180
            last_text = ""
            new_response_seen = False
            stable_count = 0

            while time.time() < deadline:
                time.sleep(0.5)

                cur_count_str = _js(ws, _COUNT_RESPONSES_JS, wait=5)
                cur_count = int(cur_count_str) if cur_count_str.isdigit() else 0
                if cur_count > prev_count:
                    new_response_seen = True

                if not new_response_seen:
                    continue

                text = _js(ws, _READ_RESPONSE_JS, wait=5).strip()
                if not text:
                    continue

                # Yield new characters
                if len(text) > len(last_text):
                    yield text[len(last_text):]
                    last_text = text

                # Check for completion
                generating = _js(ws, _IS_GENERATING_JS, wait=3) == "true"
                if text == last_text and not generating:
                    stable_count += 1
                    if stable_count >= 2:
                        return
                else:
                    stable_count = 0

            # Timed out — yield whatever we have and return
            if not last_text:
                raise RuntimeError("Gemini stream timed out with no content after 180s")

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

    bridge = GeminiCDPBridge()
    port = _cdp_port()
    print(f"[gemini-cdp] checking port {port} …")
    available = bridge.is_available()
    print(f"[gemini-cdp] is_available = {available}")

    if not available:
        print(
            f"[gemini-cdp] Chrome not found on port {port} with gemini.google.com tab.\n"
            f"  Start Chrome with:\n"
            f"  chrome.exe --remote-debugging-port={port} --remote-allow-origins=* "
            f"https://gemini.google.com"
        )
        sys.exit(1)

    prompt = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else (
        "Reply with exactly: GEMINI_CDP_OK"
    )
    print(f"[gemini-cdp] sending prompt: {prompt!r}")
    result = bridge.simple(prompt)
    print(f"[gemini-cdp] ok={result.ok}  time={result.timing_s}s  model={result.model}")
    if result.ok:
        print(f"[gemini-cdp] response:\n{result.text}")
    else:
        print(f"[gemini-cdp] error: {result.error}", file=sys.stderr)
    sys.exit(0 if result.ok else 1)
