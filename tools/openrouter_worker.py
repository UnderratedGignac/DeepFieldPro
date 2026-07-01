"""
AI worker — Qwen3.5-122B via NVIDIA NIM (primary) or Qwen3-80B via OpenRouter (fallback).

Both providers use the OpenAI-compatible API with function calling:
  read_file, write_file, list_directory, run_python, run_shell

Provider selection (automatic):
  1. NVIDIA NIM  — if NVIDIA_API_KEY is set  (qwen/qwen3.5-122b-a10b)
  2. OpenRouter  — if OPENROUTER_API_KEY is set

Usage:
    from tools.openrouter_worker import run_task, run_build_task, WorkerResult

    r = run_task("List files in tools/")
    print(r.text)

    r = run_build_task("Refactor src/dfp_config.py to add type hints")
    print(r.text)
"""

import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

# Provider config — NVIDIA NIM preferred, OpenRouter as fallback
_NVIDIA_MODEL = "qwen/qwen3.5-122b-a10b"
_NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"

_OR_MODEL = "qwen/qwen3-next-80b-a3b-instruct:free"
_OR_BASE_URL = "https://openrouter.ai/api/v1"

_PROJECT_ROOT = Path(r"C:\Users\Elie\DeepFieldPro")
_VENV_PYTHON = str(_PROJECT_ROOT / ".venv" / "Scripts" / "python.exe")


@dataclass
class WorkerResult:
    text: str
    ok: bool
    error: str = ""
    timing_s: float = 0.0
    tool_calls: int = 0


# ---------------------------------------------------------------------------
# Tool implementations (run locally, results fed back to the model)
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
        lines = []
        for e in entries:
            tag = "[DIR] " if e.is_dir() else "[FILE]"
            lines.append(f"{tag} {e.name}")
        return "\n".join(lines) or "(empty)"
    except Exception as e:
        return f"ERROR: {e}"


def _run_python(code: str) -> str:
    try:
        result = subprocess.run(
            [_VENV_PYTHON, "-c", code],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(_PROJECT_ROOT),
        )
        out = result.stdout[-4000:] if result.stdout else ""
        err = result.stderr[-2000:] if result.stderr else ""
        parts = []
        if out:
            parts.append(f"STDOUT:\n{out}")
        if err:
            parts.append(f"STDERR:\n{err}")
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
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(_PROJECT_ROOT),
        )
        out = result.stdout[-4000:] if result.stdout else ""
        err = result.stderr[-2000:] if result.stderr else ""
        parts = []
        if out:
            parts.append(out)
        if err:
            parts.append(f"STDERR: {err}")
        if result.returncode != 0:
            parts.append(f"exit_code={result.returncode}")
        return "\n".join(parts) or "(no output)"
    except subprocess.TimeoutExpired:
        return "ERROR: timeout after 30s"
    except Exception as e:
        return f"ERROR: {e}"


# ---------------------------------------------------------------------------
# Tool schemas (OpenAI function-calling format)
# ---------------------------------------------------------------------------

_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the contents of a file. Use absolute or project-relative paths.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path to read"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write content to a file, creating parent directories if needed.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path to write"},
                    "content": {"type": "string", "description": "Content to write"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_directory",
            "description": "List files and subdirectories in a directory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Directory path (default: project root)",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_python",
            "description": "Execute Python code in the project venv and return stdout/stderr.",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "Python code to execute"},
                },
                "required": ["code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_shell",
            "description": "Run a shell command in the project root and return output.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "Shell command to run",
                    },
                },
                "required": ["command"],
            },
        },
    },
]

_TOOL_FNS = {
    "read_file": lambda args: _read_file(args["path"]),
    "write_file": lambda args: _write_file(args["path"], args["content"]),
    "list_directory": lambda args: _list_directory(args.get("path", ".")),
    "run_python": lambda args: _run_python(args["code"]),
    "run_shell": lambda args: _run_shell(args["command"]),
}

_SYSTEM = (
    "You are an autonomous coding agent for the DeepFieldPro project.\n"
    "Project root: C:/Users/Elie/DeepFieldPro\n"
    "Stack: Python 3.12, Flask, SQLite, Windows, venv at .venv/\n"
    "Use your tools to read files, write code, and run scripts. "
    "After finishing, give a brief summary of what you did."
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run_task(
    prompt: str, *, timeout: int = 120, max_tool_rounds: int = 20
) -> WorkerResult:
    """
    Send prompt to Qwen3 via OpenRouter with tool-calling loop.
    The model can call read_file/write_file/list_directory/run_python/run_shell
    as many times as needed before returning its final answer.
    """
    t0 = time.time()

    # Pick provider: NVIDIA NIM first, OpenRouter fallback
    nvidia_key = os.getenv("NVIDIA_API_KEY", "")
    or_key = os.getenv("OPENROUTER_API_KEY", "")

    if nvidia_key:
        api_key = nvidia_key
        base_url = _NVIDIA_BASE_URL
        model = _NVIDIA_MODEL
    elif or_key:
        api_key = or_key
        base_url = _OR_BASE_URL
        model = _OR_MODEL
    else:
        return WorkerResult(
            "",
            False,
            "No API key set — add NVIDIA_API_KEY or OPENROUTER_API_KEY to .env",
        )

    client = OpenAI(api_key=api_key, base_url=base_url)
    messages = [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": prompt},
    ]
    tool_calls_total = 0

    is_nvidia = bool(nvidia_key)

    for _round in range(max_tool_rounds):
        if time.time() - t0 > timeout:
            return WorkerResult(
                "",
                False,
                f"Timeout after {timeout}s",
                timing_s=round(time.time() - t0, 1),
                tool_calls=tool_calls_total,
            )

        # NVIDIA NIM Qwen3.5 quirks:
        #   - round 0 (no tools called yet): 'auto' returns empty → force 'required'
        #   - round 1+ (after tool results): 'auto' still returns empty → force 'none'
        #     (none = text only, no tool calls, forces a real answer)
        if is_nvidia:
            tool_choice = "required" if tool_calls_total == 0 else "none"
        else:
            tool_choice = "auto"

        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                tools=_TOOLS,
                tool_choice=tool_choice,
                timeout=60,
            )
        except Exception as e:
            return WorkerResult(
                "",
                False,
                f"API error: {e}",
                timing_s=round(time.time() - t0, 1),
                tool_calls=tool_calls_total,
            )

        choice = response.choices[0]
        msg = choice.message

        # If the model returned tool calls, execute them and loop
        if msg.tool_calls:
            # Serialize assistant message as plain dict (avoids Pydantic object quirks)
            messages.append(
                {
                    "role": "assistant",
                    "content": msg.content,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in msg.tool_calls
                    ],
                }
            )
            for tc in msg.tool_calls:
                fn_name = tc.function.name
                try:
                    args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    args = {}
                fn = _TOOL_FNS.get(fn_name)
                result = fn(args) if fn else f"ERROR: unknown tool {fn_name!r}"
                tool_calls_total += 1
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": str(result),
                    }
                )
            continue  # send tool results back to model

        # No tool calls — model gave its final answer
        text = (msg.content or "").strip()
        return WorkerResult(
            text=text,
            ok=True,
            timing_s=round(time.time() - t0, 1),
            tool_calls=tool_calls_total,
        )

    return WorkerResult(
        "",
        False,
        f"Exceeded {max_tool_rounds} tool rounds",
        timing_s=round(time.time() - t0, 1),
        tool_calls=tool_calls_total,
    )


def run_build_task(task: str, timeout: int = 300) -> WorkerResult:
    """Autonomous build/edit task — same as run_task but longer timeout."""
    return run_task(task, timeout=timeout)


# ---------------------------------------------------------------------------
# CLI smoke test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    load_dotenv()
    provider = "NVIDIA NIM" if os.getenv("NVIDIA_API_KEY") else "OpenRouter"
    model_name = _NVIDIA_MODEL if os.getenv("NVIDIA_API_KEY") else _OR_MODEL
    prompt = (
        " ".join(sys.argv[1:])
        if len(sys.argv) > 1
        else ("List the files in the tools/ directory of this project.")
    )
    print(f"[master] provider={provider} model={model_name}")
    print(f"[master] -> {prompt!r}\n")
    r = run_task(prompt, timeout=60)
    print(f"ok={r.ok}  time={r.timing_s}s  tool_calls={r.tool_calls}")
    print("---")
    if r.ok:
        print(r.text)
    else:
        print("ERROR:", r.error, file=sys.stderr)
    sys.exit(0 if r.ok else 1)
