"""
Overnight watchdog for DeepFieldPro live server.

Monitors the dashboard server every 60 seconds. If it stops responding for
2 consecutive checks, kills all Python processes and relaunches the server.
Logs every event to logs/watchdog.log.

Usage (launched automatically by LAUNCH.bat):
    .venv\Scripts\python.exe tools\watchdog.py --port 5050
"""

import sys
import os
import time
import subprocess
import argparse
import signal

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_FILE = os.path.join(ROOT, "logs", "watchdog.log")

def _log(msg):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass

def _server_alive(port):
    try:
        import urllib.request
        urllib.request.urlopen(f"http://127.0.0.1:{port}/api/state", timeout=5)
        return True
    except Exception:
        return False

def _kill_python():
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-Process python -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue"],
            capture_output=True, timeout=10
        )
        time.sleep(3)
    except Exception:
        pass

def _launch_server(port):
    env = os.environ.copy()
    env["DEEPFIELD_PORT"] = str(port)
    env.pop("DEEPFIELD_ARENA_LIVE", None)

    log_path = os.path.join(ROOT, "logs", "server_shadow.log")
    with open(log_path, "a", encoding="utf-8") as lf:
        proc = subprocess.Popen(
            [os.path.join(ROOT, ".venv", "Scripts", "python.exe"),
             os.path.join(ROOT, "src", "live_dashboard_server.py")],
            cwd=ROOT,
            env=env,
            stdout=lf,
            stderr=lf,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
        )
    return proc

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=5050)
    parser.add_argument("--interval", type=int, default=60)
    args = parser.parse_args()

    os.makedirs(os.path.join(ROOT, "logs"), exist_ok=True)
    _log(f"Watchdog started — port={args.port} check_interval={args.interval}s")

    server_proc = None
    consecutive_failures = 0
    restarts = 0

    def _graceful_exit(sig, frame):
        _log("Watchdog received shutdown signal — exiting.")
        sys.exit(0)

    signal.signal(signal.SIGINT, _graceful_exit)
    signal.signal(signal.SIGTERM, _graceful_exit)

    # Give the server 20 seconds to come up on first start
    time.sleep(20)

    while True:
        alive = _server_alive(args.port)

        if alive:
            consecutive_failures = 0
        else:
            consecutive_failures += 1
            _log(f"Server not responding (failure {consecutive_failures}/2)")

        if consecutive_failures >= 2:
            restarts += 1
            _log(f"SERVER DOWN — restarting (restart #{restarts})")
            _kill_python()
            time.sleep(2)

            # Find a free port starting from args.port
            free_port = args.port
            import socket
            for p in range(args.port, args.port + 20):
                try:
                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                        s.bind(("127.0.0.1", p))
                    free_port = p
                    break
                except OSError:
                    continue

            if free_port != args.port:
                _log(f"Original port {args.port} busy — using {free_port}")
                # Write new port so other tools can pick it up
                with open(os.path.join(ROOT, "current_port.txt"), "w") as f:
                    f.write(str(free_port))
                args.port = free_port

            server_proc = _launch_server(args.port)
            _log(f"Server relaunched on port {args.port} (pid={server_proc.pid})")
            consecutive_failures = 0
            time.sleep(15)  # allow extra startup time after restart

        time.sleep(args.interval)


if __name__ == "__main__":
    main()
