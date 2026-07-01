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


def _count_responses(db_path: str) -> int:
    """Return the current count of completed response steps in this DB."""
    try:
        conn = sqlite3.connect(db_path, timeout=2)
        cur = conn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM steps WHERE step_type=? AND status=?",
            (_RESP_STEP_TYPE, _STATUS_DONE),
        )
        count = cur.fetchone()[0]
        conn.close()
        return count
    except Exception:
        return 0


def _max_step_idx(db_path: str) -> int:
    """Return the max step idx in this DB (or -1 on error)."""
    try:
        conn = sqlite3.connect(db_path, timeout=2)
        cur = conn.cursor()
        cur.execute("SELECT COALESCE(MAX(idx), -1) FROM steps")
        idx = cur.fetchone()[0]
        conn.close()
        return idx
    except Exception:
        return -1


def _extract_text(db_path: str, min_idx: int = -1) -> str:
    """
    Pull the newest completed assistant response added AFTER min_idx.
    Returns plain text extracted from the protobuf payload.
    """
    conn = sqlite3.connect(db_path, timeout=5)
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT step_payload FROM steps "
            "WHERE step_type=? AND status=? AND idx>? "
            "ORDER BY idx DESC LIMIT 1",
            (_RESP_STEP_TYPE, _STATUS_DONE, min_idx),
        )
        row = cur.fetchone()
        if not row or not row[0]:
            return ""
        raw = row[0].decode("utf-8", errors="replace")
        # Protobuf text fields are embedded as length-prefixed strings.
        # Grab all printable runs longer than 15 chars, filter noise, deduplicate.
        candidates = re.findall(r"[ -~\n\t]{15,}", raw)
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
    # Pure hex/protobuf framing noise (no spaces, all hex/digits)
    if re.match(r"^[0-9a-fA-F]{16,}$", s):
        return True
    return False


def _snapshot_all_dbs() -> dict[str, int]:
    """Return {db_path: max_step_idx} for every existing conversation DB."""
    snapshot = {}
    for db_path in glob.glob(str(_CONV_DIR / "*.db")):
        snapshot[db_path] = _max_step_idx(db_path)
    return snapshot


def run_task(
    prompt: str,
    *,
    timeout: int = 120,
    skip_permissions: bool = True,
    cwd: str | None = None,
) -> AgyResult:
    """
    Dispatch `prompt` to AGY as a slave and return the response.

    AGY reuses its per-project "brain" conversation DB rather than creating
    a new file each time.  The bridge therefore snapshots the max step idx
    of every existing DB before launch and polls for any DB whose idx grew.

    Args:
        prompt:            The task/instruction for AGY.
        timeout:           Seconds to wait for a response (default 120).
        skip_permissions:  Pass --dangerously-skip-permissions (default True).
        cwd:               Working directory for AGY (defaults to project root).
    """
    _CONV_DIR.mkdir(parents=True, exist_ok=True)

    # Snapshot: record the max step idx of every existing DB.
    # A DB whose idx increases after launch is the one AGY wrote to.
    before = _snapshot_all_dbs()

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
        return AgyResult(
            text="", ok=False, conversation_id="", error="agy.exe not found"
        )

    # Poll for any DB whose max_step_idx has grown AND contains a new
    # completed response step (type=15, status=3) after the snapshot idx.
    deadline = time.time() + timeout
    found_db: str | None = None
    found_min_idx: int = -1

    while time.time() < deadline:
        time.sleep(1)
        # Scan all DBs — both existing (checking if idx grew) and any new ones.
        all_dbs = glob.glob(str(_CONV_DIR / "*.db"))
        for db_path in all_dbs:
            prior_idx = before.get(db_path, -1)
            cur_idx = _max_step_idx(db_path)
            if cur_idx > prior_idx:
                # This DB got new steps. Check if one of them is a completed response.
                try:
                    conn = sqlite3.connect(db_path, timeout=2)
                    cur = conn.cursor()
                    cur.execute(
                        "SELECT COUNT(*) FROM steps "
                        "WHERE step_type=? AND status=? AND idx>?",
                        (_RESP_STEP_TYPE, _STATUS_DONE, prior_idx),
                    )
                    n = cur.fetchone()[0]
                    conn.close()
                    if n > 0:
                        found_db = db_path
                        found_min_idx = prior_idx
                        break
                except Exception:
                    pass
        if found_db:
            break
        # If AGY process exited, do one final scan then stop waiting.
        if proc.poll() is not None:
            time.sleep(2)
            # Final scan
            for db_path in glob.glob(str(_CONV_DIR / "*.db")):
                prior_idx = before.get(db_path, -1)
                cur_idx = _max_step_idx(db_path)
                if cur_idx > prior_idx:
                    try:
                        conn = sqlite3.connect(db_path, timeout=2)
                        cur = conn.cursor()
                        cur.execute(
                            "SELECT COUNT(*) FROM steps "
                            "WHERE step_type=? AND status=? AND idx>?",
                            (_RESP_STEP_TYPE, _STATUS_DONE, prior_idx),
                        )
                        n = cur.fetchone()[0]
                        conn.close()
                        if n > 0:
                            found_db = db_path
                            found_min_idx = prior_idx
                    except Exception:
                        pass
            break

    if proc.poll() is None:
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()

    if not found_db:
        return AgyResult(
            text="",
            ok=False,
            conversation_id="",
            error=f"No new AGY response appeared within {timeout}s",
        )

    conv_id = Path(found_db).stem
    text = _extract_text(found_db, min_idx=found_min_idx)

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
    return run_task(
        full_prompt,
        timeout=timeout,
        skip_permissions=True,
        cwd="C:/Users/Elie/DeepFieldPro",
    )


# ---------------------------------------------------------------------------
# CLI entry point — also serves as a quick smoke test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys

    prompt = (
        " ".join(sys.argv[1:])
        if len(sys.argv) > 1
        else "Say ONLINE in exactly one word."
    )
    print(f"[master] dispatching to AGY slave: {prompt!r}")
    result = run_task(prompt, timeout=60)
    print(f"[slave]  ok={result.ok}  conv={result.conversation_id}")
    print(f"[slave]  response:\n{result.text}")
    if result.error:
        print(f"[slave]  error: {result.error}", file=sys.stderr)
    sys.exit(0 if result.ok else 1)
