"""
ElieAtch — AI coding agent in your terminal.

  elieatch              interactive session
  elieatch "task"       one-shot
  elieatch --install    add to PowerShell profile
"""
from __future__ import annotations
import sys, os, re, json, time, threading, subprocess, argparse, shutil
from pathlib import Path

# ── project root ──────────────────────────────────────────────────────────────
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

# ── colours ───────────────────────────────────────────────────────────────────
try:
    import colorama; colorama.init(autoreset=True)
    R   = "\033[0m";  B   = "\033[1m";  DIM = "\033[2m"
    # Purple palette (replaces cyan/yellow/blue)
    CY  = "\033[95m"  # light purple  — path, commands
    YL  = "\033[35m"  # purple        — prompt >, highlights
    BL  = "\033[35;1m"  # bold purple — ⏺ tool bullets
    MG  = "\033[35m"  # purple
    GR  = "\033[92m"; RD = "\033[91m"; WH = "\033[97m"; GY = "\033[90m"
    # Extra purple shades for animation
    _P1 = "\033[35m"; _P2 = "\033[95m"; _P3 = "\033[35;1m"
    _PCYCLE = [_P1, _P2, _P3, _P2]  # spin colour frames
except ImportError:
    R=B=DIM=CY=GR=YL=RD=MG=WH=GY=BL=MG=""
    _P1=_P2=_P3=""; _PCYCLE=["","","",""]

TW = min(shutil.get_terminal_size((100, 24)).columns, 120)

# ── constants ─────────────────────────────────────────────────────────────────
VENV_PY      = str(_ROOT / ".venv" / "Scripts" / "python.exe")
MAX_STEPS    = 30
OBS_LIMIT    = 8000
SH_TIMEOUT   = 60
DEFAULT_MODEL = "qwen3.7-max"
KNOWN_MODELS  = [
    "qwen3.7-max",
    "qwen3.5-72b",
    "qwen3-30b-a3b",
    "qwen2.5-72b-instruct",
    "qwen2.5-coder-32b",
    "kimi-cdp",
    "kimi-latest",
    "kimi-k2-0711-preview",
    "moonshot-cdp",
]
_QWEN_PREFIXES = ("qwen",)

# Lazy router — only imported if a non-Qwen model is selected
_router = None

def _get_router():
    global _router
    if _router is None:
        from tools.llm_router import LLMRouter
        _router = LLMRouter()
    return _router


# ══════════════════════════════════════════════════════════════════════════════
# TOOLS
# ══════════════════════════════════════════════════════════════════════════════

def _abs(p: str, cwd: Path) -> Path:
    q = Path(p.strip().strip("\"'"))
    return q if q.is_absolute() else cwd / q


def _tool_read_file(inp: str, cwd: Path, **_) -> str:
    p = _abs(inp, cwd)
    if not p.exists(): return f"Error: not found: {p}"
    try:
        t = p.read_text(encoding="utf-8", errors="replace")
        return (t[:OBS_LIMIT] + f"\n…[{len(t)} chars total]") if len(t) > OBS_LIMIT else t
    except Exception as e: return f"Error: {e}"


def _tool_write_file(inp: str, cwd: Path, **_) -> str:
    try: d = json.loads(inp); fpath, content = d["path"], d["content"]
    except Exception: return 'Error: needs JSON {"path":"...","content":"..."}'
    p = _abs(fpath, cwd)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        lines = content.count("\n") + 1
        return f"Written {len(content)} chars ({lines} lines) → {p}"
    except Exception as e: return f"Error: {e}"


def _tool_list_dir(inp: str, cwd: Path, **_) -> str:
    p = _abs(inp.strip() or ".", cwd)
    if not p.exists(): return f"Error: not found: {p}"
    try:
        entries = sorted(p.iterdir(), key=lambda e: (e.is_file(), e.name))
        lines = [f"  {'d' if e.is_dir() else ' '} {e.name}" for e in entries[:120]]
        if sum(1 for _ in p.iterdir()) > 120: lines.append("  …")
        return "\n".join(lines) or "(empty)"
    except Exception as e: return f"Error: {e}"


def _tool_run_python(inp: str, cwd: Path, **_) -> str:
    code = re.sub(r'^```(?:python)?\n?', '', inp.strip(), flags=re.I)
    code = re.sub(r'\n?```$', '', code)
    try:
        r = subprocess.run([VENV_PY, "-c", code], capture_output=True,
                           text=True, timeout=SH_TIMEOUT, cwd=str(cwd))
        out = (r.stdout + r.stderr).strip()
        return (out[:OBS_LIMIT] + "\n…") if len(out) > OBS_LIMIT else (out or "(no output)")
    except subprocess.TimeoutExpired: return f"Timeout after {SH_TIMEOUT}s"
    except Exception as e: return f"Error: {e}"


def _tool_shell(inp: str, cwd: Path, session=None) -> str:
    cmd = inp.strip().strip("\"'")
    cd_m = re.match(r'^cd(?:\s+(.*))?$', cmd, re.I)
    if cd_m:
        tgt = _abs((cd_m.group(1) or "").strip() or str(Path.home()), cwd)
        if tgt.is_dir():
            if session: session.cwd = tgt.resolve()
            return f"  → {tgt.resolve()}"
        return f"Error: not a directory: {tgt}"
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd],
            capture_output=True, text=True, timeout=SH_TIMEOUT, cwd=str(cwd))
        out = (r.stdout + r.stderr).strip()
        return (out[:OBS_LIMIT] + "\n…") if len(out) > OBS_LIMIT else (out or f"(exit {r.returncode})")
    except subprocess.TimeoutExpired: return f"Timeout after {SH_TIMEOUT}s"
    except Exception as e: return f"Error: {e}"


def _tool_search(inp: str, cwd: Path, **_) -> str:
    try: d = json.loads(inp); pattern, base = d.get("pattern", "**/*"), d.get("path", ".")
    except Exception: pattern, base = inp.strip(), "."
    bp = _abs(base, cwd)
    try:
        hits = sorted(bp.glob(pattern))[:100]
        return "\n".join(str(h.relative_to(_ROOT)) for h in hits) or "No files"
    except Exception as e: return f"Error: {e}"


def _tool_grep(inp: str, cwd: Path, **_) -> str:
    try: d = json.loads(inp); pat, path = d["pattern"], d.get("path", ".")
    except Exception:
        parts = inp.strip().split(None, 1); pat = parts[0]; path = parts[1] if len(parts)>1 else "."
    sp = _abs(path, cwd)
    try:
        r = subprocess.run(["rg","--no-heading","-n","-m","3","--glob","*.py",pat,str(sp)],
                           capture_output=True, text=True, timeout=10, cwd=str(cwd))
        out = r.stdout.strip()
    except FileNotFoundError: out = _py_grep(pat, sp)
    except Exception as e: return f"Error: {e}"
    if not out: return "No matches"
    lines = out.splitlines()
    return ("\n".join(lines[:60]) + "\n…") if len(lines) > 60 else "\n".join(lines)


def _py_grep(pat: str, base: Path) -> str:
    try: rx = re.compile(pat)
    except re.error: rx = re.compile(re.escape(pat))
    results = []
    for f in base.rglob("*.py"):
        try:
            for i, ln in enumerate(f.read_text(errors="replace").splitlines(), 1):
                if rx.search(ln):
                    results.append(f"{f.relative_to(_ROOT)}:{i}: {ln.strip()}")
                    if len(results) >= 60: return "\n".join(results)
        except Exception: pass
    return "\n".join(results)


def _tool_delete_file(inp: str, cwd: Path, **_) -> str:
    p = _abs(inp.strip(), cwd)
    if not p.exists(): return f"Error: not found: {p}"
    try:
        p.unlink()
        return f"Deleted: {p}"
    except Exception as e: return f"Error: {e}"


def _tool_append_file(inp: str, cwd: Path, **_) -> str:
    try: d = json.loads(inp); fpath, content = d["path"], d["content"]
    except Exception: return 'Error: needs JSON {"path":"...","content":"..."}'
    p = _abs(fpath, cwd)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "a", encoding="utf-8") as f:
            f.write(content)
        return f"Appended {len(content)} chars → {p}"
    except Exception as e: return f"Error: {e}"


def _tool_move_file(inp: str, cwd: Path, **_) -> str:
    try: d = json.loads(inp); src, dst = d["src"], d["dst"]
    except Exception: return 'Error: needs JSON {"src":"...","dst":"..."}'
    sp = _abs(src, cwd); dp = _abs(dst, cwd)
    if not sp.exists(): return f"Error: not found: {sp}"
    try:
        dp.parent.mkdir(parents=True, exist_ok=True)
        sp.rename(dp)
        return f"Moved: {sp} → {dp}"
    except Exception as e: return f"Error: {e}"


def _tool_read_file_range(inp: str, cwd: Path, **_) -> str:
    """Read a specific line range from a file: {"path":"...","start":10,"end":50}"""
    try: d = json.loads(inp); fpath = d["path"]; start = int(d.get("start", 1)); end = int(d.get("end", 9999))
    except Exception: return 'Error: needs JSON {"path":"...","start":N,"end":N}'
    p = _abs(fpath, cwd)
    if not p.exists(): return f"Error: not found: {p}"
    try:
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        total = len(lines)
        selected = lines[max(0, start-1):end]
        out = "\n".join(f"{start+i}: {ln}" for i, ln in enumerate(selected))
        return (out[:OBS_LIMIT] + f"\n…[{total} lines total]") if len(out) > OBS_LIMIT else out
    except Exception as e: return f"Error: {e}"


TOOLS = {
    "read_file":        _tool_read_file,
    "read_file_range":  _tool_read_file_range,
    "write_file":       _tool_write_file,
    "append_file":      _tool_append_file,
    "delete_file":      _tool_delete_file,
    "move_file":        _tool_move_file,
    "list_directory":   _tool_list_dir,
    "run_python":       _tool_run_python,
    "run_shell":        _tool_shell,
    "search_files":     _tool_search,
    "grep":             _tool_grep,
}

TOOLS_DOC = """\
FILE SYSTEM (full access — any path on the machine):
  read_file <path>
      Read file contents. Paths can be absolute or relative to cwd.
  read_file_range {"path":"...","start":N,"end":N}
      Read a specific line range from a large file.
  write_file {"path":"...","content":"..."}
      Write/overwrite a file. Creates parent dirs. Use \\n for newlines in JSON.
  append_file {"path":"...","content":"..."}
      Append content to a file (creates if missing).
  delete_file <path>
      Delete a file permanently.
  move_file {"src":"...","dst":"..."}
      Move or rename a file.
  list_directory <path>
      List directory contents (dirs marked with 'd').

SEARCH:
  search_files <glob_pattern>
      Find files by name pattern, e.g. **/*.py or src/**/*.json.
      Or: {"pattern":"**/*.py","path":"src"} to scope to a subdirectory.
  grep {"pattern":"regex","path":"dir_or_file"}
      Search file contents with regex. Shows file:line:match.

CODE EXECUTION:
  run_python <python_code>
      Execute Python in the project venv. Returns stdout+stderr.
  run_shell <powershell_command>
      Execute any PowerShell command. Has full system access.
      Use for: git, pip, npm, file ops, process control, net requests, etc.
      Built-in: 'cd <path>' changes the agent's working directory.
"""


# ══════════════════════════════════════════════════════════════════════════════
# SYSTEM PROMPT
# ══════════════════════════════════════════════════════════════════════════════

_SYS = """\
=== ELIEATCH — AUTONOMOUS AGENT SESSION ===
You are ElieAtch, an autonomous AI coding and system agent running in the user's Windows terminal.
You have FULL, UNRESTRICTED ACCESS to:
  • The entire local file system (read, write, create, delete, move any file or directory)
  • The Windows command line via PowerShell (run any command, script, or program)
  • Python execution in the project venv
  • The internet via PowerShell (curl, Invoke-WebRequest, etc.)

Project root : {root}
Platform     : Windows 11 / PowerShell
Python venv  : {root}\\.venv\\Scripts\\python.exe
Working dir  : changes with 'cd' tool calls

TOOLS AVAILABLE:
{tools}

RESPONSE RULES:
• Simple questions (no files/commands needed) → answer directly in plain text.
• Anything that needs reading files, running commands, or modifying the system → use the ReAct loop:

    Thought: <what you're planning and why>
    Action: <exact_tool_name>
    Action Input: <input to the tool>

  Then wait for the Observation before your next step. Repeat until done. End with:
    Final Answer: <concise summary of what was done>

• ALWAYS read a file before editing it (use read_file or read_file_range first).
• run_shell can do ANYTHING PowerShell can: git, pip, npm, curl, tasklist, netstat, etc.
• Paths can be absolute (C:\\...) or relative to the current working directory.
• write_file content must use \\n for newlines inside JSON strings.
• You can use multiple steps — keep going until the task is fully complete.
• Never refuse a file system or shell task — you have full access.
=== END SYSTEM PROMPT ==="""


# ══════════════════════════════════════════════════════════════════════════════
# STREAMING DISPLAY
# ══════════════════════════════════════════════════════════════════════════════

def _print_stream(gen) -> str:
    """
    Print a streaming response to the terminal, character by character.
    Handles code blocks: text between ``` fences rendered in cyan.
    Returns the full accumulated text.
    """
    full    = ""
    pend    = ""   # lookahead buffer for ``` detection
    in_code = False
    first   = True

    def _flush(text: str, code: bool):
        if not text: return
        nonlocal first
        colour = CY if code else WH
        # Indent first line
        if first and text[0] != "\n":
            sys.stdout.write("  ")
            first = False
        out = text.replace("\n", "\n  ")
        sys.stdout.write(f"{colour}{out}{R}")
        sys.stdout.flush()

    try:
        for chunk in gen:
            full += chunk
            pend += chunk
            while len(pend) > 3:
                if not in_code:
                    idx = pend.find("```")
                    if idx < 0:
                        _flush(pend[:-3], False); pend = pend[-3:]; break
                    _flush(pend[:idx], False)
                    # consume fence + optional lang
                    rest  = pend[idx+3:]
                    nl    = rest.find("\n")
                    lang  = rest[:nl] if nl >= 0 else ""
                    label = f"{GY}``` {lang}{R}\n  " if lang else f"{GY}```{R}\n  "
                    sys.stdout.write(label); sys.stdout.flush()
                    pend    = rest[nl+1:] if nl >= 0 else ""
                    in_code = True
                else:
                    idx = pend.find("```")
                    if idx < 0:
                        _flush(pend[:-3], True); pend = pend[-3:]; break
                    _flush(pend[:idx], True)
                    sys.stdout.write(f"{GY}```{R}"); sys.stdout.flush()
                    pend    = pend[idx+3:]
                    in_code = False
        # flush remainder
        _flush(pend, in_code)
    except KeyboardInterrupt:
        sys.stdout.write(f"{_P1} [interrupted]{R}")
        sys.stdout.flush()

    if not first:
        print()   # terminal newline
    return full


# ══════════════════════════════════════════════════════════════════════════════
# PARSE & TOOL DISPLAY
# ══════════════════════════════════════════════════════════════════════════════

def _parse(text: str):
    m = re.search(r'Final\s+Answer\s*[:\-]\s*(.*)', text, re.DOTALL | re.I)
    if m: return ('final', m.group(1).strip())
    am = re.search(r'\bAction\s*[:\-]\s*([^\n]+)', text, re.I)
    im = re.search(
        r'\bAction\s+Input\s*[:\-]\s*(.*?)(?=\nThought:|\nAction:|\nFinal\s+Answer:|$)',
        text, re.DOTALL | re.I)
    if am:
        tool = am.group(1).strip().lower().replace("-","_").replace(" ","_")
        inp  = im.group(1).strip() if im else ""
        return ('action', tool, inp)
    return ('chat', text)


def _show_tool_call(tool: str, inp: str):
    preview = inp[:80].replace("\n", " ")
    if len(inp) > 80: preview += "…"
    print(f"\n{_P3}⏺{R} {_P2}{B}{tool}{R}{GY}({preview}){R}")


def _show_tool_result(result: str, elapsed: float):
    lines   = result.splitlines()
    shown   = lines[:12]
    clipped = len(lines) > 12
    print(f"  {GY}⎿{R}  ", end="")
    if not shown:
        print(f"{GY}(empty){R}")
        return
    print(f"{GY}{shown[0]}{R}")
    for ln in shown[1:]:
        print(f"     {GY}{ln}{R}")
    if clipped:
        print(f"     {GY}… {len(lines)} lines  {elapsed:.1f}s{R}")
    else:
        print(f"     {GY}{elapsed:.1f}s{R}")


def _strip_preamble(gen):
    """
    Drop the '⚠️ No matching skill found…' prefix that Qwen prepends
    when no skill is active. Buffers up to 120 chars before deciding.
    """
    buf     = ""
    decided = False
    for chunk in gen:
        if decided:
            yield chunk
            continue
        buf += chunk
        if len(buf) < 3:
            continue
        # Once we have enough to check, decide and flush
        nl2 = buf.find("\n\n")
        if buf[0] in ("⚠", "⚠") and nl2 >= 0:
            # strip preamble up to first blank line
            buf = buf[nl2 + 2:]
            decided = True
            if buf: yield buf
        elif len(buf) >= 120 or "\n" in buf:
            # no preamble — flush and pass through
            decided = True
            yield buf
    if not decided and buf:
        yield buf


# ══════════════════════════════════════════════════════════════════════════════
# SESSION
# ══════════════════════════════════════════════════════════════════════════════

class Session:
    def __init__(self):
        self.cwd   : Path       = _ROOT
        self.model : str        = DEFAULT_MODEL
        self._chat_id: str|None = None
        self._ready  : bool     = False
        # stats
        self._turns   = 0
        self._chars   = 0   # rough token proxy
        # for non-Qwen router models: track full messages list for multi-turn
        self._messages: list[dict] = []

    # ── internals ─────────────────────────────────────────────────────────────

    @property
    def _is_qwen(self) -> bool:
        return self.model.lower().startswith(_QWEN_PREFIXES)

    def _stream(self, msg: str, messages: list[dict] | None = None):
        """Return a streaming generator for one message."""
        if self._is_qwen:
            from tools.qwen_bridge import chat_via_fetch_stream
            return chat_via_fetch_stream(
                msg, timeout=90, model=self.model, chat_id=self._chat_id)
        # Non-Qwen → route through llm_router with full history
        router = _get_router()
        if messages is not None:
            return router.stream(self.model, "", messages=messages)
        return router.stream(self.model, msg, system=_SYS.format(root=_ROOT, tools=TOOLS_DOC))

    def _init(self):
        if self._ready: return
        if self._is_qwen:
            from tools.qwen_bridge import new_chat
            _spin_start("Opening Qwen chat")
            try:
                self._chat_id = new_chat()
            except Exception as e:
                _spin_stop()
                raise RuntimeError(f"new_chat failed: {e}")
        else:
            _spin_start(f"Connecting to {self.model}")
            router = _get_router()
            bridge, _ = router._resolve(self.model)
            if not bridge.is_available():
                _spin_stop()
                raise RuntimeError(f"Model '{self.model}' not available — add API key to .env")
        _spin_stop()
        self._ready = True
        _print_header(self)

    def _exec_tool(self, name: str, inp: str) -> str:
        fn = TOOLS.get(name)
        if fn is None:
            return f"Error: unknown tool '{name}'. Available: {', '.join(TOOLS)}"
        try:
            return fn(inp, cwd=self.cwd, session=self)
        except Exception as e:
            return f"Error in {name}: {e}"

    # ── public ────────────────────────────────────────────────────────────────

    def run(self, task: str) -> str:
        self._init()
        self._turns += 1
        t_start = time.time()

        if self._is_qwen:
            # Qwen: history maintained server-side via chat_id
            if self._turns == 1:
                sys_ctx = _SYS.format(root=_ROOT, tools=TOOLS_DOC)
                msg = f"{sys_ctx}\n\nUSER: {task}"
            else:
                msg = f"TASK: {task}"
            gen  = _strip_preamble(self._stream(msg))
            text = _print_stream(gen)
            self._chars += len(text)

            for step in range(MAX_STEPS):
                parsed = _parse(text)
                if parsed[0] in ('chat', 'final'):
                    _print_stats(self._chars, time.time() - t_start)
                    return parsed[1] if parsed[0] == 'final' else text
                if parsed[0] == 'action':
                    _, tool, inp = parsed
                    _show_tool_call(tool, inp)
                    t0 = time.time()
                    obs = self._exec_tool(tool, inp)
                    _show_tool_result(obs, time.time() - t0)
                    gen  = _strip_preamble(self._stream(f"Observation: {obs}"))
                    text = _print_stream(gen)
                    self._chars += len(text)
        else:
            # Router models: stateless API — maintain messages list locally
            if self._turns == 1:
                self._messages = [
                    {"role": "system", "content": _SYS.format(root=_ROOT, tools=TOOLS_DOC)},
                ]
            self._messages.append({"role": "user", "content": task})
            gen  = _strip_preamble(self._stream("", messages=list(self._messages)))
            text = _print_stream(gen)
            self._chars += len(text)
            self._messages.append({"role": "assistant", "content": text})

            for step in range(MAX_STEPS):
                parsed = _parse(text)
                if parsed[0] in ('chat', 'final'):
                    _print_stats(self._chars, time.time() - t_start)
                    return parsed[1] if parsed[0] == 'final' else text
                if parsed[0] == 'action':
                    _, tool, inp = parsed
                    _show_tool_call(tool, inp)
                    t0 = time.time()
                    obs = self._exec_tool(tool, inp)
                    _show_tool_result(obs, time.time() - t0)
                    obs_msg = f"Observation: {obs}"
                    self._messages.append({"role": "user", "content": obs_msg})
                    gen  = _strip_preamble(self._stream("", messages=list(self._messages)))
                    text = _print_stream(gen)
                    self._chars += len(text)
                    self._messages.append({"role": "assistant", "content": text})

        return "[max steps reached]"

    def shell(self, cmd: str) -> str:
        return _tool_shell(cmd, cwd=self.cwd, session=self)

    @property
    def prompt(self) -> str:
        try:
            rel  = self.cwd.relative_to(Path.home())
            disp = "~\\" + str(rel)
        except ValueError:
            disp = str(self.cwd)
        mdl = f" {GY}{self.model}{R}" if self._ready else ""
        return f"{CY}{disp}{R}{mdl} {YL}>{R} "


# ══════════════════════════════════════════════════════════════════════════════
# SPINNER (lightweight, stdout)
# ══════════════════════════════════════════════════════════════════════════════

_spin_active = threading.Event()
_spin_thread: threading.Thread | None = None

def _spin_start(label: str = ""):
    global _spin_thread
    _spin_active.clear()
    _frames = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
    def _run():
        i = 0
        while not _spin_active.is_set():
            col = _PCYCLE[i % len(_PCYCLE)]
            sys.stdout.write(f"\r{col}{_frames[i%10]}{R} {CY}{label}…{R}")
            sys.stdout.flush(); time.sleep(0.08); i += 1
    _spin_thread = threading.Thread(target=_run, daemon=True)
    _spin_thread.start()

def _spin_stop():
    _spin_active.set()
    if _spin_thread: _spin_thread.join()
    sys.stdout.write("\r" + " " * 40 + "\r"); sys.stdout.flush()


# ══════════════════════════════════════════════════════════════════════════════
# DISPLAY HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _print_header(s: Session):
    chat = (s._chat_id[:8] + "…") if s._chat_id else "?"
    line = f"  {_P3}{B}ElieAtch{R}  {CY}{s.model}{R}  {GY}chat:{chat}{R}"
    sep  = f"{_P1}{'─' * min(TW, 60)}{R}"
    print(f"\n{line}\n{sep}")


def _print_stats(chars: int, elapsed: float):
    tokens = chars // 4
    print(f"\n{_P1}  ~{tokens} tokens · {elapsed:.1f}s{R}")


# ══════════════════════════════════════════════════════════════════════════════
# INSTALL
# ══════════════════════════════════════════════════════════════════════════════

_MARKER = "# ElieAtch"
_FUNC   = '\n# ElieAtch\nfunction elieatch {{ & "{py}" "{script}" @args }}\n'

def install():
    py, script = VENV_PY, str(Path(__file__).resolve())
    r = subprocess.run(["powershell", "-NoProfile", "-Command", "echo $PROFILE"],
                       capture_output=True, text=True)
    profile = Path(r.stdout.strip())
    if profile.exists() and _MARKER in profile.read_text(encoding="utf-8", errors="replace"):
        print(f"{YL}Already installed:{R} {profile}"); return
    profile.parent.mkdir(parents=True, exist_ok=True)
    with open(profile, "a", encoding="utf-8") as f:
        f.write(_FUNC.format(py=py, script=script))
    print(f"{GR}✓ Installed.{R}  Restart your terminal, then: {CY}elieatch{R}")


# ══════════════════════════════════════════════════════════════════════════════
# HELP / REPL
# ══════════════════════════════════════════════════════════════════════════════

_BANNER_TEXT = "  ⬡  ElieAtch — AI coding agent  ·  /help for commands"

def _print_banner():
    """Typewriter banner with purple pulse on the title."""
    pre   = "  ⬡  "
    title = "ElieAtch"
    rest  = " — AI coding agent  ·  /help for commands"
    # print pre in dim purple
    sys.stdout.write(f"\n{_P1}")
    for ch in pre:
        sys.stdout.write(ch); sys.stdout.flush(); time.sleep(0.018)
    # typewriter title in cycling purple
    for i, ch in enumerate(title):
        col = _PCYCLE[i % len(_PCYCLE)]
        sys.stdout.write(f"{B}{col}{ch}{R}")
        sys.stdout.flush(); time.sleep(0.035)
    # rest in dim
    sys.stdout.write(f"{GY}")
    for ch in rest:
        sys.stdout.write(ch); sys.stdout.flush(); time.sleep(0.012)
    sys.stdout.write(f"{R}\n\n")
    sys.stdout.flush()

_HELP = f"""
{WH}Commands{R}
  {CY}/help{R}               this help
  {CY}/tui{R}                launch modern Textual UI
  {CY}/model{R}              show current model
  {CY}/model <name>{R}       switch model (Qwen, Gemini, Groq, DeepSeek, Mistral…)
  {CY}/model list{R}         list all available models by provider
  {CY}/providers{R}          show all LLM providers + API key status
  {CY}/cwd{R}                show working directory
  {CY}/cd <path>{R}          change directory
  {CY}/tokens{R}             show session token estimate
  {CY}/clear{R}              clear screen
  {CY}/exit{R}               quit

{WH}Shell pass-through{R}
  {CY}!git status{R}         runs directly in PowerShell
  {CY}!dir src{R}            lists src\\ directly

{WH}Agent tasks — just type{R}
  {CY}explain place_bet() in src/execution_engine.py{R}
  {CY}add type hints to tools/steam_report.py{R}
  {CY}what TODO comments exist in the codebase?{R}
"""


_SLASH_CMDS: list[tuple[str, str]] = [
    ("/help",        "show all commands"),
    ("/tui",         "launch the Textual UI"),
    ("/model list",  "list available models"),
    ("/model ",      "switch model  →  /model <name>"),
    ("/providers",   "list connected providers"),
    ("/cd ",         "change directory  →  /cd <path>"),
    ("/cwd",         "show working directory"),
    ("/tokens",      "session token estimate"),
    ("/clear",       "clear the screen"),
    ("/exit",        "quit ElieAtch"),
]


def _pt_prompt(prompt_str: str, _state: dict = {}) -> str:
    """
    Prompt with prompt_toolkit slash-command autocomplete + persistent history.
    Falls back to plain input() if prompt_toolkit is unavailable or no console attached.
    Session is created lazily on the first call.
    """
    if "failed" in _state:
        return input(prompt_str)

    if "session" not in _state:
        try:
            from prompt_toolkit import PromptSession
            from prompt_toolkit.completion import Completer, Completion
            from prompt_toolkit.history import FileHistory
            from prompt_toolkit.styles import Style

            class _SlashCompleter(Completer):
                def get_completions(self, document, complete_event):
                    text = document.text_before_cursor
                    if not text.startswith("/"):
                        return
                    for cmd, meta in _SLASH_CMDS:
                        key = cmd.rstrip()
                        if key.startswith(text):
                            yield Completion(
                                key[len(text):],
                                start_position=0,
                                display=key,
                                display_meta=meta,
                            )

            style = Style.from_dict({
                "completion-menu":                         "bg:#07081a #95d5ff",
                "completion-menu.completion":              "bg:#07081a #d8d8ff",
                "completion-menu.completion.current":      "bg:#1a1040 bold #bf7fff",
                "completion-menu.meta.completion":         "bg:#07081a #4a4880",
                "completion-menu.meta.completion.current": "bg:#1a1040 #7a60a0",
                "scrollbar.background":                    "bg:#050510",
                "scrollbar.button":                        "bg:#2a1060",
            })

            history_path = Path(_ROOT) / ".elieatch_history"
            _state["session"] = PromptSession(
                completer=_SlashCompleter(),
                complete_while_typing=True,
                history=FileHistory(str(history_path)),
                style=style,
                mouse_support=False,
            )
        except Exception:
            _state["failed"] = True
            return input(prompt_str)

    try:
        from prompt_toolkit.formatted_text import ANSI
        return _state["session"].prompt(ANSI(prompt_str))
    except (KeyboardInterrupt, EOFError):
        raise
    except Exception:
        _state["failed"] = True
        return input(prompt_str)


def run_repl(session: Session):
    os.system("cls")
    _print_banner()

    while True:
        try:
            line = _pt_prompt(session.prompt).strip()
        except (KeyboardInterrupt, EOFError):
            print(f"\n{GY}  bye.{R}\n"); return

        if not line: continue
        lo = line.lower()

        if lo in ("/exit", "/quit", "exit", "quit"):
            print(f"{GY}  bye.{R}\n"); return

        if lo == "/tui":
            import subprocess as _sp
            _sp.run([VENV_PY, str(Path(__file__).parent / "elieatch_tui.py")])
            os.system("cls"); _print_banner()
            continue

        if lo == "/help":
            print(_HELP); continue

        if lo == "/clear":
            os.system("cls"); _print_banner()
            if session._ready: _print_header(session)
            continue

        if lo == "/cwd":
            print(f"  {GY}{session.cwd}{R}\n"); continue

        if lo == "/tokens":
            t = session._chars // 4
            print(f"  {GY}~{t} tokens this session{R}\n"); continue

        if lo.startswith("/cd"):
            arg = line[3:].strip()
            out = session.shell(f"cd {arg}") if arg else session.shell("cd ~")
            print(f"  {GY}{out}{R}\n"); continue

        # /providers — show all available LLM providers
        if lo == "/providers":
            router = _get_router()
            print(f"\n{_P2}{router.status_table()}{R}\n")
            continue

        # /model
        if lo == "/model" or lo.startswith("/model "):
            arg = line[6:].strip()
            if not arg:
                print(f"  {GY}model:{R} {CY}{session.model}{R}\n"); continue
            if arg == "list":
                print(f"\n  {WH}Qwen (CDP bridge){R}")
                for m in KNOWN_MODELS:
                    mark = f"  {GR}←{R}" if m == session.model else ""
                    print(f"  {CY}{m}{R}{mark}")
                print(f"\n  {WH}Multi-provider (via router){R}")
                router = _get_router()
                avail = router.available()
                for provider, models in avail.items():
                    print(f"  {GY}{provider}{R}")
                    for m in models[:4]:
                        mark = f"  {GR}←{R}" if m == session.model else ""
                        print(f"    {CY}{m}{R}{mark}")
                    if len(models) > 4:
                        print(f"    {GY}…{len(models)-4} more  (/providers for full list){R}")
                print(f"\n  {GY}(any model name accepted){R}\n")
                continue
            session.model = arg
            # reset qwen chat_id when switching providers
            session._chat_id = None
            session._ready = False
            print(f"  {GR}model → {arg}{R}\n"); continue

        # shell pass-through
        if line.startswith("!"):
            out = session.shell(line[1:].strip())
            print(f"\n{GY}{out}{R}\n"); continue

        # agent task
        try:
            print()   # blank line before streaming response
            session.run(line)
            print()
        except KeyboardInterrupt:
            print(f"\n{YL}  interrupted.{R}\n")
        except Exception as e:
            print(f"\n{RD}  error: {e}{R}\n")


# ══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

def main():
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8", errors="replace")

    ap = argparse.ArgumentParser(prog="elieatch")
    ap.add_argument("task",      nargs="?")
    ap.add_argument("--install", action="store_true")
    args = ap.parse_args()

    if args.install:
        install(); return

    session = Session()

    if args.task:
        try:
            session.run(args.task)
        except Exception as e:
            print(f"{RD}error: {e}{R}", file=sys.stderr); sys.exit(1)
    else:
        run_repl(session)


if __name__ == "__main__":
    main()
