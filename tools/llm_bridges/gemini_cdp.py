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
(async function() {{
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
    // contenteditable — use textContent/replaceChildren, not innerHTML:
    // gemini.google.com enforces a Trusted Types CSP that throws on any
    // innerHTML assignment ("This document requires 'TrustedHTML' assignment").
    el.textContent = '';
    el.dispatchEvent(new Event('input', {{bubbles: true}}));
  }}

  // Set content via execCommand (works for contenteditable)
  if (document.execCommand) {{
    document.execCommand('selectAll', false, null);
    document.execCommand('delete', false, null);
    if (el.tagName === 'TEXTAREA') {{
      document.execCommand('insertText', false, {prompt_json});
    }} else {{
      // Quill (the rich-textarea's contenteditable) reconciles the DOM
      // asynchronously via a MutationObserver. A single insertText call
      // whose string contains literal newlines produces a DOM shape Quill
      // doesn't recognize, and its reconciliation pass corrupts or drops
      // content around/after the newlines. Inserting line-by-line and using
      // insertParagraph for line breaks — the same native action a real
      // Enter keypress triggers — keeps every step in a DOM shape Quill
      // already knows how to reconcile.
      //
      // A real multi-paragraph prompt (~25 lines) still gets corrupted with
      // NO yield between steps: verified live that a same-tick synchronous
      // burst leaves all 25 <p> elements in the DOM but wipes the text out
      // of all but the first one 0.3s later (Quill's MutationObserver
      // appears to only fully absorb a small batch of mutations before its
      // reconciliation "corrects" the rest back out). A 2-3 line toy case
      // does NOT reproduce this — don't trust a fix against a toy case here.
      //
      // A setTimeout-based delay between steps *does* prevent the
      // corruption, but setTimeout is a macrotask and Chrome heavily
      // throttles macrotasks on background/inactive tabs — verified live
      // that delays nominally totalling ~1s inflated to 3.5s+ and could
      // blow past the caller's CDP wait timeout entirely on a real prompt.
      // MutationObserver callbacks are delivered as microtasks, not
      // macrotasks, so yielding via `await Promise.resolve()` gives Quill's
      // observer a chance to run between steps WITHOUT going through the
      // throttled timer queue at all. Verified live: the same 25-line
      // prompt stays fully intact (immediate length == length read back
      // 1.3s later) with microtask yields, taking ~6s total — no timeout
      // risk. Two chained yields per step for margin; do not drop below one
      // without re-verifying against a real, ~800+ char, 20+ line prompt on
      // a fresh reload (not a short toy string).
      const lines = {prompt_json}.split('\\n');
      for (let i = 0; i < lines.length; i++) {{
        if (lines[i].length > 0) {{
          document.execCommand('insertText', false, lines[i]);
          await Promise.resolve(); await Promise.resolve();
        }}
        if (i < lines.length - 1) {{
          document.execCommand('insertParagraph', false, null);
          await Promise.resolve(); await Promise.resolve();
        }}
      }}
    }}
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

# Check if Gemini is still generating (streaming indicator present).
# NOTE: two heuristics were tried here and both false-positived permanently
# on the current UI, live-tested 2026-07:
#   1. `[class*="loading|thinking|spinner"]` scanned across the whole page —
#      matched unrelated persistent feature-flag classes on <body> and the
#      logo chip (e.g. `enable-lm-loading-animation`, `thinking-level-enabled`).
#   2. A visible "Stop response" button — Gemini leaves this button visible
#      for a while *after* a response has already fully completed, so its
#      presence does not mean generation is still in progress.
# Both made this return 'true' forever, so _send_prompt_and_wait's stability
# loop could never terminate on the fast path — it only ever "succeeded" by
# exhausting the full poll timeout and falling back to its partial-text
# return. This function is now deliberately conservative: only the specific,
# purpose-built indicators below (not scanned/wildcarded) count as a real
# signal, and _send_prompt_and_wait treats text-stability as authoritative
# rather than requiring this to be false. See its comment for detail.
_IS_GENERATING_JS = """
(function() {
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


def _new_conversation(ws, wait: float = 20) -> bool:
    """
    Navigate the tab to a fresh, empty Gemini conversation.

    Without this, every call (across every caller sharing the tab -- the
    live daemon's own per-candidate cycle AND any standalone script) keeps
    appending to whatever conversation happens to already be open, forever.
    Verified live 2026-07: once a thread accumulates several turns, Gemini's
    per-turn generation latency grows enough that _send_prompt_and_wait's
    own fixed `timeout` (240s) is no longer enough -- calls report
    "No response within {timeout}s" even though Gemini eventually does
    answer (confirmed by reading the DOM afterwards: the response was there,
    just later than the poll deadline). This reproduced with a trivial
    unrelated one-word prompt, not just long ones, so thread length -- not
    prompt content -- is what was driving it. Starting every call on a
    bare "/app" (no conversation id) gives each call a clean, short thread
    and keeps latency bounded and predictable.
    """
    _send(ws, "Page.navigate", {"url": "https://gemini.google.com/app"}, wait=10)
    deadline = time.time() + wait
    while time.time() < deadline:
        if _js(ws, _FIND_INPUT_JS, wait=3):
            return True
        time.sleep(0.5)
    return False


def _send_prompt_and_wait(
    ws,
    prompt: str,
    timeout: int = 240,
) -> tuple[bool, str]:
    """
    Inject prompt into the Gemini textarea, click send, and wait for the response.
    Returns (ok, text_or_error).
    """
    # 0. Start clean -- see _new_conversation's docstring for why this is
    # not optional (unbounded thread growth silently pushes real latency
    # past this function's own timeout below).
    if not _new_conversation(ws):
        return False, "Could not start a fresh Gemini conversation (navigation timed out)"

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
    set_result, set_exc = _js_async(ws, set_js, wait=20)
    if set_exc:
        return False, f"Error setting input text: {set_exc}"
    if not set_result.startswith("ok:"):
        return False, f"Could not set input text: {set_result}"
    inserted_len_str = set_result.split(":", 1)[1]
    inserted_len = int(inserted_len_str) if inserted_len_str.isdigit() else 0
    if inserted_len == 0 and len(prompt) > 0:
        # execCommand('insertText', ...) silently no-ops when the page is stuck
        # (e.g. still believes a prior response is generating). Fail fast here
        # instead of clicking send on an empty box and burning the full poll
        # timeout waiting for a response that was never actually requested.
        return False, (
            "Input box empty after insert — Gemini tab may be stuck "
            "(reload gemini.google.com and retry)"
        )

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

        # _IS_GENERATING_JS is a soft signal only (see its comment — the
        # available DOM indicators have repeatedly false-positived "still
        # generating" well after a response actually finished). Text that
        # stops changing across several polls is the reliable signal that
        # generation is done, so stability alone drives success; a specific
        # generating indicator just resets the counter so we don't declare
        # victory mid-stream on a coincidental pause.
        generating = _js(ws, _IS_GENERATING_JS, wait=3) == "true"

        if text == last_text and not generating:
            stable_count += 1
            if stable_count >= 3:
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
            set_result, set_exc = _js_async(ws, set_js, wait=20)
            if set_exc:
                raise RuntimeError(f"Error setting input text: {set_exc}")
            if not set_result.startswith("ok:"):
                raise RuntimeError(f"Could not set input text: {set_result}")
            inserted_len_str = set_result.split(":", 1)[1]
            inserted_len = int(inserted_len_str) if inserted_len_str.isdigit() else 0
            if inserted_len == 0 and len(prompt) > 0:
                raise RuntimeError(
                    "Input box empty after insert — Gemini tab may be stuck "
                    "(reload gemini.google.com and retry)"
                )

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

                # Check for completion (see _IS_GENERATING_JS comment — its
                # DOM indicators are a soft signal only; text-stability drives
                # the actual completion decision).
                generating = _js(ws, _IS_GENERATING_JS, wait=3) == "true"
                if text == last_text and not generating:
                    stable_count += 1
                    if stable_count >= 3:
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
