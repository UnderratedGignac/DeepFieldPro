"""
ElieAtch TUI v2 — QUANTUMTUI v0.5
Cyberpunk AI operating system terminal.

Launch:
  python tools/elieatch_tui_v2.py
  python tools/elieatch_tui_v2.py "explain place_bet()"
"""
from __future__ import annotations
import sys, os, re, time, threading, subprocess, math
from pathlib import Path
from collections import deque

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

from textual.app import App, ComposeResult
from textual.widget import Widget
from textual.widgets import Static, Input, RichLog
from textual.containers import Horizontal
from textual.reactive import reactive
from textual.message import Message
from textual import on, work
from rich.text import Text

from tools.elieatch import (
    TOOLS, TOOLS_DOC, _SYS, _parse, _strip_preamble,
    KNOWN_MODELS, DEFAULT_MODEL, OBS_LIMIT, SH_TIMEOUT,
    _QWEN_PREFIXES, _get_router,
)

VENV_PY   = str(_ROOT / ".venv" / "Scripts" / "python.exe")
MAX_STEPS = 30

# ── Palette ───────────────────────────────────────────────────────────────────
C_DEEP  = "#060c14"
C_PANEL = "#0b1a2a"
C_CARD  = "#0e2038"
C_CYAN  = "#00ccff"
C_CBRT  = "#00eeff"
C_CDIM  = "#003a50"
C_CBRD  = "#0a2840"
C_MAG   = "#cc44ff"
C_MDIM  = "#220044"
C_GRN   = "#00ff88"
C_GDIM  = "#003322"
C_RED   = "#ff3355"
C_AMB   = "#ffaa22"
C_TXT   = "#88bbcc"
C_TXTB  = "#cce8ff"
C_TXTD  = "#1e3848"
C_TEAL  = "#00aa88"
C_PINK  = "#ff6ec7"

# ══════════════════════════════════════════════════════════════════════════════
# MESSAGES (unchanged)
# ══════════════════════════════════════════════════════════════════════════════

class StreamChunk(Message):
    def __init__(self, text: str) -> None:
        super().__init__(); self.text = text

class ToolCallMsg(Message):
    def __init__(self, tool: str, inp: str) -> None:
        super().__init__(); self.tool = tool; self.inp = inp

class ToolResultMsg(Message):
    def __init__(self, tool: str, result: str, elapsed: float, ok: bool = True) -> None:
        super().__init__()
        self.tool = tool; self.result = result; self.elapsed = elapsed; self.ok = ok

class StatsMsg(Message):
    def __init__(self, tokens: int, elapsed: float, tps: float) -> None:
        super().__init__(); self.tokens = tokens; self.elapsed = elapsed; self.tps = tps

class SessionReady(Message):
    def __init__(self, chat_id: str) -> None:
        super().__init__(); self.chat_id = chat_id

class AgentError(Message):
    def __init__(self, error: str) -> None:
        super().__init__(); self.error = error

class AgentDone(Message):
    pass

class CmdSubmitted(Message):
    def __init__(self, value: str) -> None:
        super().__init__(); self.value = value

class AgentStateMsg(Message):
    def __init__(self, state: str, task: str = "") -> None:
        super().__init__(); self.state = state; self.task = task


# ══════════════════════════════════════════════════════════════════════════════
# QUANTUM HEADER  (top bar — model tabs + stats)
# ══════════════════════════════════════════════════════════════════════════════

class QuantumHeader(Static):
    """Single-line header rendered as a Static — no nested containers."""
    DEFAULT_CSS = f"""
    QuantumHeader {{
        dock: top;
        height: 1;
        background: {C_PANEL};
        border-bottom: solid {C_CDIM};
        color: {C_CYAN};
        padding: 0 1;
        content-align: left middle;
    }}
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._cpu  = 0.0
        self._ram  = 0.0
        self._sess_start = time.time()
        self.model       = DEFAULT_MODEL
        self.provider    = "Qwen CDP"
        self.tokens      = 0
        self.cost        = 0.0
        self.agent_state = "IDLE"

    def on_mount(self) -> None:
        self.set_interval(2.0, self._tick)
        self._render()

    def _tick(self) -> None:
        if HAS_PSUTIL:
            self._cpu = psutil.cpu_percent(interval=0)
            self._ram = psutil.virtual_memory().percent
        self._render()

    def update_stats(self, **kwargs) -> None:
        for k, v in kwargs.items():
            if hasattr(self, k):
                setattr(self, k, v)
        self._render()

    def _render(self) -> None:
        elapsed = int(time.time() - self._sess_start)
        m, s = divmod(elapsed, 60)
        SEP = ("  │  ", C_TXTD)
        t = Text()
        # Logo
        t.append(" ▷ ", style=f"bold {C_CYAN}")
        t.append("ElieAtch", style=f"bold {C_TXTB}")
        t.append(*SEP)
        # Tabs
        t.append(" ElieAtch ", style=f"bold {C_CYAN}")
        t.append("│", style=C_CDIM)
        t.append(f" {self.model} ", style=f"bold {C_TXTB}")
        t.append("│", style=C_CDIM)
        sync_col = C_AMB if self.agent_state == "RUNNING" else C_GRN
        sync_lbl = "Running" if self.agent_state == "RUNNING" else "Syncing"
        t.append(f" {self.provider} [", style=C_TXT)
        t.append(sync_lbl, style=f"bold {sync_col}")
        t.append("]", style=C_TXT)
        t.append(*SEP)
        # Stats
        t.append(f"~{self.tokens:,} tok", style=C_MAG)
        t.append(*SEP)
        t.append(f"${self.cost:.4f}", style=C_TXT)
        t.append(*SEP)
        cpu_col = C_GRN if self._cpu < 50 else C_AMB if self._cpu < 80 else C_RED
        t.append(f"CPU {self._cpu:.0f}%", style=cpu_col)
        t.append(*SEP)
        ram_col = C_GRN if self._ram < 60 else C_AMB if self._ram < 85 else C_RED
        t.append(f"RAM {self._ram:.0f}%", style=ram_col)
        t.append(*SEP)
        t.append(f"Session: {m}m {s:02d}s", style=C_TXTD)
        self.update(t)


# ══════════════════════════════════════════════════════════════════════════════
# EXPLORER MATRIX  (left sidebar)
# ══════════════════════════════════════════════════════════════════════════════

class ExplorerMatrix(Widget):
    DEFAULT_CSS = f"""
    ExplorerMatrix {{
        width: 22;
        height: 100%;
        background: {C_PANEL};
        border-right: solid {C_CDIM};
        overflow-y: auto;
        scrollbar-color: {C_CDIM};
        scrollbar-background: {C_PANEL};
        transition: width 200ms in_out_cubic;
    }}
    ExplorerMatrix.collapsed {{
        width: 0;
        min-width: 0;
        overflow: hidden;
    }}
    ExplorerMatrix Static {{
        background: {C_PANEL};
        width: 100%;
    }}
    #em-title {{
        height: 1;
        background: {C_CARD};
        color: {C_CYAN};
        text-style: bold;
        padding: 0 1;
        border-bottom: solid {C_CDIM};
    }}
    #em-agents, #em-projects, #em-memory, #em-tasks, #em-history {{
        padding: 0;
    }}
    """

    def compose(self) -> ComposeResult:
        yield Static("", id="em-title")
        yield Static("", id="em-agents")
        yield Static("", id="em-projects")
        yield Static("", id="em-memory")
        yield Static("", id="em-tasks")
        yield Static("", id="em-history")

    def on_mount(self) -> None:
        self._history: list[str] = []
        self._agent_state = "IDLE"
        self._task = ""
        self._tool_records: list[tuple] = []
        self._pulse = 0
        self.set_interval(3.0, self._heartbeat)
        self._render_all()

    def _heartbeat(self) -> None:
        self._pulse += 1
        self._render_all()

    def _render_all(self) -> None:
        try:
            # Title
            t = Text()
            t.append(" ▷ ", style=f"bold {C_CYAN}")
            t.append("EXPLORER MATRIX", style=f"bold {C_CYAN}")
            self.query_one("#em-title", Static).update(t)

            self._render_agents()
            self._render_projects()
            self._render_memory()
            self._render_tasks()
            self._render_history()
        except Exception:
            pass

    def _section_header(self, label: str, icon: str = "⊕") -> Text:
        t = Text()
        t.append(f" {icon} ", style=f"bold {C_CYAN}")
        t.append(label, style=f"bold {C_TXTB}")
        t.append("  ...\n", style=C_TXTD)
        return t

    def _render_agents(self) -> None:
        t = self._section_header("AGENTS")
        health = 98
        bar_w = 10
        filled = int(health / 100 * bar_w)
        bar = "█" * filled + "░" * (bar_w - filled)
        t.append("  ElieAtch ", style=f"bold {C_TXTB}")
        t.append("[Active]\n", style=f"bold {C_GRN}")
        t.append(f"  {bar} ", style=C_GRN)
        t.append(f"{health}%\n", style=C_TXT)
        self.query_one("#em-agents", Static).update(t)

    def _render_projects(self) -> None:
        t = self._section_header("PROJECTS")
        items = [
            ("/arc",       "✓", C_GRN),
            ("/tests",     "△", C_RED),
            ("/docs",      "✓", C_GRN),
            ("/ets",       "✓", C_GRN),
            ("/dets",      "✓", C_GRN),
            ("/templates", "✓", C_GRN),
            ("/src",       "✓", C_GRN),
        ]
        t.append("  ▼ DeepFieldPro\n", style=f"bold {C_CYAN}")
        for name, icon, col in items:
            t.append(f"    ▶ {name:<10}", style=C_TXT)
            t.append(f" ({icon})", style=col)
            t.append("  ●\n", style=col)
        self.query_one("#em-projects", Static).update(t)

    def _render_memory(self) -> None:
        t = self._section_header("MEMORY")
        # simple arc gauge using blocks
        pct = 52.768
        arc = self._mini_gauge(pct)
        t.append(f"  {arc}\n", style=C_CYAN)
        for label, val in [("Long-term", 52.768), ("Session", 6.738), ("Key-Value", 71.788)]:
            bar_w = 6
            filled = int(val / 100 * bar_w)
            bar = "▓" * filled + "░" * (bar_w - filled)
            col = C_CYAN if val > 30 else C_TXTD
            t.append(f"  {label:<10} ", style=C_TXT)
            t.append(f"{bar} ", style=col)
            t.append(f"{val:.3f}%\n", style=C_TXT)
        self.query_one("#em-memory", Static).update(t)

    def _mini_gauge(self, pct: float) -> str:
        chars = ["░", "▒", "▓", "█"]
        idx   = min(3, int(pct / 25))
        return f"◖{'█' * idx}{'░' * (3 - idx)}◗ {pct:.0f}%"

    def _render_tasks(self) -> None:
        t = self._section_header("TASKS")
        tasks = [
            "Planned planned tasks",
            "Planned tasks ( progr...",
            "Planned tasks to chan...",
            "Planned tasks a queue",
        ]
        for task in tasks:
            icon = "◉" if task == self._task else "○"
            col  = C_CYAN if task == self._task else C_TXT
            t.append(f"  {icon} ", style=f"bold {col}")
            t.append(f"{task[:18]}\n", style=C_TXT)
        self.query_one("#em-tasks", Static).update(t)

    def _render_history(self) -> None:
        t = self._section_header("HISTORY")
        if not self._history:
            t.append("  (no history yet)\n", style=C_TXTD)
        else:
            for msg in self._history[-3:]:
                t.append("  ● ", style=f"bold {C_CYAN}")
                t.append(f"{msg[:17]}\n", style=C_TXT)
                t.append(f"    {msg[17:34]}...\n", style=C_TXTD)
        self.query_one("#em-history", Static).update(t)

    def push_history(self, msg: str) -> None:
        self._history.append(msg)
        self._render_history()

    def set_agent_state(self, state: str, task: str = "") -> None:
        self._agent_state = state
        self._task = task
        self._render_tasks()

    def toggle_collapse(self) -> None:
        self.toggle_class("collapsed")


# ══════════════════════════════════════════════════════════════════════════════
# WORKSPACE CONSOLE  (center chat)
# ══════════════════════════════════════════════════════════════════════════════

class WorkspaceConsole(Widget):
    DEFAULT_CSS = f"""
    WorkspaceConsole {{
        width: 1fr;
        height: 100%;
        background: {C_DEEP};
    }}
    #ws-header {{
        height: 1;
        background: {C_CARD};
        border-bottom: solid {C_CDIM};
        color: {C_CYAN};
        text-style: bold;
        padding: 0 2;
        content-align: left middle;
    }}
    #chat-log {{
        height: 1fr;
        background: {C_DEEP};
        padding: 0;
        scrollbar-color: {C_CDIM};
        scrollbar-background: {C_DEEP};
    }}
    #stream-widget {{
        background: {C_PANEL};
        color: {C_TXT};
        padding: 0 4;
        min-height: 1;
        max-height: 12;
        border-top: solid {C_CDIM};
        display: none;
    }}
    #stream-widget.streaming {{
        display: block;
    }}
    """

    def compose(self) -> ComposeResult:
        yield Static("", id="ws-header")
        yield RichLog(id="chat-log", markup=False, highlight=False, wrap=True)
        yield Static("", id="stream-widget")

    def on_mount(self) -> None:
        self._stream_buf = ""
        self._stream_open = False
        self._render_header()
        self.show_banner()

    def _render_header(self, model: str = DEFAULT_MODEL) -> None:
        t = Text()
        t.append(" >_ ", style=f"bold {C_CYAN}")
        t.append("WORKSPACE CONSOLE", style=f"bold {C_CYAN}")
        try:
            self.query_one("#ws-header", Static).update(t)
        except Exception:
            pass

    def show_banner(self) -> None:
        log = self.query_one(RichLog)
        log.write(Text(""))
        w = 55
        r1 = Text(); r1.append("  ╔" + "═" * w + "╗", style=C_CDIM)
        r2 = Text()
        r2.append("  ║  ", style=C_CDIM)
        r2.append("⬡ QUANTUMTUI v0.5", style=f"bold {C_CYAN}")
        r2.append(" — AI OPERATING SYSTEM", style=f"bold {C_TXT}")
        r2.append(" " * (w - 36) + "║", style=C_CDIM)
        r3 = Text(); r3.append("  ╚" + "═" * w + "╝", style=C_CDIM)
        log.write(r1); log.write(r2); log.write(r3)
        log.write(Text("  Type a task or /help for commands", style=C_TXTD))
        log.write(Text(""))

    def clear_chat(self) -> None:
        self.query_one(RichLog).clear()
        self._stream_buf = ""
        self._stream_open = False
        sw = self.query_one("#stream-widget", Static)
        sw.update("")
        sw.remove_class("streaming")
        self.show_banner()

    def add_user_message(self, text: str) -> None:
        log = self.query_one(RichLog)
        log.write(Text(""))
        t = Text()
        t.append("  ╭", style=C_CDIM)
        t.append("─" * 3, style=C_CDIM)
        t.append(" You ", style=f"bold {C_MAG}")
        t.append("─" * 34, style=C_CDIM)
        t.append("╮", style=C_CDIM)
        log.write(t)
        for line in (text.splitlines() or [text]):
            row = Text()
            row.append("  │ ", style=C_CDIM)
            row.append(line, style=C_TXTB)
            log.write(row)
        log.write(Text("  ╰" + "─" * 40 + "╯", style=C_CDIM))

    def start_agent_response(self) -> None:
        log = self.query_one(RichLog)
        log.write(Text(""))
        t = Text()
        t.append("  ╭", style=C_CDIM)
        t.append("─" * 3, style=C_CDIM)
        t.append(" ⬡ ElieAtch ", style=f"bold {C_CYAN}")
        t.append("─" * 26, style=C_CDIM)
        t.append("╮", style=C_CDIM)
        log.write(t)
        self._stream_buf = ""
        self._stream_open = True
        sw = self.query_one("#stream-widget", Static)
        sw.update(Text("", style=C_TXT))
        sw.add_class("streaming")

    def stream_chunk(self, chunk: str) -> None:
        self._stream_buf += chunk
        display = self._stream_buf[-600:] if len(self._stream_buf) > 600 else self._stream_buf
        rendered = display.replace("\n", "\n  │ ")
        self.query_one("#stream-widget", Static).update(
            Text(f"  │ {rendered}", style=C_TXT)
        )

    def commit_response(self, tokens: int, elapsed: float) -> None:
        if not self._stream_open:
            return
        log = self.query_one(RichLog)
        for line in self._stream_buf.splitlines():
            t = Text()
            t.append("  │ ", style=C_CDIM)
            t.append(line, style=C_TXTB)
            log.write(t)
        stats = Text()
        stats.append("  │ ", style=C_CDIM)
        stats.append(f"~{tokens:,} tokens", style=C_CDIM)
        stats.append("  ·  ", style=C_TXTD)
        stats.append(f"{elapsed:.1f}s", style=C_CDIM)
        log.write(stats)
        log.write(Text("  ╰" + "─" * 40 + "╯", style=C_CDIM))
        log.write(Text(""))
        self._stream_buf = ""
        self._stream_open = False
        sw = self.query_one("#stream-widget", Static)
        sw.update("")
        sw.remove_class("streaming")

    def _flush_stream_partial(self) -> None:
        if not self._stream_buf:
            return
        log = self.query_one(RichLog)
        for line in self._stream_buf.splitlines():
            t = Text()
            t.append("  │ ", style=C_CDIM)
            t.append(line, style=C_TXTB)
            log.write(t)
        self._stream_buf = ""
        self.query_one("#stream-widget", Static).update(Text("", style=C_TXT))

    def show_tool_call(self, tool: str, inp: str) -> None:
        self._flush_stream_partial()
        preview = inp[:50].replace("\n", " ")
        if len(inp) > 50:
            preview += "…"
        t = Text()
        t.append("  │ ", style=C_CDIM)
        t.append("  ┌─ ", style=C_CDIM)
        t.append("⏺ ", style=f"bold {C_MAG}")
        t.append(tool, style=f"bold {C_CYAN}")
        t.append(f"({preview})", style=C_TXTD)
        self.query_one(RichLog).write(t)

    def show_tool_result(self, result: str, elapsed: float, ok: bool = True) -> None:
        log = self.query_one(RichLog)
        icon  = "✓" if ok else "✖"
        color = C_GRN if ok else C_RED
        lines = result.splitlines()
        shown = lines[:5]
        for i, ln in enumerate(shown):
            prefix = f"  │   {icon} " if i == 0 else "  │     "
            t = Text(prefix, style=color if i == 0 else C_TXTD)
            t.append(ln[:68], style=C_TXT)
            log.write(t)
        extra = len(lines) - len(shown)
        suffix = f"+{extra} lines  ·  {elapsed:.2f}s" if extra > 0 else f"{elapsed:.2f}s"
        log.write(Text(f"  │     {suffix}", style=C_TXTD))
        self._stream_open = True

    def write_info(self, msg: str) -> None:
        log = self.query_one(RichLog)
        for line in str(msg).splitlines():
            t = Text()
            t.append("  ", style="")
            t.append(line, style=C_CYAN)
            log.write(t)
        log.write(Text(""))

    def write_error(self, msg: str) -> None:
        log = self.query_one(RichLog)
        t = Text()
        t.append("  ✖  ", style=f"bold {C_RED}")
        t.append(msg, style=C_RED)
        log.write(t)
        log.write(Text(""))


# ══════════════════════════════════════════════════════════════════════════════
# EXECUTION MATRIX  (right sidebar)
# ══════════════════════════════════════════════════════════════════════════════

class ExecutionMatrix(Widget):
    DEFAULT_CSS = f"""
    ExecutionMatrix {{
        width: 28;
        height: 100%;
        background: {C_PANEL};
        border-left: solid {C_CDIM};
        overflow-y: auto;
        scrollbar-color: {C_CDIM};
        scrollbar-background: {C_PANEL};
        transition: width 200ms in_out_cubic;
    }}
    ExecutionMatrix.collapsed {{
        width: 0;
        min-width: 0;
        overflow: hidden;
    }}
    ExecutionMatrix Static {{
        background: {C_PANEL};
        width: 100%;
    }}
    #ex-title {{
        height: 1;
        background: {C_CARD};
        color: {C_CYAN};
        text-style: bold;
        padding: 0 1;
        border-bottom: solid {C_CDIM};
    }}
    """

    def compose(self) -> ComposeResult:
        yield Static("", id="ex-title")
        yield Static("", id="ex-health")
        yield Static("", id="ex-flow")
        yield Static("", id="ex-tools")
        yield Static("", id="ex-perf")

    def on_mount(self) -> None:
        self._plan: list[str] = []
        self._plan_idx = 0
        self._tool_records: deque = deque(maxlen=5)
        self._tps = 0.0
        self._sess_tokens = 0
        self._tps_history: deque = deque(maxlen=20)
        self._cpu = 0.0
        self._ram = 0.0
        self._agent_state = "IDLE"
        self.set_interval(3.0, self._tick)
        self._render_all()

    def _tick(self) -> None:
        if HAS_PSUTIL:
            self._cpu = psutil.cpu_percent(interval=0)
            self._ram = psutil.virtual_memory().percent
        self._render_all()

    def _render_all(self) -> None:
        try:
            t = Text()
            t.append(" ▷ ", style=f"bold {C_CYAN}")
            t.append("EXECUTION MATRIX", style=f"bold {C_CYAN}")
            self.query_one("#ex-title", Static).update(t)
            self._render_health()
            self._render_flow()
            self._render_tools()
            self._render_perf()
        except Exception:
            pass

    def _section_header(self, label: str, badge: str = "") -> Text:
        t = Text()
        t.append(" ⊕ ", style=f"bold {C_CYAN}")
        t.append(label, style=f"bold {C_TXTB}")
        if badge:
            t.append(f"  {badge}", style=C_PINK)
        t.append("\n", style="")
        return t

    def _gauge(self, value: float, label: str, max_val: float = 100.0) -> Text:
        pct = min(1.0, value / max(max_val, 1))
        w   = 5
        filled = int(pct * w)
        bar = "█" * filled + "░" * (w - filled)
        col = C_GRN if pct < 0.5 else C_AMB if pct < 0.8 else C_RED
        t = Text()
        t.append(" ┌─────┐\n", style=C_CDIM)
        t.append(f" │", style=C_CDIM)
        t.append(f"{bar}", style=col)
        t.append(f"│ ", style=C_CDIM)
        t.append(f"{label}\n", style=C_TXT)
        t.append(f" │ ", style=C_CDIM)
        disp = f"{value:.0f}%" if max_val == 100 else f"{value:.2f}"
        t.append(f"{disp:<4}", style=f"bold {col}")
        t.append(" │\n", style=C_CDIM)
        t.append(" └─────┘\n", style=C_CDIM)
        return t

    def _render_health(self) -> None:
        t = self._section_header("SYSTEM HEALTH")
        # Three gauges side by side (text layout)
        cpu_pct = self._cpu
        ram_pct = self._ram
        # Compact inline triple display
        def _mini(v: float, max_v: float = 100.0) -> tuple[str, str]:
            p = min(1.0, v / max(max_v, 1))
            w = 4
            b = "█" * int(p * w) + "░" * (w - int(p * w))
            c = C_GRN if p < 0.5 else C_AMB if p < 0.8 else C_RED
            return b, c

        cpu_b, cpu_c = _mini(cpu_pct)
        ram_b, ram_c = _mini(ram_pct)
        # row 1
        t.append(f"  CPU     RAM    Disk I/O\n", style=C_TXT)
        t.append("  ", style="")
        t.append(cpu_b, style=cpu_c)
        t.append("  ", style="")
        t.append(ram_b, style=ram_c)
        t.append("   ", style="")
        t.append("░░░░", style=C_TXTD)
        t.append("\n", style="")
        t.append(f"  {cpu_pct:.0f}%", style=f"bold {cpu_c}")
        t.append(f"     {ram_pct:.0f}%", style=f"bold {ram_c}")
        t.append(f"    0.000\n", style=C_TXTD)
        # capacity labels
        t.append("  90%    88%    38%\n", style=C_TXTD)
        self.query_one("#ex-health", Static).update(t)

    def _render_flow(self) -> None:
        t = self._section_header("AGENT FLOW", "(New visual feature)")
        _S = {
            "IDLE":     ("●", C_TXTD),
            "RUNNING":  ("▶", C_CYAN),
            "PLANNING": ("◈", C_MAG),
            "DONE":     ("✓", C_GRN),
            "ERROR":    ("✖", C_RED),
        }
        icon, col = _S.get(self._agent_state, ("●", C_TXTD))

        steps = self._plan if self._plan else [
            "Parse", "Model Query", "Code Gen", "Security Review"
        ]
        # Row 1: main pipeline
        t.append(" ", style="")
        for i, step in enumerate(steps[:4]):
            short = step[:8]
            done = i < self._plan_idx
            cur  = i == self._plan_idx
            s_icon = "✓" if done else ("▶" if cur else "·")
            s_col  = C_GRN if done else (C_CYAN if cur else C_TXTD)
            t.append(f"{s_icon}", style=f"bold {s_col}")
            t.append(short[:6], style=s_col)
            if i < len(steps[:4]) - 1:
                t.append("→", style=C_CDIM)
        t.append("\n", style="")

        # Sub-steps
        if self._plan and len(self._plan) > 4:
            t.append("         ↓\n", style=C_CDIM)
            for step in self._plan[4:7]:
                t.append(f"      {step[:18]}\n", style=C_TXT)
        else:
            t.append(f"     ↓\n", style=C_CDIM)
            t.append(f"  Code Review\n", style=C_TXTD)
            t.append(f"     ↓\n", style=C_CDIM)
            t.append(f"  Parse\n", style=C_TXTD)
            t.append(f"  Model Query\n", style=C_TXTD)
        self.query_one("#ex-flow", Static).update(t)

    def _render_tools(self) -> None:
        t = self._section_header("ACTIVE TOOLS", "(New visual feature)")
        defaults = [
            ("▣", "File Manager"),
            ("●", "Python Interpreter"),
            ("⊕", "Web Search"),
        ]
        if self._tool_records:
            for tool, elapsed, ok in list(self._tool_records)[-4:]:
                icon  = "✓" if ok else "✖"
                color = C_GRN if ok else C_RED
                t.append(f"  {icon} ", style=f"bold {color}")
                t.append(f"{tool:<20}", style=C_TXT)
                t.append(f" {elapsed:.2f}s\n", style=C_TXTD)
        else:
            for icon, name in defaults:
                t.append(f"  {icon} ", style=f"bold {C_CYAN}")
                t.append(f"{name}\n", style=C_TXT)
        self.query_one("#ex-tools", Static).update(t)

    def _render_perf(self) -> None:
        t = self._section_header("PERFORMANCE ANALYTICS")
        # Sparkline
        history = list(self._tps_history)
        if len(history) < 2:
            history = [0] * 20
        sparkline_w = 22
        history_pad = (history + [0] * sparkline_w)[-sparkline_w:]
        max_v = max(history_pad) or 1
        bars  = " ▁▂▃▄▅▆▇█"
        line  = ""
        for v in history_pad:
            idx = min(8, int(v / max_v * 8))
            line += bars[idx]
        t.append(f"  {line}\n", style=C_CYAN)
        t.append("  02:00  11:30  15:00\n", style=C_TXTD)
        t.append(f"\n", style="")
        tps_color = C_CYAN if self._tps > 50 else C_TXT
        t.append(f"  Text tok/s   ", style=C_TXT)
        t.append(f"{self._tps:.0f} tok/s\n", style=f"bold {tps_color}")
        t.append(f"  ~{self._sess_tokens:,} tok session\n", style=C_TXTD)
        self.query_one("#ex-perf", Static).update(t)

    # ── public API ─────────────────────────────────────────────────────────

    def set_agent_state(self, state: str, task: str = "") -> None:
        self._agent_state = state
        self._render_flow()

    def set_plan(self, steps: list[str]) -> None:
        self._plan = list(steps)
        self._plan_idx = 0
        self._render_flow()

    def mark_step(self, idx: int, done: bool = True) -> None:
        if done and idx >= self._plan_idx:
            self._plan_idx = idx + 1
        self._render_flow()

    def add_tool_record(self, tool: str, elapsed: float, ok: bool) -> None:
        self._tool_records.append((tool, elapsed, ok))
        self._render_tools()

    def update_context(self, used: int, total: int) -> None:
        pass  # context info shown in header

    def update_perf(self, tps: float, total_tokens: int, cost: float = 0.0) -> None:
        self._tps = tps
        self._sess_tokens = total_tokens
        self._tps_history.append(tps)
        self._render_perf()

    def toggle_collapse(self) -> None:
        self.toggle_class("collapsed")


# ══════════════════════════════════════════════════════════════════════════════
# QUANTUM INPUT  (command bar)
# ══════════════════════════════════════════════════════════════════════════════

_CMDS: dict[str, str] = {
    "/model":     "switch AI model  ·  /model list  |  /model <name>",
    "/providers": "show all LLM providers + API key status",
    "/agent":     "agent mode",
    "/mcp":       "MCP server status",
    "/memory":    "show memory recalls",
    "/tools":     "list available tools",
    "/skills":    "list loaded skills",
    "/workflow":  "run a workflow",
    "/dashboard": "toggle dashboard view",
    "/help":      "show command reference",
    "/clear":     "clear chat history",
    "/exit":      "quit ElieAtch",
    "/cwd":       "show working directory",
    "/cd":        "change directory  ·  /cd <path>",
    "/tokens":    "session token count",
    "/tui-info":  "TUI version and status",
}


class QuantumInput(Widget):
    DEFAULT_CSS = f"""
    QuantumInput {{
        dock: bottom;
        height: 4;
        background: {C_PANEL};
        border-top: solid {C_CDIM};
    }}
    #qi-input {{
        height: 3;
        background: {C_CARD};
        border: tall {C_CDIM};
        color: {C_TXTB};
        padding: 0 2;
    }}
    #qi-input:focus {{
        border: tall {C_CYAN};
    }}
    #qi-hints {{
        height: 1;
        background: {C_PANEL};
        color: {C_TXTD};
        padding: 0 3;
        content-align: left middle;
    }}
    """

    def compose(self) -> ComposeResult:
        yield Input(placeholder="  ⬡  type a task or /command…", id="qi-input")
        yield Static("", id="qi-hints")

    def on_mount(self) -> None:
        self._update_hints("")

    @on(Input.Changed, "#qi-input")
    def _on_changed(self, ev: Input.Changed) -> None:
        self._update_hints(ev.value)

    @on(Input.Submitted, "#qi-input")
    def _on_submitted(self, ev: Input.Submitted) -> None:
        value = ev.value.strip()
        if value:
            self.post_message(CmdSubmitted(value))
        self.query_one(Input).value = ""

    def focus_input(self) -> None:
        self.query_one(Input).focus()

    def _update_hints(self, value: str) -> None:
        hints = self.query_one("#qi-hints", Static)
        if not value:
            t = Text()
            for i, cmd in enumerate(list(_CMDS.keys())[:9]):
                t.append(cmd, style=C_TXTD)
                if i < 8:
                    t.append("  ", style="")
            hints.update(t)
            return
        if value.startswith("/"):
            matches = {k: v for k, v in _CMDS.items() if k.startswith(value.lower())}
            if matches:
                t = Text()
                for i, (cmd, desc) in enumerate(list(matches.items())[:3]):
                    t.append(cmd, style=f"bold {C_CYAN}")
                    t.append(f"  {desc[:28]}", style=C_TXTD)
                    if i < min(2, len(matches) - 1):
                        t.append("  │  ", style=C_TXTD)
                hints.update(t)
            else:
                hints.update(Text("  ✖  no matching command", style=C_RED))
        else:
            t = Text()
            t.append("  ⬡ ", style=f"bold {C_CYAN}")
            t.append("agent task", style=C_TXT)
            t.append("  ·  Enter to run", style=C_TXTD)
            hints.update(t)


# ══════════════════════════════════════════════════════════════════════════════
# QUANTUM STATUS LINE  (bottom 1-line bar)
# ══════════════════════════════════════════════════════════════════════════════

class QuantumStatusLine(Static):
    DEFAULT_CSS = f"""
    QuantumStatusLine {{
        dock: bottom;
        height: 1;
        background: {C_CARD};
        border-top: solid {C_CDIM};
        color: {C_CYAN};
        text-style: bold;
        padding: 0 2;
        content-align: left middle;
    }}
    """

    def on_mount(self) -> None:
        self._state = "READY"
        self._model = DEFAULT_MODEL
        self._render()
        self.set_interval(1.0, self._render)

    def update_state(self, state: str, model: str = "") -> None:
        self._state = state
        if model:
            self._model = model
        self._render()

    def _render(self) -> None:
        state_col = C_GRN if self._state == "READY" else C_AMB if self._state == "RUNNING" else C_RED
        t = Text()
        t.append("[ STATUS: ", style=C_TXTD)
        t.append(self._state, style=f"bold {state_col}")
        t.append(" ]", style=C_TXTD)
        t.append("  [ ACTIVE MODEL: ", style=C_TXTD)
        t.append(self._model.upper()[:20], style=f"bold {C_CYAN}")
        t.append(" ]", style=C_TXTD)
        t.append("  [ POWERED BY ", style=C_TXTD)
        t.append("QUANTUMTUI v0.5", style=f"bold {C_MAG}")
        t.append(" ]", style=C_TXTD)
        self.update(t)


# ══════════════════════════════════════════════════════════════════════════════
# MAIN APP
# ══════════════════════════════════════════════════════════════════════════════

APP_CSS = f"""
Screen {{
    background: {C_DEEP};
    layers: base;
}}
#main-row {{
    height: 1fr;
}}
"""


class ElieAtchApp(App):
    CSS = APP_CSS

    BINDINGS = [
        ("ctrl+b", "toggle_left",  "Toggle Explorer"),
        ("ctrl+r", "toggle_right", "Toggle Execution"),
        ("ctrl+k", "focus_cmd",    "Command Bar"),
        ("ctrl+l", "clear_chat",   "Clear Chat"),
        ("escape", "focus_cmd",    "Focus Input"),
    ]

    def __init__(self, first_task: str | None = None) -> None:
        super().__init__()
        self.model        = DEFAULT_MODEL
        self.cwd          = _ROOT
        self._chat_id: str | None = None
        self._turns       = 0
        self._chars       = 0
        self._busy        = False
        self._interrupt   = threading.Event()
        self._first_task  = first_task
        self._t_start     = 0.0
        self._last_tool   = ""
        self._router_messages: list[dict] = []

    def compose(self) -> ComposeResult:
        yield QuantumHeader(id="qh")
        with Horizontal(id="main-row"):
            yield ExplorerMatrix(id="explorer")
            yield WorkspaceConsole(id="workspace")
            yield ExecutionMatrix(id="execution")
        yield QuantumInput(id="qi")
        yield QuantumStatusLine(id="status-line")

    def on_mount(self) -> None:
        self.query_one(QuantumInput).focus_input()
        self._init_session()

    # ── session ───────────────────────────────────────────────────────────

    @property
    def _is_qwen(self) -> bool:
        return self.model.lower().startswith(_QWEN_PREFIXES)

    @work(thread=True)
    def _init_session(self) -> None:
        if self._is_qwen:
            from tools.qwen_bridge import new_chat
            try:
                cid = new_chat()
                self.call_from_thread(self.post_message, SessionReady(cid))
                return
            except Exception as e:
                # Qwen CDP/REST unavailable — fall through to router fallback
                fallback_model = "nvidia/qwen/qwen3-235b-a22b-instruct-2507"
                self.call_from_thread(
                    self.post_message,
                    AgentError(f"Qwen session failed ({e})  →  falling back to router")
                )
                # Give the error a moment to display, then try router
                import time as _t; _t.sleep(0.5)
                self.model = fallback_model
                self.call_from_thread(
                    self.post_message,
                    AgentStateMsg("IDLE", f"switched to {fallback_model}")
                )

        # Router path (non-Qwen or after Qwen fallback)
        router = _get_router()
        bridge, _ = router._resolve(self.model)
        if bridge.is_available():
            self.call_from_thread(self.post_message, SessionReady(f"router:{bridge.provider}"))
        else:
            # Try OpenRouter free as last resort
            from tools.llm_bridges.openrouter_free import OpenRouterFreeBridge
            b = OpenRouterFreeBridge()
            if b.is_available():
                self.call_from_thread(self.post_message, SessionReady("router:openrouter-free"))
            else:
                self.call_from_thread(
                    self.post_message,
                    AgentError(f"No model available. Add NVIDIA_API_KEY or OPENROUTER_API_KEY to .env")
                )

    def on_session_ready(self, ev: SessionReady) -> None:
        self._chat_id = ev.chat_id
        provider = "Qwen CDP" if self._is_qwen else ev.chat_id.replace("router:", "")
        self.query_one("#qh", QuantumHeader).update_stats(provider=provider)
        ws = self.query_one("#workspace", WorkspaceConsole)
        ws.write_info(f"session ready  ·  provider: {provider}")
        self.query_one("#status-line", QuantumStatusLine).update_state("READY", self.model)
        if self._first_task:
            self._run_task(self._first_task)
            self._first_task = None

    # ── agent state events ────────────────────────────────────────────────

    def on_agent_state_msg(self, ev: AgentStateMsg) -> None:
        try:
            qh  = self.query_one("#qh", QuantumHeader)
            em  = self.query_one("#explorer", ExplorerMatrix)
            ex  = self.query_one("#execution", ExecutionMatrix)
            sl  = self.query_one("#status-line", QuantumStatusLine)
            qh.update_stats(agent_state=ev.state, task_label=ev.task)
            em.set_agent_state(ev.state, ev.task)
            ex.set_agent_state(ev.state, ev.task)
            sl.update_state(ev.state if ev.state != "DONE" else "READY")
        except Exception:
            pass

    def on_stream_chunk(self, ev: StreamChunk) -> None:
        try:
            self.query_one("#workspace", WorkspaceConsole).stream_chunk(ev.text)
            self._chars += len(ev.text)
        except Exception:
            pass

    def on_tool_call_msg(self, ev: ToolCallMsg) -> None:
        self._last_tool = ev.tool
        try:
            self.query_one("#workspace", WorkspaceConsole).show_tool_call(ev.tool, ev.inp)
        except Exception:
            pass

    def on_tool_result_msg(self, ev: ToolResultMsg) -> None:
        try:
            self.query_one("#workspace", WorkspaceConsole).show_tool_result(ev.result, ev.elapsed, ev.ok)
            self.query_one("#execution", ExecutionMatrix).add_tool_record(ev.tool, ev.elapsed, ev.ok)
        except Exception:
            pass

    def on_stats_msg(self, ev: StatsMsg) -> None:
        try:
            ws  = self.query_one("#workspace", WorkspaceConsole)
            qh  = self.query_one("#qh", QuantumHeader)
            ex  = self.query_one("#execution", ExecutionMatrix)
            ws.commit_response(ev.tokens, ev.elapsed)
            qh.update_stats(tokens=ev.tokens, agent_state="IDLE", task_label="")
            ex.update_context(ev.tokens, 4000)
            ex.update_perf(ev.tps, ev.tokens)
        except Exception:
            pass

    def on_agent_done(self, _: AgentDone) -> None:
        self._busy = False
        try:
            self.query_one(QuantumInput).focus_input()
        except Exception:
            pass

    def on_agent_error(self, ev: AgentError) -> None:
        self._busy = False
        msg = ev.error or "Unknown error"
        # Toast always works regardless of widget state
        self.notify(msg[:160], title="Agent Error", severity="error", timeout=8)
        try:
            self.query_one("#workspace", WorkspaceConsole).write_error(msg)
            self.query_one("#qh", QuantumHeader).update_stats(agent_state="ERROR")
            self.query_one("#status-line", QuantumStatusLine).update_state("ERROR")
            self.query_one(QuantumInput).focus_input()
        except Exception:
            pass

    # ── command routing ───────────────────────────────────────────────────

    def on_cmd_submitted(self, ev: CmdSubmitted) -> None:
        self._handle_cmd(ev.value.strip())

    def _handle_cmd(self, line: str) -> None:
        lo  = line.lower()
        ws  = self.query_one("#workspace", WorkspaceConsole)

        if lo in ("/exit", "/quit"):
            self.exit(); return

        if lo == "/help":
            ws.write_info(self._help_text()); return

        if lo == "/clear":
            ws.clear_chat(); return

        if lo == "/cwd":
            ws.write_info(str(self.cwd)); return

        if lo == "/tokens":
            ws.write_info(f"~{self._chars // 4:,} tokens this session"); return

        if lo == "/tui-info":
            import textual
            ws.write_info(
                f"ElieAtch TUI v2  ·  QUANTUMTUI v0.5\n"
                f"Textual {textual.__version__}  ·  Python {sys.version.split()[0]}"
                f"  ·  psutil {'✓' if HAS_PSUTIL else '✗'}"
            ); return

        if lo.startswith("/cd"):
            arg = line[3:].strip()
            p   = (self.cwd / arg).resolve() if arg else Path.home()
            if p.is_dir():
                self.cwd = p; ws.write_info(f"→ {p}")
            else:
                ws.write_error(f"Not a directory: {p}")
            return

        if lo == "/providers":
            router = _get_router()
            ws.write_info(router.status_table()); return

        if lo == "/model" or lo.startswith("/model "):
            arg = line[6:].strip()
            if not arg:
                ws.write_info(f"Model: {self.model}"); return
            if arg == "list":
                parts = ["Qwen (CDP bridge):"]
                parts += [f"  {'→' if m == self.model else ' '} {m}" for m in KNOWN_MODELS]
                router = _get_router()
                avail = router.available()
                for prov, models in avail.items():
                    parts.append(f"\n{prov}:")
                    for m in models[:5]:
                        parts.append(f"  {'→' if m == self.model else ' '} {m}")
                    if len(models) > 5:
                        parts.append(f"    …{len(models)-5} more (/providers for full list)")
                ws.write_info("\n".join(parts)); return
            self.model = arg
            self._chat_id = None
            self._turns = 0
            self._router_messages = []
            self.query_one("#qh", QuantumHeader).update_stats(model=arg, provider="…")
            self.query_one("#status-line", QuantumStatusLine).update_state("READY", arg)
            ws.write_info(f"model → {arg}  (re-initialising session…)")
            self._init_session()
            return

        if line.startswith("!"):
            self._shell_cmd(line[1:].strip()); return

        if lo.startswith("/"):
            ws.write_error(f"Unknown command: {line}  ·  /help for list"); return

        if self._busy:
            ws.write_error("Agent is busy — please wait"); return
        if self._chat_id is None:
            ws.write_error("Session not ready yet"); return

        self._run_task(line)

    # ── agent task ────────────────────────────────────────────────────────

    def _run_task(self, task: str) -> None:
        self._busy    = True
        self._turns  += 1
        self._interrupt.clear()
        self._t_start = time.time()

        ws  = self.query_one("#workspace", WorkspaceConsole)
        ex  = self.query_one("#execution", ExecutionMatrix)
        em  = self.query_one("#explorer", ExplorerMatrix)

        ws.add_user_message(task)
        ws.start_agent_response()
        em.push_history(task)

        ex.set_plan(["Parse request", "Model Query", "Code Gen", "Security Review"])
        ex.mark_step(0, done=True)

        self._agent_work(task)

    @work(thread=True)
    def _agent_work(self, task: str) -> None:
        self.call_from_thread(self.post_message, AgentStateMsg("RUNNING", task))

        def _collect(gen) -> str:
            buf = ""; pending = ""
            for chunk in gen:
                if self._interrupt.is_set():
                    break
                buf += chunk; pending += chunk
                if len(pending) >= 12 or "\n" in pending:
                    self.call_from_thread(self.post_message, StreamChunk(pending))
                    pending = ""
            if pending:
                self.call_from_thread(self.post_message, StreamChunk(pending))
            return buf

        try:
            if self._is_qwen:
                from tools.qwen_bridge import chat_via_fetch_stream
                msg = (
                    f"{_SYS.format(root=_ROOT, tools=TOOLS_DOC)}\n\nUSER: {task}"
                    if self._turns == 1 else f"TASK: {task}"
                )
                # Try Qwen CDP; if it fails, permanently switch to router for this session
                _qwen_fallback = False
                _router_msgs: list[dict] = []
                try:
                    def _qwen_stream(m: str):
                        return _strip_preamble(
                            chat_via_fetch_stream(m, timeout=90, model=self.model, chat_id=self._chat_id)
                        )
                    text = _collect(_qwen_stream(msg))
                except Exception as qe:
                    _qwen_fallback = True
                    self.call_from_thread(
                        self.post_message,
                        StreamChunk(f"[Qwen CDP unavailable: {qe}  →  using router]\n\n")
                    )
                    router = _get_router()
                    _router_msgs = [
                        {"role": "system", "content": _SYS.format(root=_ROOT, tools=TOOLS_DOC)},
                        {"role": "user", "content": task},
                    ]
                    text = _collect(router.stream(self.model, "", messages=list(_router_msgs)))
                    _router_msgs.append({"role": "assistant", "content": text})
                self._chars += len(text)

                for _ in range(MAX_STEPS):
                    if self._interrupt.is_set(): break
                    parsed = _parse(text)
                    if parsed[0] in ('chat', 'final'):
                        elapsed = time.time() - self._t_start
                        tokens  = self._chars // 4
                        tps     = max(len(text) / 4 / max(elapsed, 0.1), 0.0)
                        self.call_from_thread(self.post_message, StatsMsg(tokens, elapsed, tps))
                        self.call_from_thread(self.post_message, AgentStateMsg("DONE"))
                        break
                    if parsed[0] == 'action':
                        _, tool_name, inp = parsed
                        self.call_from_thread(self.post_message, ToolCallMsg(tool_name, inp))
                        t0 = time.time()
                        fn = TOOLS.get(tool_name)
                        obs = fn(inp, cwd=self.cwd, session=None) if fn else f"Error: unknown tool '{tool_name}'. Available: {', '.join(TOOLS)}"
                        ok = fn is not None
                        self.call_from_thread(self.post_message, ToolResultMsg(tool_name, obs, time.time() - t0, ok))
                        obs_str = f"Observation: {obs}"
                        if _qwen_fallback:
                            _router_msgs.append({"role": "user", "content": obs_str})
                            text = _collect(router.stream(self.model, "", messages=list(_router_msgs)))
                            _router_msgs.append({"role": "assistant", "content": text})
                        else:
                            text = _collect(_qwen_stream(obs_str))
                        self._chars += len(text)
            else:
                router = _get_router()
                if self._turns == 1:
                    self._router_messages = [
                        {"role": "system", "content": _SYS.format(root=_ROOT, tools=TOOLS_DOC)},
                    ]
                self._router_messages.append({"role": "user", "content": task})

                def _rstream(messages: list[dict]):
                    return _strip_preamble(router.stream(self.model, "", messages=messages))

                text = _collect(_rstream(list(self._router_messages)))
                self._chars += len(text)
                self._router_messages.append({"role": "assistant", "content": text})

                for _ in range(MAX_STEPS):
                    if self._interrupt.is_set(): break
                    parsed = _parse(text)
                    if parsed[0] in ('chat', 'final'):
                        elapsed = time.time() - self._t_start
                        tokens  = self._chars // 4
                        tps     = max(len(text) / 4 / max(elapsed, 0.1), 0.0)
                        self.call_from_thread(self.post_message, StatsMsg(tokens, elapsed, tps))
                        self.call_from_thread(self.post_message, AgentStateMsg("DONE"))
                        break
                    if parsed[0] == 'action':
                        _, tool_name, inp = parsed
                        self.call_from_thread(self.post_message, ToolCallMsg(tool_name, inp))
                        t0 = time.time()
                        fn = TOOLS.get(tool_name)
                        obs = fn(inp, cwd=self.cwd, session=None) if fn else f"Error: unknown tool '{tool_name}'"
                        ok = fn is not None
                        self.call_from_thread(self.post_message, ToolResultMsg(tool_name, obs, time.time() - t0, ok))
                        obs_msg = f"Observation: {obs}"
                        self._router_messages.append({"role": "user", "content": obs_msg})
                        text = _collect(_rstream(list(self._router_messages)))
                        self._chars += len(text)
                        self._router_messages.append({"role": "assistant", "content": text})

            self.call_from_thread(self.post_message, AgentDone())

        except Exception as e:
            self.call_from_thread(self.post_message, AgentError(str(e)))

    # ── shell ─────────────────────────────────────────────────────────────

    def _shell_cmd(self, cmd: str) -> None:
        ws = self.query_one("#workspace", WorkspaceConsole)
        try:
            r = subprocess.run(
                ["powershell", "-NoProfile", "-Command", cmd],
                capture_output=True, text=True, timeout=30, cwd=str(self.cwd),
            )
            out = (r.stdout + r.stderr).strip() or "(no output)"
        except Exception as e:
            out = f"Error: {e}"
        for line in out.splitlines()[:25]:
            ws.write_info(line)

    # ── keyboard actions ──────────────────────────────────────────────────

    def action_toggle_left(self) -> None:
        self.query_one(ExplorerMatrix).toggle_collapse()

    def action_toggle_right(self) -> None:
        self.query_one(ExecutionMatrix).toggle_collapse()

    def action_focus_cmd(self) -> None:
        self.query_one(QuantumInput).focus_input()

    def action_clear_chat(self) -> None:
        self.query_one("#workspace", WorkspaceConsole).clear_chat()

    # ── help ──────────────────────────────────────────────────────────────

    def _help_text(self) -> str:
        rows = [
            ("/model [list|name]",  "switch AI model"),
            ("/providers",          "list all LLM providers"),
            ("/cwd",                "show working directory"),
            ("/cd <path>",          "change directory"),
            ("/tokens",             "session token count"),
            ("/tui-info",           "TUI version + status"),
            ("/clear",              "clear chat"),
            ("/exit",               "quit"),
            ("!<cmd>",              "shell pass-through"),
            ("Ctrl+B",              "toggle Explorer Matrix"),
            ("Ctrl+R",              "toggle Execution Matrix"),
            ("Ctrl+K / Esc",        "focus command bar"),
            ("Ctrl+L",              "clear chat"),
        ]
        header = "ElieAtch QUANTUMTUI v0.5 — Commands\n"
        body   = "\n".join(f"  {cmd:<22}  {desc}" for cmd, desc in rows)
        return header + body


# ══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8", errors="replace")
    import argparse
    ap = argparse.ArgumentParser(prog="elieatch-tui-v2")
    ap.add_argument("task", nargs="?", help="Optional first task")
    args = ap.parse_args()
    ElieAtchApp(first_task=args.task).run()


if __name__ == "__main__":
    main()
