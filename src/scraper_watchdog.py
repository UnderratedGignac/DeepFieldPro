# mypy: ignore-errors
"""
scraper_watchdog.py — Betarabia odds-scraper health probe.
==========================================================
The daemon calls odds_stale() once per sweep to detect a HUNG scrape (its own
subprocess handle alive but data not advancing) and then kills/respawns its
OWN process handle. The daemon is the single spawner — this module must NOT
spawn a competing scrape while a daemon runs (double Chromium = the crash
mode that made odds go stale in the first place).

ensure_scraper_alive() remains for STANDALONE use only (no daemon running,
e.g. a cron job or manual recovery). It restarts betarabia_scraper.py when
data/odds_stream.db is stale, rate-limited to once per 10 minutes.

State file: data/scraper_watchdog.json  {pid, started_at, reason, last_restart}
Threshold:  data/settings.json key 'scraper_max_stale_min' (default 20 min).

Nothing here ever raises to the caller; importing has zero side effects.
"""

import datetime
import json
import os
import sqlite3
import subprocess
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "data", "odds_stream.db")
SETTINGS_PATH = os.path.join(BASE_DIR, "data", "settings.json")
STATE_PATH = os.path.join(BASE_DIR, "data", "scraper_watchdog.json")
SCRAPER_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "betarabia_scraper.py"
)

DEFAULT_MAX_STALE_MIN = 20.0
RESTART_COOLDOWN_SEC = 600  # never restart more than once per 10 minutes


def _read_max_stale_min() -> float:
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            raw = json.load(f).get("scraper_max_stale_min")
        val = float(raw)
        if val > 0:
            return val
    except Exception:
        pass
    return DEFAULT_MAX_STALE_MIN


def _parse_iso_utc(ts):
    """Parse an ISO timestamp ('+00:00', 'Z', or naive) to aware UTC, or None."""
    if not ts:
        return None
    try:
        dt = datetime.datetime.fromisoformat(str(ts).strip().replace("Z", "+00:00"))
    except Exception:
        return None
    if dt.tzinfo is None:
        # Scraper writes UTC; treat naive legacy rows as UTC too.
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return dt.astimezone(datetime.timezone.utc)


def _last_scrape_utc():
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH, timeout=5)
        row = conn.execute("SELECT MAX(scraped_at) FROM fixture").fetchone()
        return _parse_iso_utc(row[0] if row else None)
    except Exception:
        return None
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def _read_state() -> dict:
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            state = json.load(f)
        return state if isinstance(state, dict) else {}
    except Exception:
        return {}


def _write_state(state: dict) -> None:
    try:
        with open(STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
    except Exception:
        pass


def _pid_is_our_scraper(pid) -> bool:
    """True only if pid is alive AND its command line is betarabia_scraper.py.

    A name-only 'is it python' check is not enough: on this box nearly every
    process is python (dashboard, daemon, tools) and Windows reuses PIDs, so a
    stale recorded pid could point at the daemon itself. Require the cmdline
    to name the scraper script; without psutil we cannot verify, so refuse.
    """
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    try:
        import psutil
    except ImportError:
        return False  # cannot verify cmdline -> never kill on name alone
    try:
        cmdline = " ".join(psutil.Process(pid).cmdline() or [])
        return "betarabia_scraper" in cmdline.lower()
    except Exception:
        return False


def _kill_pid(pid) -> None:
    try:
        import psutil

        try:
            psutil.Process(int(pid)).kill()
            return
        except Exception:
            pass
    except ImportError:
        pass
    try:
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/F"],
            capture_output=True,
            timeout=10,
        )
    except Exception:
        pass


def _python_exe() -> str:
    venv_py = os.path.join(BASE_DIR, ".venv", "Scripts", "python.exe")
    return venv_py if os.path.exists(venv_py) else sys.executable


def odds_stale(max_stale_min: float = None) -> bool:
    """True when odds_stream.db's newest scrape is older than the threshold
    (or unreadable). Pure probe — no side effects, never raises. The daemon
    uses this to detect its own hung scrape subprocess."""
    try:
        threshold = max_stale_min if max_stale_min else _read_max_stale_min()
        last = _last_scrape_utc()
        if last is None:
            return True
        age_min = (
            datetime.datetime.now(datetime.timezone.utc) - last
        ).total_seconds() / 60.0
        return age_min > threshold
    except Exception:
        return False  # fail safe: never report stale on probe error


def ensure_scraper_alive() -> bool:
    """Restart betarabia_scraper.py if odds_stream.db data is stale.

    Returns True when the data is fresh or a restart was just launched;
    False when the data is stale but nothing was restarted (cooldown or
    launch failure). Never raises.
    """
    try:
        max_stale_min = _read_max_stale_min()
        now = datetime.datetime.now(datetime.timezone.utc)
        last = _last_scrape_utc()

        if last is not None:
            age_min = (now - last).total_seconds() / 60.0
            if age_min <= max_stale_min:
                return True
            reason = (
                f"stale: last scrape {age_min:.1f} min ago "
                f"(max {max_stale_min:g} min)"
            )
        else:
            reason = "unreadable: no parseable scraped_at in odds_stream.db"

        state = _read_state()
        last_restart = _parse_iso_utc(state.get("last_restart"))
        if last_restart is not None:
            since_sec = (now - last_restart).total_seconds()
            if 0 <= since_sec < RESTART_COOLDOWN_SEC:
                print(
                    f"[WATCHDOG] {reason} - restart suppressed "
                    f"(last restart {since_sec:.0f}s ago, cooldown "
                    f"{RESTART_COOLDOWN_SEC}s)."
                )
                return False

        # Kill only a process WE started earlier (recorded pid) and only if
        # its cmdline proves it is a betarabia_scraper.py run (PID-reuse guard).
        prev_pid = state.get("pid")
        if prev_pid and _pid_is_our_scraper(prev_pid):
            _kill_pid(prev_pid)
            print(f"[WATCHDOG] Killed stuck previous scraper (pid {prev_pid}).")

        # Mirror the daemon's Popen: [python, src/betarabia_scraper.py],
        # close_fds=True, inherited cwd, no output redirection.
        proc = subprocess.Popen([_python_exe(), SCRAPER_PATH], close_fds=True)

        _write_state(
            {
                "pid": proc.pid,
                "started_at": now.isoformat(),
                "reason": reason,
                "last_restart": now.isoformat(),
            }
        )
        print(
            f"[WATCHDOG] {reason} - restarted betarabia_scraper.py "
            f"(pid {proc.pid})."
        )
        return True
    except Exception as exc:
        try:
            print(f"[WATCHDOG] error (ignored): {exc}")
        except Exception:
            pass
        return False
