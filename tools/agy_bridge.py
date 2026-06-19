"""
AGY (Antigravity/Gemini CLI) slave bridge.

Master-slave pattern:
  - Master: Claude Code / Python orchestrator
  - Slave:  agy.exe, dispatched via --print mode

Usage:
    from tools.agy_bridge import run_task

    result = run_task("Refactor src/execution_engine.py to add retry logic")
    print(result.text)
    print(result.ok)
"""

import glob
import os
import re
import sqlite3
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

_CONV_DIR = Path.home() / ".gemini" / "antigravity-cli" / "conversations"
_AGY_EXE = "agy.exe"

# Step type 15 = model response (assistant turn)
# Status 3 = completed
_RESP_STEP_TYPE = 15
_STATUS_DONE = 3


@dataclass
class AgyResult:
    text: str
    ok: bool
    conversation_id: str
    error: str = ""


def _extract_text(db_path: str) -> str:
    """Pull assistant response text from a conversation DB."""
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT step_payload FROM steps WHERE step_type=? AND status=? ORDER BY idx DESC LIMIT 1",
            (_RESP_STEP_TYPE, _STATUS_DONE),
        )
        row = cur.fetchone()
        if not row or not row[0]:
            return ""
        raw = row[0].decode("utf-8", errors="replace")
        # Protobuf text fields are embedded as length-prefixed strings.
        # Grab all printable runs longer than 20 chars, deduplicate adjacent duplicates.
        candidates = re.findall(r"[ -~\n\t]{20,}", raw)
        seen, parts = set(), []
        for c in candidates:
            c = c.strip()
            if c and c not in seen and not _is_noise(c):
                seen.add(c)
                parts.append(c)
        return "\n".join(parts)
    finally:
        conn.close()


def _is_noise(s: str) -> bool:
    """Filter out UUIDs, file paths, and other non-response noise."""
    if re.match(r"^[0-9a-f\-]{36}$", s):
        return True
    if s.startswith(("file:///", "C:\\", "C:/", "/c/")):
        return True
    if s.startswith(("command(", "execute_url(", "read_url(")):
        return True
    return False


def _db_has_response(db_path: str) -> bool:
    """Return True if the DB already contains a completed response step."""
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM steps WHERE step_type=? AND status=?",
            (_RESP_STEP_TYPE, _STATUS_DONE),
        )
        count = cur.fetchone()[0]
        conn.close()
        return count > 0
    except Exception:
        return False


def run_task(
    prompt: str,
    *,
    timeout: int = 120,
    skip_permissions: bool = True,
    cwd: str | None = None,
) -> AgyResult:
    """
    Dispatch `prompt` to AGY as a slave and return the response.

    Args:
        prompt:            The task/instruction for AGY.
        timeout:           Seconds to wait for a response (default 120).
        skip_permissions:  Pass --dangerously-skip-permissions (default True).
        cwd:               Working directory for AGY (defaults to current dir).
    """
    _CONV_DIR.mkdir(parents=True, exist_ok=True)

    # Snapshot existing DBs so we can identify the new one.
    before = set(glob.glob(str(_CONV_DIR / "*.db")))

    cmd = [_AGY_EXE, "--print", prompt]
    if skip_permissions:
        cmd.append("--dangerously-skip-permissions")

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            cwd=cwd or os.getcwd(),
        )
    except FileNotFoundError:
        return AgyResult(text="", ok=False, conversation_id="", error="agy.exe not found")

    # Poll for the new conversation DB.
    deadline = time.time() + timeout
    new_db: str | None = None

    while time.time() < deadline:
        time.sleep(1)
        after = set(glob.glob(str(_CONV_DIR / "*.db")))
        candidates = after - before
        if candidates:
            new_db = max(candidates, key=os.path.getmtime)
            # Wait until the DB contains a completed response.
            if _db_has_response(new_db):
                break
        # Also check if process exited — give it one more second then read.
        if proc.poll() is not None and new_db and time.time() > deadline - timeout + 5:
            time.sleep(2)
            break

    if proc.poll() is None:
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()

    if not new_db:
        return AgyResult(
            text="",
            ok=False,
            conversation_id="",
            error=f"No new conversation DB appeared within {timeout}s",
        )

    conv_id = Path(new_db).stem
    text = _extract_text(new_db)

    return AgyResult(
        text=text,
        ok=bool(text),
        conversation_id=conv_id,
        error="" if text else "Response DB found but no text extracted",
    )


def run_build_task(task: str, timeout: int = 180) -> AgyResult:
    """
    Convenience wrapper: ask AGY to build/implement `task` in the DeepFieldPro repo.
    Instructs AGY to work autonomously (skip permissions) and report what it did.
    """
    full_prompt = (
        f"You are a slave agent for the DeepFieldPro project at C:/Users/Elie/DeepFieldPro. "
        f"Complete the following task autonomously, edit files as needed, and report a brief summary of changes made:\n\n"
        f"{task}"
    )
    return run_task(full_prompt, timeout=timeout, skip_permissions=True, cwd="C:/Users/Elie/DeepFieldPro")


# ---------------------------------------------------------------------------
# CLI entry point — also serves as a quick smoke test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys

    prompt = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "Say ONLINE in exactly one word."
    print(f"[master] dispatching to AGY slave: {prompt!r}")
    result = run_task(prompt, timeout=60)
    print(f"[slave]  ok={result.ok}  conv={result.conversation_id}")
    print(f"[slave]  response:\n{result.text}")
    if result.error:
        print(f"[slave]  error: {result.error}", file=sys.stderr)
    sys.exit(0 if result.ok else 1)
