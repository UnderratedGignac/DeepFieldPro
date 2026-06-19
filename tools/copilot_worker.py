"""
AI worker — Microsoft Copilot via the unofficial Sydney API (sydney-py).

Auth: browser session cookie (_U) from copilot.microsoft.com — no API key needed.
Set BING_U_COOKIE in .env.

How to get your cookie:
  1. Open Edge/Chrome → go to https://copilot.microsoft.com
  2. Sign in with your Microsoft account
  3. F12 → Application → Cookies → copilot.microsoft.com
  4. Copy the value of the "_U" cookie
  5. Add to .env:  BING_U_COOKIE=<value>

Sydney has no native function calling, so this worker uses a ReAct loop:
  model outputs  TOOL: <name> / INPUT: <json>  → we execute → feed result back
  until model outputs  FINAL: <answer>

Usage:
    from tools.copilot_worker import run_task, run_build_task, WorkerResult

    r = run_task("List files in tools/")
    print(r.text)

    r = run_build_task("Add type hints to src/dfp_config.py")
    print(r.text)
"""

import asyncio
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

_PROJECT_ROOT = Path(r"C:\Users\Elie\DeepFieldPro")
_VENV_PYTHON  = str(_PROJECT_ROOT / ".venv" / "Scripts" / "python.exe")


@dataclass
class WorkerResult:
    text: str
    ok: bool
    error: str = ""
    timing_s: float = 0.0
    tool_calls: int = 0


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

def _read_file(path: str) -> str:
    p = Path(path)
    if not p.is_absolute():
        p = _PROJECT_ROOT / path
    if not p.exists():
        return f"ERROR: file not found: {p}"
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return f"ERROR: {e}"


def _write_file(path: str, content: str) -> str:
    p = Path(path)
    if not p.is_absolute():
        p = _PROJECT_ROOT / path
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return f"OK: wrote {len(content)} chars to {p}"
    except Exception as e:
        return f"ERROR: {e}"


def _list_directory(path: str = ".") -> str:
    p = Path(path)
    if not p.is_absolute():
        p = _PROJECT_ROOT / path
    if not p.exists():
        return f"ERROR: directory not found: {p}"
    try:
        entries = sorted(p.iterdir(), key=lambda x: (x.is_file(), x.name))
        return "\n".join(
            f"{'[DIR] ' if e.is_dir() else '[FILE]'} {e.name}" for e in entries
        ) or "(empty)"
    except Exception as e:
        return f"ERROR: {e}"


def _run_python(code: str) -> str:
    try:
        result = subprocess.run(
            [_VENV_PYTHON, "-c", code],
            capture_output=True, text=True, timeout=30,
            cwd=str(_PROJECT_ROOT),
        )
        parts = []
        if result.stdout:
            parts.append(f"STDOUT:\n{result.stdout[-4000:]}")
        if result.stderr:
            parts.append(f"STDERR:\n{result.stderr[-2000:]}")
        if result.returncode != 0:
            parts.append(f"exit_code={result.returncode}")
        return "\n".join(parts) or "(no output)"
    except subprocess.TimeoutExpired:
        return "ERROR: timeout after 30s"
    except Exception as e:
        return f"ERROR: {e}"


def _run_shell(command: str) -> str:
    try:
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True, timeout=30,
            cwd=str(_PROJECT_ROOT),
        )
        parts = []
        if result.stdout:
            parts.append(result.stdout[-4000:])
        if result.stderr:
            parts.append(f"STDERR: {result.stderr[-2000:]}")
        if result.returncode != 0:
            parts.append(f"exit_code={result.returncode}")
        return "\n".join(parts) or "(no output)"
    except subprocess.TimeoutExpired:
        return "ERROR: timeout after 30s"
    except Exception as e:
        return f"ERROR: {e}"


_TOOL_FNS = {
    "read_file":      lambda a: _read_file(a.get("path", "")),
    "write_file":     lambda a: _write_file(a.get("path", ""), a.get("content", "")),
    "list_directory": lambda a: _list_directory(a.get("path", ".")),
    "run_python":     lambda a: _run_python(a.get("code", "")),
    "run_shell":      lambda a: _run_shell(a.get("command", "")),
}


# ---------------------------------------------------------------------------
# ReAct parser
# ---------------------------------------------------------------------------

def _parse_tool_call(text: str):
    """Return (tool_name, args_dict) if a TOOL/INPUT block is present, else (None, None)."""
    tool_m  = re.search(r"TOOL:\s*(\w+)", text, re.IGNORECASE)
    input_m = re.search(r"INPUT:\s*(\{.*?\})", text, re.DOTALL | re.IGNORECASE)
    if not (tool_m and input_m):
        return None, None
    try:
        return tool_m.group(1).strip().lower(), json.loads(input_m.group(1))
    except json.JSONDecodeError:
        return tool_m.group(1).strip().lower(), {}


def _extract_final(text: str) -> str | None:
    """Return the text after FINAL: if present."""
    m = re.search(r"FINAL:\s*(.*)", text, re.DOTALL | re.IGNORECASE)
    return m.group(1).strip() if m else None


# ---------------------------------------------------------------------------
# System prompt injected as the first user turn
# ---------------------------------------------------------------------------

_SYSTEM = """\
You are an autonomous coding agent for the DeepFieldPro project.
Project root: C:/Users/Elie/DeepFieldPro
Stack: Python 3.12, Flask, SQLite, Windows, venv at .venv/

You have these tools available:

  read_file(path)            — read a file from disk
  write_file(path, content)  — write/overwrite a file
  list_directory(path)       — list directory contents
  run_python(code)           — execute Python code in the project venv
  run_shell(command)         — run a shell command in the project root

STRICT OUTPUT FORMAT — follow this exactly:

To call a tool:
  TOOL: <tool_name>
  INPUT: {"arg": "value"}

When you have your final answer:
  FINAL: <your answer here>

Rules:
- Call ONE tool per response, then wait for the result.
- After receiving a tool result, call the next tool or output FINAL.
- Never output FINAL and a TOOL call in the same response.
- Do not explain your reasoning outside the TOOL/INPUT/FINAL blocks.
"""


# ---------------------------------------------------------------------------
# Async core
# ---------------------------------------------------------------------------

async def _run_async(
    prompt: str,
    timeout: int,
    max_rounds: int,
) -> WorkerResult:
    from sydney import SydneyClient  # imported here so missing install gives clear error

    t0 = time.time()
    tool_calls_total = 0

    first_message = f"{_SYSTEM}\n\nTask: {prompt}"

    try:
        async with SydneyClient(style="precise") as client:
            current_message = first_message

            for round_num in range(max_rounds):
                if time.time() - t0 > timeout:
                    return WorkerResult(
                        "", False, f"Timeout after {timeout}s",
                        timing_s=round(time.time() - t0, 1),
                        tool_calls=tool_calls_total,
                    )

                try:
                    response = await client.ask(
                        current_message,
                        citations=False,
                        suggestions=False,
                    )
                except Exception as e:
                    return WorkerResult(
                        "", False, f"Sydney API error: {e}",
                        timing_s=round(time.time() - t0, 1),
                        tool_calls=tool_calls_total,
                    )

                # Check for final answer first
                final = _extract_final(response)
                if final:
                    return WorkerResult(
                        text=final,
                        ok=True,
                        timing_s=round(time.time() - t0, 1),
                        tool_calls=tool_calls_total,
                    )

                # Check for tool call
                tool_name, tool_args = _parse_tool_call(response)
                if tool_name and tool_name in _TOOL_FNS:
                    result = _TOOL_FNS[tool_name](tool_args)
                    tool_calls_total += 1
                    current_message = (
                        f"Tool result for {tool_name}:\n"
                        f"{result}\n\n"
                        f"Continue. Call the next tool or output FINAL: <answer>."
                    )
                    continue

                # Model gave a plain answer with no TOOL or FINAL marker — treat as final
                text = response.strip()
                if text:
                    return WorkerResult(
                        text=text,
                        ok=True,
                        timing_s=round(time.time() - t0, 1),
                        tool_calls=tool_calls_total,
                    )

                return WorkerResult(
                    "", False, "Empty response from model",
                    timing_s=round(time.time() - t0, 1),
                    tool_calls=tool_calls_total,
                )

    except Exception as e:
        return WorkerResult(
            "", False, f"Client error: {e}",
            timing_s=round(time.time() - t0, 1),
            tool_calls=tool_calls_total,
        )

    return WorkerResult(
        "", False, f"Exceeded {max_rounds} rounds",
        timing_s=round(time.time() - t0, 1),
        tool_calls=tool_calls_total,
    )


# ---------------------------------------------------------------------------
# Public API  (sync wrappers — matches openrouter_worker.py interface)
# ---------------------------------------------------------------------------

def _ensure_cookie():
    cookie = os.getenv("BING_U_COOKIE", "")
    if not cookie:
        return "BING_U_COOKIE not set in .env — see module docstring for how to get it"
    os.environ["BING_U_COOKIE"] = cookie
    return None


def run_task(prompt: str, *, timeout: int = 120, max_tool_rounds: int = 15) -> WorkerResult:
    """Send prompt to Microsoft Copilot with a ReAct tool-calling loop."""
    err = _ensure_cookie()
    if err:
        return WorkerResult("", False, err)

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    return asyncio.run(_run_async(prompt, timeout, max_tool_rounds))


def run_build_task(task: str, *, timeout: int = 300) -> WorkerResult:
    """Autonomous build/edit task — same as run_task but longer timeout."""
    return run_task(task, timeout=timeout)


# ---------------------------------------------------------------------------
# CLI smoke test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    load_dotenv()

    cookie = os.getenv("BING_U_COOKIE", "")
    if not cookie:
        print("ERROR: BING_U_COOKIE not set in .env", file=sys.stderr)
        print("", file=sys.stderr)
        print("How to get it:", file=sys.stderr)
        print("  1. Open Edge/Chrome → https://copilot.microsoft.com", file=sys.stderr)
        print("  2. Sign in with your Microsoft account", file=sys.stderr)
        print("  3. F12 → Application → Cookies → copilot.microsoft.com", file=sys.stderr)
        print("  4. Copy the value of the '_U' cookie", file=sys.stderr)
        print("  5. Add to .env:  BING_U_COOKIE=<value>", file=sys.stderr)
        sys.exit(1)

    prompt = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else (
        "List the files in the tools/ directory of this project."
    )
    print(f"[copilot-worker] style=precise  ReAct loop enabled")
    print(f"[copilot-worker] -> {prompt!r}\n")

    r = run_task(prompt, timeout=60)
    print(f"ok={r.ok}  time={r.timing_s}s  tool_calls={r.tool_calls}")
    print("---")
    if r.ok:
        print(r.text)
    else:
        print("ERROR:", r.error, file=sys.stderr)
    sys.exit(0 if r.ok else 1)
