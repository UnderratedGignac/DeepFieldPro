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

    AGY >= 1.0.16 prints the response to STDOUT in --print mode, then hangs
    in its shutdown phase ("waiting for migrations") instead of exiting.
    The bridge therefore captures stdout to a temp file, waits until the
    output is non-empty and stable, then kills the lingering process.
    The conversation-DB poll is kept as a fallback for older AGY builds
    that wrote the response to the DB instead of stdout.

    Args:
        prompt:            The task/instruction for AGY.
        timeout:           Seconds to wait for a response (default 120).
        skip_permissions:  Pass --dangerously-skip-permissions (default True).
        cwd:               Working directory for AGY (defaults to project root).
    """
    import tempfile

    _CONV_DIR.mkdir(parents=True, exist_ok=True)

    # Snapshot for the DB fallback path.
    before = _snapshot_all_dbs()

    cmd = [_AGY_EXE, "--print", prompt]
    if skip_permissions:
        cmd.append("--dangerously-skip-permissions")

    fd, out_path = tempfile.mkstemp(prefix="agy_out_", suffix=".txt")
    os.close(fd)
    try:
        with open(out_path, "w", encoding="utf-8") as out_file:
            try:
                proc = subprocess.Popen(
                    cmd,
                    stdin=subprocess.DEVNULL,  # piped stdin makes AGY block reading it
                    stdout=out_file,
                    stderr=subprocess.DEVNULL,
                    cwd=cwd or os.getcwd(),
                )
            except FileNotFoundError:
                return AgyResult(
                    text="", ok=False, conversation_id="", error="agy.exe not found"
                )

            # Output is complete when the stdout file is non-empty and its
            # size has stopped growing for a few seconds.
            deadline = time.time() + timeout
            last_size, stable_since = 0, None
            while time.time() < deadline:
                time.sleep(0.5)
                try:
                    size = os.path.getsize(out_path)
                except OSError:
                    size = 0
                if size > 0:
                    if size != last_size:
                        last_size, stable_since = size, time.time()
                    # Multi-step tasks (read several files, then edit) can go quiet for
                    # well over 3s between stdout writes while AGY runs tool calls that
                    # don't stream output — a short window falsely reads that as "done"
                    # and kills the process mid-task (observed: 30s task, opening line only).
                    elif stable_since and time.time() - stable_since >= 12.0:
                        break
                if proc.poll() is not None:
                    break

        # Kill the hung shutdown phase — the answer is already on disk.
        if proc.poll() is None:
            proc.kill()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass

        text = Path(out_path).read_text(encoding="utf-8", errors="replace").strip()
        if text:
            return AgyResult(text=text, ok=True, conversation_id="stdout")
    finally:
        try:
            os.unlink(out_path)
        except OSError:
            pass

    # Fallback: older AGY builds wrote the response to the conversation DB.
    for db_path in glob.glob(str(_CONV_DIR / "*.db")):
        prior_idx = before.get(db_path, -1)
        if _max_step_idx(db_path) > prior_idx and _count_new_responses(db_path, prior_idx) > 0:
            db_text = _extract_text(db_path, min_idx=prior_idx)
            if db_text:
                return AgyResult(
                    text=db_text, ok=True, conversation_id=Path(db_path).stem
                )

    return AgyResult(
        text="",
        ok=False,
        conversation_id="",
        error=f"No AGY response (stdout or conversation DB) within {timeout}s",
    )


def _count_new_responses(db_path: str, after_idx: int) -> int:
    """Completed response steps (type=15, status=3) newer than after_idx."""
    try:
        conn = sqlite3.connect(db_path, timeout=2)
        cur = conn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM steps WHERE step_type=? AND status=? AND idx>?",
            (_RESP_STEP_TYPE, _STATUS_DONE, after_idx),
        )
        n = cur.fetchone()[0]
        conn.close()
        return n
    except Exception:
        return 0


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
