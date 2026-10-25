"""
DeepFieldPro server watchdog — one check per run, scheduled every 5 minutes.

Task Scheduler runs this (task "DeepFieldPro Watchdog", via pythonw.exe so no
window flashes). Each run looks at /api/health and at the server's own
processes, then does at most one thing: nothing, start, or kill-and-restart.
The consecutive-failure count persists in logs/watchdog_state.json.

Why one-shot + Task Scheduler instead of a loop: a long-running watchdog dies
with whatever launched it. The 2026-10-23 outage (~5 h, no bets, no
settlement) was a server started from a Claude session that then restarted.
The server is launched through WMI (Win32_Process.Create), so its parent is
WmiPrvSE — not this script, not the scheduler, not a terminal.

Only DeepFieldPro server processes are ever killed. The previous version of
this file killed every python.exe on the machine (MCP servers included).

Usage:
    .venv\\Scripts\\pythonw.exe tools\\watchdog.py            # what the task runs
    .venv\\Scripts\\python.exe tools\\watchdog.py --dry-run   # print the decision only
    .venv\\Scripts\\python.exe tools\\watchdog.py --test-alert  # send one test push

Phone alerts go to the project's ntfy topic (NTFY_TOPIC in .env): every start or
restart, a second consecutive unhealthy check, one urgent push for a restart
loop (then quiet for an hour), and an all-clear once an incident recovers.
"""

import argparse
import json
import os
import socket
import subprocess
import sys
import time
import traceback
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_FILE = os.path.join(ROOT, "logs", "watchdog.log")
STATE_FILE = os.path.join(ROOT, "logs", "watchdog_state.json")
PORT_FILE = os.path.join(ROOT, "current_port.txt")
PYTHON = os.path.join(ROOT, ".venv", "Scripts", "python.exe")

SERVER_SCRIPT = "live_dashboard_server.py"
DEFAULT_PORT = 5058
PORT_RANGE = range(5058, 5066)

# A single slow or failed health call is not an outage: restart only after
# this many consecutive misses (3 x 5 min = 15 min).
HEALTH_FAILS_BEFORE_RESTART = 3
# The supervisor briefly reports alive=False while it backs off between
# retries of a crashed worker; only a second consecutive report counts.
DEAD_REPORTS_BEFORE_RESTART = 2
# Flask binds within ~20 s; before this the port is legitimately silent.
BOOT_GRACE_MIN = 5.0
# The first prediction cycle after a long gap took ~30 min before writing
# state (2026-10-23). Stale state only means "wedged" past both bars.
WEDGED_STATE_AGE_SEC = 90 * 60
WEDGED_MIN_UPTIME_MIN = 60.0
# ...and the server's stdout log must have gone quiet too. On a big slate one
# cycle ran >80 min while still placing bets (2026-10-24); a live cycle keeps
# printing, a wedged one does not. Flask access lines go to the .err log, so
# the watchdog's own health checks never refresh this.
WEDGED_LOG_IDLE_MIN = 30.0
HEALTHY = "healthy"
# This many starts/restarts inside the window is a loop, not a blip: one
# urgent push, then quiet for the rest of the window.
RESTART_LOOP_COUNT = 3
RESTART_LOOP_WINDOW_SEC = 3600

CREATE_NO_WINDOW = 0x08000000


# ---------------------------------------------------------------------------
# Decisions (pure — see tests/test_watchdog.py)
# ---------------------------------------------------------------------------


def decide(roots, age_min, health, fails, log_idle_min=None):
    """Return (action, reason, fails) where action is ok | wait | start | restart.

    roots        — number of independent server process chains running
    age_min      — uptime of the oldest server process, minutes (None if none)
    health       — parsed /api/health JSON, or None if it did not answer
    fails        — consecutive failures carried over from the previous run
    log_idle_min — minutes since the server's stdout log was written (None if unknown)
    """
    if roots == 0:
        return "start", "no server process", 0
    if roots > 1:
        return "restart", f"{roots} servers running (twin daemons double-place bets)", 0

    if health is None:
        if age_min is not None and age_min < BOOT_GRACE_MIN:
            return "wait", f"booting ({age_min:.1f} min), no HTTP yet", fails
        fails += 1
        if fails >= HEALTH_FAILS_BEFORE_RESTART:
            return "restart", f"/api/health unreachable for {fails} checks", 0
        return "wait", f"/api/health unreachable ({fails}/{HEALTH_FAILS_BEFORE_RESTART})", fails

    if not health.get("alive"):
        fails += 1
        if fails >= DEAD_REPORTS_BEFORE_RESTART:
            return "restart", f"prediction worker dead for {fails} checks", 0
        return "wait", f"prediction worker reported dead ({fails}/{DEAD_REPORTS_BEFORE_RESTART})", fails

    if health.get("state_stale"):
        age = health.get("state_age_sec")
        uptime = age_min or 0.0
        log_quiet = log_idle_min is None or log_idle_min > WEDGED_LOG_IDLE_MIN
        if (age is None or age > WEDGED_STATE_AGE_SEC) and uptime > WEDGED_MIN_UPTIME_MIN and log_quiet:
            age_txt = f"{age / 60:.0f} min" if age is not None else "missing"
            log_txt = f", log silent {log_idle_min:.0f} min" if log_idle_min is not None else ""
            return "restart", f"state stale ({age_txt}) after {uptime:.0f} min uptime{log_txt} — wedged", 0
        return "ok", "prediction cycle still running (state stale, still logging)", 0

    return "ok", HEALTHY, 0


def alert_for(action, reason, fails, incident_open, recent_starts, muted):
    """(title, message, priority) for a phone push, or None.

    recent_starts — starts/restarts in the last window, including this run's
    incident_open — an earlier alert of this incident has not been cleared yet
    muted         — a restart-loop alert already went out this window
    """
    if action in ("start", "restart"):
        if recent_starts >= RESTART_LOOP_COUNT:
            if muted:
                return None
            return (
                "DeepFieldPro restart loop",
                f"{recent_starts} restarts in the last hour and it keeps failing. "
                f"Last: {reason}. Check logs/server_*.err.log",
                "urgent",
            )
        verb = "started" if action == "start" else "restarted"
        return f"DeepFieldPro server {verb}", f"Watchdog {verb} the server: {reason}", "high"
    if action == "wait" and fails >= 2:
        return "DeepFieldPro unhealthy", f"{reason} - restarting if it persists", "default"
    # All-clear only on fresh state — not while a restarted server is still on
    # its first cycle (that pushed a premature "healthy again" on 2026-10-24).
    if action == "ok" and incident_open and reason == HEALTHY:
        return "DeepFieldPro healthy again", "Server is healthy again after the last alert", "low"
    return None


def server_roots(procs):
    """PIDs of independent server chains in [(pid, ppid, cmdline), ...].

    One server is a cmd wrapper -> venv launcher -> interpreter, all carrying
    the script name; a root is a server process whose parent is not one.
    """
    server = {pid for pid, _, cmd in procs if SERVER_SCRIPT in (cmd or "").lower()}
    return [pid for pid, ppid, cmd in procs if pid in server and ppid not in server]


def pick_port(preferred, is_listening, candidates=PORT_RANGE):
    """The preferred port unless something (an orphaned socket) holds it."""
    if not is_listening(preferred):
        return preferred
    for port in candidates:
        if port != preferred and not is_listening(port):
            return port
    return preferred


# ---------------------------------------------------------------------------
# System access
# ---------------------------------------------------------------------------


def _log(msg):
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    try:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def _load_state():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save_state(state):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f)
    except OSError:
        pass


def _list_procs():
    import psutil

    out = []
    for p in psutil.process_iter(["pid", "ppid", "cmdline", "create_time"]):
        try:
            cmd = " ".join(p.info["cmdline"] or [])
        except Exception:  # noqa: BLE001 - access denied on system processes
            continue
        out.append((p.info["pid"], p.info["ppid"], cmd, p.info["create_time"]))
    return out


def _server_pids(procs):
    return [pid for pid, _, cmd, _ in procs if SERVER_SCRIPT in (cmd or "").lower()]


def _listening_port(pids):
    import psutil

    for pid in pids:
        try:
            for conn in psutil.Process(pid).net_connections(kind="tcp"):
                if conn.status == psutil.CONN_LISTEN:
                    return conn.laddr.port
        except Exception:  # noqa: BLE001
            continue
    return None


def _log_idle_min():
    """Minutes since any server stdout log (logs/server_*.log) was written."""
    import glob

    logs = [p for p in glob.glob(os.path.join(ROOT, "logs", "server_*.log"))
            if not p.endswith(".err.log")]
    if not logs:
        return None
    return (time.time() - max(os.path.getmtime(p) for p in logs)) / 60


def _read_port():
    try:
        with open(PORT_FILE, encoding="utf-8") as f:
            return int(f.read().strip())
    except (OSError, ValueError):
        return DEFAULT_PORT


def _is_listening(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1.0)
        return s.connect_ex(("127.0.0.1", port)) == 0


def _get_health(port):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=15) as r:
            return json.loads(r.read())
    except Exception:  # noqa: BLE001 - any failure means "did not answer"
        return None


def _kill_servers(pids):
    import psutil

    victims = []
    for pid in pids:
        try:
            proc = psutil.Process(pid)
            victims.extend([proc] + proc.children(recursive=True))
        except psutil.NoSuchProcess:
            continue
    for proc in victims:
        try:
            proc.kill()
        except psutil.NoSuchProcess:
            pass
    psutil.wait_procs(victims, timeout=15)


def _push(title, message, priority):
    """Phone push via the project's ntfy topic, sent synchronously.

    NotificationManager._notify() sends from a daemon thread, which dies with
    this one-shot process before the request goes out — so call the senders
    directly, keeping its ntfy-then-WhatsApp fallback order.
    """
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    from src.services.alerting import NotificationManager

    nm = NotificationManager()
    sent = nm._send_ntfy(message, title=title, priority=priority, tags="rotating_light")
    if not sent:
        sent = nm._send_whatsapp(f"{title}: {message}")
    _log(f"alert {'sent' if sent else 'FAILED'}: {title} - {message}")
    return sent


def _start_server(port):
    """Launch via WMI so the server's parent is WmiPrvSE, independent of us."""
    day = time.strftime("%Y-%m-%d")
    inner = (
        f"set DEEPFIELD_PORT={port}&& set DEEPFIELD_ARENA_LIVE=0&& "
        f'"{PYTHON}" -u src\\{SERVER_SCRIPT} '
        f">> logs\\server_{day}.log 2>> logs\\server_{day}.err.log"
    )
    env = dict(os.environ, WD_CMD=f'cmd.exe /c "{inner}"', WD_DIR=ROOT)
    ps = (
        "$r = Invoke-CimMethod -ClassName Win32_Process -MethodName Create "
        "-Arguments @{ CommandLine = $env:WD_CMD; CurrentDirectory = $env:WD_DIR }; "
        '"$($r.ReturnValue) $($r.ProcessId)"'
    )
    res = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
        capture_output=True, text=True, timeout=60, env=env,
        creationflags=CREATE_NO_WINDOW,
    )
    parts = res.stdout.split()
    if len(parts) != 2 or parts[0] != "0":
        raise RuntimeError(f"Win32_Process.Create failed: {res.stdout!r} {res.stderr!r}")
    with open(PORT_FILE, "w", encoding="utf-8") as f:
        f.write(str(port))
    return int(parts[1])


# ---------------------------------------------------------------------------
# One run
# ---------------------------------------------------------------------------


def run_once(dry_run=False):
    state = _load_state()
    procs = _list_procs()
    roots = server_roots([(pid, ppid, cmd) for pid, ppid, cmd, _ in procs])
    pids = _server_pids(procs)
    created = [ct for pid, _, _, ct in procs if pid in pids]
    age_min = (time.time() - min(created)) / 60 if created else None
    port = _listening_port(pids) or _read_port()
    health = _get_health(port) if roots else None

    log_idle = _log_idle_min()
    action, reason, fails = decide(len(roots), age_min, health, state.get("fails", 0), log_idle)

    now = time.time()
    starts = [t for t in state.get("starts", []) if now - t < RESTART_LOOP_WINDOW_SEC]
    if action in ("start", "restart"):
        starts.append(now)
    muted = now < state.get("loop_muted_until", 0)
    incident_open = state.get("incident_open", False)
    alert = alert_for(action, reason, fails, incident_open, len(starts), muted)

    if dry_run:
        print(f"action={action} reason={reason} roots={roots} port={port} "
              f"uptime_min={age_min and round(age_min, 1)} log_idle_min={log_idle and round(log_idle, 1)} "
              f"fails={fails} alert={alert}")
        return action

    if action == "restart":
        _log(f"RESTART — {reason}; killing server pids {pids}")
        _kill_servers(pids)
        for _ in range(10):  # let the socket go before re-binding
            if not _is_listening(port):
                break
            time.sleep(1)
    if action in ("start", "restart"):
        new_port = pick_port(port, _is_listening)
        if new_port != port:
            _log(f"port {port} still held (orphaned socket?) — using {new_port}")
        pid = _start_server(new_port)
        _log(f"{'Started' if action == 'start' else 'Restarted'} server on port {new_port} "
             f"(WMI pid {pid}){'' if action == 'restart' else ' — ' + reason}")
    elif action == "wait":
        _log(f"WAIT — {reason}")
    elif state.get("last_action") not in (None, "ok"):
        _log(f"OK — {reason} (port {port})")

    # Alert only after acting: a failed push must never cost a restart.
    loop_muted_until = state.get("loop_muted_until", 0)
    if alert:
        try:
            _push(*alert)
        except Exception as e:  # noqa: BLE001
            _log(f"alert FAILED ({type(e).__name__}: {e}): {alert[0]}")
        if alert[2] == "urgent":
            loop_muted_until = now + RESTART_LOOP_WINDOW_SEC
        incident_open = action != "ok"
    elif action == "ok" and reason == HEALTHY:
        incident_open = False

    _save_state({
        "fails": fails,
        "last_action": action,
        "last_run": now,
        "starts": starts,
        "incident_open": incident_open,
        "loop_muted_until": loop_muted_until,
    })
    return action


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--dry-run", action="store_true", help="print the decision, change nothing")
    ap.add_argument("--test-alert", action="store_true", help="send one test push and exit")
    args = ap.parse_args(argv)
    try:
        if args.test_alert:
            return 0 if _push("DeepFieldPro watchdog test",
                              "Alerts are on: you'll get a push if the server is "
                              "restarted or stays unhealthy.", "default") else 1
        run_once(dry_run=args.dry_run)
    except Exception:  # noqa: BLE001 - a scheduled run has no console; leave a trace
        _log("WATCHDOG ERROR\n" + traceback.format_exc())
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
