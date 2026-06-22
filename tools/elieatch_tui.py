"""
ElieAtch TUI — Modern Textual UI powered by Qwen CDP bridge.

    python tools/elieatch_tui.py        interactive session
    python tools/elieatch_tui.py "task" one-shot then interactive
"""
from __future__ import annotations
import sys, os, re, time, subprocess, threading
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from textual.app import App, ComposeResult
from textual.widgets import Input, RichLog, Static
from textual.containers import Vertical
from textual import work, on
from textual.message import Message
from rich.text import Text

# ── reuse logic from elieatch.py ──────────────────────────────────────────────
from tools.elieatch import (
    TOOLS, TOOLS_DOC, _SYS, _parse, _strip_preamble,
    KNOWN_MODELS, DEFAULT_MODEL, OBS_LIMIT,
)

VENV_PY = str(_ROOT / ".venv" / "Scripts" / "python.exe")


# ══════════════════════════════════════════════════════════════════════════════
# INTER-THREAD MESSAGES
# ══════════════════════════════════════════════════════════════════════════════

class StreamChunk(Message):
    def __init__(self, text: str) -> None:
        super().__init__(); self.text = text

class ToolCall(Message):
    def __init__(self, tool: str, inp: str) -> None:
        super().__init__(); self.tool = tool; self.inp = inp

class ToolResult(Message):
    def __init__(self, result: str, elapsed: float) -> None:
        super().__init__(); self.result = result; self.elapsed = elapsed

class Stats(Message):
    def __init__(self, tokens: int, elapsed: float) -> None:
        super().__init__(); self.tokens = tokens; self.elapsed = elapsed

class SessionReady(Message):
    def __init__(self, chat_id: str) -> None:
        super().__init__(); self.chat_id = chat_id

class AgentError(Message):
    def __init__(self, error: str) -> None:
        super().__init__(); self.error = error

class AgentDone(Message):
    pass


# ══════════════════════════════════════════════════════════════════════════════
# CSS — deep-space purple theme
# ══════════════════════════════════════════════════════════════════════════════

_CSS = """
Screen {
    background: #080010;
    layers: base;
}

#header-bar {
    dock: top;
    height: 1;
    background: #12002a;
    color: #bf7fff;
    text-style: bold;
    padding: 0 2;
}

#chat-log {
    background: #080010;
    height: 1fr;
    padding: 1 2;
    scrollbar-color: #5b21b6;
    scrollbar-background: #12002a;
    border: solid #1e0040;
    margin: 0 1;
}

#stream-area {
    background: #0d0020;
    color: #e9d5ff;
    border-top: solid #2d0052;
    border-bottom: solid #2d0052;
    padding: 0 4;
    min-height: 2;
    max-height: 14;
    margin: 0 1;
    display: none;
}

#stream-area.active {
    display: block;
}

#input-wrap {
    dock: bottom;
    height: 3;
    background: #080010;
    padding: 0 1;
}

#prompt-input {
    background: #12002a;
    border: tall #5b21b6;
    color: #e9d5ff;
    height: 3;
}

#prompt-input:focus {
    border: tall #a855f7;
}

#footer-bar {
    dock: bottom;
    height: 1;
    background: #080010;
    color: #3d1a66;
    padding: 0 2;
}
"""


# ══════════════════════════════════════════════════════════════════════════════
# APP
# ══════════════════════════════════════════════════════════════════════════════

class ElieAtchApp(App):
    CSS = _CSS

    def __init__(self, first_task: str | None = None) -> None:
        super().__init__()
        self.model        = DEFAULT_MODEL
        self.cwd          = _ROOT
        self._chat_id: str | None = None
        self._turns       = 0
        self._chars       = 0
        self._busy        = False
        self._stream_buf  = ""
        self._interrupt   = threading.Event()
        self._first_task  = first_task
        # widget refs set in on_mount
        self._log: RichLog
        self._stream: Static

    # ── layout ────────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        yield Static("  ⬡  ElieAtch", id="header-bar")
        yield RichLog(id="chat-log", highlight=False, markup=False, wrap=True)
        yield Static("", id="stream-area")
        yield Vertical(
            Input(placeholder="  Type a task or /command…", id="prompt-input"),
            id="input-wrap",
        )
        yield Static(
            "  /help  /model  /clear  /exit  /cwd  /tokens  ·  Ctrl+C quit",
            id="footer-bar",
        )

    def on_mount(self) -> None:
        self._log    = self.query_one("#chat-log",    RichLog)
        self._stream = self.query_one("#stream-area", Static)
        self.query_one("#prompt-input", Input).focus()
        self._log_banner()
        self._init_session()

    # ── startup ───────────────────────────────────────────────────────────────

    def _log_banner(self) -> None:
        log = self._log
        log.write(Text(""))
        t = Text("  ⬡  ", style="#5b21b6")
        t.append("ElieAtch", style="bold #a855f7")
        t.append("  — AI coding agent", style="#6b21a8")
        log.write(t)
        log.write(Text("  Powered by Qwen via CDP bridge", style="#3d1a66"))
        log.write(Text(""))

    @work(thread=True)
    def _init_session(self) -> None:
        from tools.qwen_bridge import new_chat
        try:
            cid = new_chat()
            self.call_from_thread(self.post_message, SessionReady(cid))
        except Exception as e:
            self.call_from_thread(self.post_message, AgentError(f"Session init: {e}"))

    def on_session_ready(self, ev: SessionReady) -> None:
        self._chat_id = ev.chat_id
        t = Text(f"  ✓ ", style="#7c3aed")
        t.append(self.model, style="#c084fc")
        t.append(f"  ·  chat:{ev.chat_id[:10]}…", style="#4b2d8a")
        self._log.write(t)
        self._log.write(Text(""))
        self._update_header()
        if self._first_task:
            self._run_task(self._first_task)
            self._first_task = None

    # ── input ─────────────────────────────────────────────────────────────────

    @on(Input.Submitted, "#prompt-input")
    def on_submitted(self, ev: Input.Submitted) -> None:
        line = ev.value.strip()
        if not line:
            return
        self.query_one(Input).value = ""
        lo = line.lower()

        if lo in ("/exit", "/quit"):
            self.exit(); return

        if lo == "/help":
            self._show_help(); return

        if lo == "/clear":
            self._log.clear(); self._log_banner(); return

        if lo == "/cwd":
            self._info(str(self.cwd)); return

        if lo == "/tokens":
            self._info(f"~{self._chars // 4} tokens this session"); return

        if lo.startswith("/cd"):
            arg = line[3:].strip()
            p = (self.cwd / arg).resolve() if arg else Path.home()
            if p.is_dir():
                self.cwd = p; self._info(f"→ {p}")
            else:
                self._error(f"Not a directory: {p}")
            return

        if lo == "/model" or lo.startswith("/model "):
            arg = line[6:].strip()
            if not arg:
                self._info(f"Model: {self.model}"); return
            if arg == "list":
                lines = "\n".join(
                    f"  {'→' if m == self.model else ' '} {m}" for m in KNOWN_MODELS
                )
                self._info(lines); return
            self.model = arg
            self._update_header()
            self._info(f"model → {arg}"); return

        if line.startswith("!"):
            self._shell_passthrough(line[1:].strip()); return

        if self._busy:
            self._error("Agent busy — wait or restart."); return
        if self._chat_id is None:
            self._error("Session not ready yet."); return

        self._run_task(line)

    # ── agent task ────────────────────────────────────────────────────────────

    def _run_task(self, task: str) -> None:
        self._busy = True
        self._turns += 1
        self._interrupt.clear()
        self.query_one(Input).disabled = True

        # print "You" header
        self._log.write(Text(""))
        t = Text("  You", style="bold #c084fc")
        t.append("  " + "─" * 50, style="#2d0052")
        self._log.write(t)
        self._log.write(Text(f"  {task}", style="#e9d5ff"))
        self._log.write(Text(""))
        t2 = Text("  ElieAtch", style="bold #a855f7")
        t2.append("  " + "─" * 47, style="#2d0052")
        self._log.write(t2)

        # activate streaming area
        self._stream_buf = ""
        self._stream.add_class("active")
        self._stream.update(Text("", style="#e9d5ff"))

        self._agent_work(task)

    @work(thread=True)
    def _agent_work(self, task: str) -> None:
        from tools.qwen_bridge import chat_via_fetch_stream

        try:
            msg = (
                f"{_SYS.format(root=_ROOT, tools=TOOLS_DOC)}\n\nUSER: {task}"
                if self._turns == 1 else f"TASK: {task}"
            )

            t_start = time.time()

            def _stream_fn(m: str):
                return _strip_preamble(
                    chat_via_fetch_stream(m, timeout=90, model=self.model, chat_id=self._chat_id)
                )

            def _collect(gen) -> str:
                buf = ""; chunk_buf = ""
                for chunk in gen:
                    if self._interrupt.is_set():
                        break
                    buf += chunk; chunk_buf += chunk
                    if len(chunk_buf) >= 15 or "\n" in chunk_buf:
                        self.call_from_thread(self.post_message, StreamChunk(chunk_buf))
                        chunk_buf = ""
                if chunk_buf:
                    self.call_from_thread(self.post_message, StreamChunk(chunk_buf))
                return buf

            text = _collect(_stream_fn(msg))
            self._chars += len(text)

            for _ in range(30):
                if self._interrupt.is_set():
                    break
                parsed = _parse(text)

                if parsed[0] in ('chat', 'final'):
                    elapsed = time.time() - t_start
                    self.call_from_thread(self.post_message, Stats(self._chars // 4, elapsed))
                    break

                if parsed[0] == 'action':
                    _, tool_name, inp = parsed
                    self.call_from_thread(self.post_message, ToolCall(tool_name, inp))
                    t0 = time.time()
                    fn = TOOLS.get(tool_name)
                    if fn is None:
                        obs = f"Error: unknown tool '{tool_name}'"
                    else:
                        try:
                            obs = fn(inp, cwd=self.cwd, session=None)
                        except Exception as e:
                            obs = f"Error: {e}"
                    self.call_from_thread(self.post_message, ToolResult(obs, time.time() - t0))
                    # reset stream buffer for next response
                    self.call_from_thread(self._reset_stream)
                    text = _collect(_stream_fn(f"Observation: {obs}"))
                    self._chars += len(text)

            self.call_from_thread(self.post_message, AgentDone())

        except Exception as e:
            self.call_from_thread(self.post_message, AgentError(str(e)))

    # ── message handlers ─────────────────────────────────────────────────────

    def on_stream_chunk(self, ev: StreamChunk) -> None:
        self._stream_buf += ev.text
        self._stream.update(Text(self._stream_buf, style="#e9d5ff"))

    def _reset_stream(self) -> None:
        # commit current buffer to log, then clear for next turn
        if self._stream_buf.strip():
            for line in self._stream_buf.splitlines():
                self._log.write(Text(f"  {line}", style="#e9d5ff"))
        self._stream_buf = ""
        self._stream.update(Text("", style="#e9d5ff"))

    def on_tool_call(self, ev: ToolCall) -> None:
        self._reset_stream()
        self._log.write(Text(""))
        preview = ev.inp[:80].replace("\n", " ")
        if len(ev.inp) > 80:
            preview += "…"
        t = Text("  ⏺ ", style="bold #a855f7")
        t.append(ev.tool, style="#c084fc")
        t.append(f"({preview})", style="#4b2d8a")
        self._log.write(t)

    def on_tool_result(self, ev: ToolResult) -> None:
        lines = ev.result.splitlines()
        shown = lines[:10]
        for i, ln in enumerate(shown):
            prefix = "  ⎿  " if i == 0 else "     "
            self._log.write(Text(f"{prefix}{ln}", style="#3d1a66"))
        extra = len(lines) - len(shown)
        if extra > 0:
            self._log.write(Text(f"     … +{extra} lines  {ev.elapsed:.1f}s", style="#3d1a66"))
        else:
            self._log.write(Text(f"     {ev.elapsed:.1f}s", style="#3d1a66"))

    def on_stats(self, ev: Stats) -> None:
        # commit streamed response to log
        self._reset_stream()
        self._stream.remove_class("active")
        self._log.write(Text(""))
        t = Text(f"  ~{ev.tokens} tokens · {ev.elapsed:.1f}s", style="#5b21b6")
        self._log.write(t)
        self._log.write(Text(""))

    def on_agent_done(self, _: AgentDone) -> None:
        self._busy = False
        self._stream.remove_class("active")
        self.query_one(Input).disabled = False
        self.query_one(Input).focus()

    def on_agent_error(self, ev: AgentError) -> None:
        self._reset_stream()
        self._stream.remove_class("active")
        self._busy = False
        self._log.write(Text(""))
        self._log.write(Text(f"  ✖  {ev.error}", style="bold #ef4444"))
        self._log.write(Text(""))
        self.query_one(Input).disabled = False
        self.query_one(Input).focus()

    # ── helpers ───────────────────────────────────────────────────────────────

    def _update_header(self) -> None:
        chat = (self._chat_id[:8] + "…") if self._chat_id else "…"
        self.query_one("#header-bar", Static).update(
            f"  ⬡  ElieAtch  ·  {self.model}  ·  chat:{chat}"
        )

    def _info(self, msg: str) -> None:
        for line in msg.splitlines():
            self._log.write(Text(f"  {line}", style="#7c3aed"))
        self._log.write(Text(""))

    def _error(self, msg: str) -> None:
        self._log.write(Text(f"  ✖  {msg}", style="bold #ef4444"))
        self._log.write(Text(""))

    def _shell_passthrough(self, cmd: str) -> None:
        try:
            r = subprocess.run(
                ["powershell", "-NoProfile", "-Command", cmd],
                capture_output=True, text=True, timeout=30, cwd=str(self.cwd),
            )
            out = (r.stdout + r.stderr).strip()
        except Exception as e:
            out = f"Error: {e}"
        for line in out.splitlines()[:30]:
            self._log.write(Text(f"  {line}", style="#9ca3af"))
        self._log.write(Text(""))

    def _show_help(self) -> None:
        cmds = [
            ("/help",         "this help"),
            ("/model",        "show current model"),
            ("/model <name>", "switch model"),
            ("/model list",   "list known models"),
            ("/cwd",          "show working directory"),
            ("/cd <path>",    "change directory"),
            ("/tokens",       "session token estimate"),
            ("/clear",        "clear screen"),
            ("/exit",         "quit"),
            ("!<cmd>",        "shell pass-through (PowerShell)"),
        ]
        self._log.write(Text(""))
        self._log.write(Text("  Commands", style="bold #c084fc"))
        for cmd, desc in cmds:
            t = Text(f"  {cmd:<22}", style="#a855f7")
            t.append(desc, style="#6b7280")
            self._log.write(t)
        self._log.write(Text(""))

    def action_quit(self) -> None:
        self.exit()


# ══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8", errors="replace")
    import argparse
    ap = argparse.ArgumentParser(prog="elieatch-tui")
    ap.add_argument("task", nargs="?", help="Optional first task")
    args = ap.parse_args()
    ElieAtchApp(first_task=args.task).run()


if __name__ == "__main__":
    main()
