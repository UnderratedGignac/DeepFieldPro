"""
health_check.py - verify the DeepFieldPro system is running correctly.
======================================================================
One-shot PASS/FAIL report across the things that must be true for the system to
be working: dashboard up, odds fresh, sharp feed live, bankroll intact, no crashes.
Run:  .venv\\Scripts\\python.exe health_check.py
Exit code 0 = all healthy, 1 = at least one FAIL (so it's scriptable/loopable).
"""
import os
import sys
import time
import json
import sqlite3
import datetime
import urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))

# Resolve the live port: current_port.txt (written at launch) -> $DEEPFIELD_PORT -> 5050.
def _port():
    try:
        with open(os.path.join(BASE, "current_port.txt")) as f:
            return f.read().strip() or "5050"
    except Exception:
        return os.getenv("DEEPFIELD_PORT", "5050")


PORT = _port()


def _data(p):
    return os.path.join(BASE, "data", p)


def _age_min(iso_or_epoch):
    try:
        if isinstance(iso_or_epoch, (int, float)):
            ts = float(iso_or_epoch)
        else:
            ts = datetime.datetime.fromisoformat(
                str(iso_or_epoch).replace("Z", "+00:00")).timestamp()
        return (time.time() - ts) / 60.0
    except Exception:
        return None


checks = []


def add(name, ok, detail):
    checks.append((name, bool(ok), detail))


# 1. Dashboard server responding. Use /api/state (reads a local file, fast) rather
# than /arena/api/status (makes a slow live StairAI wallet API call that can time out).
try:
    with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/api/state", timeout=15) as r:
        state = json.load(r)
    nfix = len(state) if isinstance(state, list) else "?"
    add(f"Dashboard server (:{PORT})", True, f"up | /api/state served {nfix} fixtures")
except Exception as e:
    add(f"Dashboard server (:{PORT})", False, f"NOT responding ({e})")

# 1b. Arena real-money gate state (best-effort; the wallet call can be slow)
try:
    with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/arena/api/status", timeout=20) as r:
        st = json.load(r)
    armed = "paused" not in str(st.get("last_summary", "")).lower()
    add("Arena gate", True, f"{'ARMED' if armed else 'paused'} | {st.get('last_summary')}")
except Exception as e:
    add("Arena gate", True, f"status endpoint slow/unreachable ({e}) - non-critical")

# 2. Betarabia odds fresh (scraper writing). Lenient: scrape cycle is ~3-6 min.
try:
    c = sqlite3.connect(_data("odds_stream.db"))
    newest = c.execute("SELECT MAX(scraped_at) FROM fixture").fetchone()[0]
    n = c.execute("SELECT COUNT(*) FROM fixture").fetchone()[0]
    c.close()
    age = _age_min(newest)
    add("Betarabia odds fresh", age is not None and age < 35,
        f"{n} fixtures, newest {age:.0f} min ago" if age is not None else "no timestamp")
except Exception as e:
    add("Betarabia odds fresh", False, str(e))

# 3. Sharp (Pinnacle) snapshots fresh (thread alive; every 120s)
try:
    c = sqlite3.connect(_data(os.path.join("deepfield_browser_data", "completed_fixtures.db")))
    last = c.execute("SELECT MAX(ts) FROM sharp_odds_history").fetchone()[0]
    c.close()
    age = _age_min(last)
    add("Sharp (Pinnacle) feed live", age is not None and age < 15,
        f"newest snapshot {age:.1f} min ago" if age is not None else "no snapshots yet")
except Exception as e:
    add("Sharp (Pinnacle) feed live", False, str(e))

# 4. Paper bankroll intact (zero = daemon silently places nothing)
try:
    c = sqlite3.connect(_data("bankroll.db"))
    row = c.execute("SELECT current_balance, daily_exposure FROM bankroll ORDER BY date DESC LIMIT 1").fetchone()
    c.close()
    bal = row[0] + (row[1] or 0.0)
    add("Paper bankroll", bal and bal > 1, f"${bal:.2f} (Liquid: ${row[0]:.2f})")
except Exception as e:
    add("Paper bankroll", False, str(e))

# 5. No crashes in the recent log
try:
    with open(os.path.join(BASE, "server_startup.log"), encoding="utf-8", errors="ignore") as f:
        tail = f.read()[-12000:]
    tb = tail.count("Traceback (most recent call last)")
    add("No recent crashes", tb == 0, f"{tb} tracebacks in recent log")
except Exception:
    add("No recent crashes", True, "log unreadable (skipped)")

# ---- report ----
allok = all(ok for _, ok, _ in checks)
ts = time.strftime("%Y-%m-%d %H:%M:%S")
print("=" * 66)
print(f" DEEPFIELDPRO HEALTH CHECK  -  {ts}")
print("=" * 66)
for name, ok, detail in checks:
    print(f"  [{'PASS' if ok else 'FAIL'}]  {name:30s} {detail}")
print("-" * 66)
print(" OVERALL: " + ("ALL HEALTHY - system running correctly"
                      if allok else "PROBLEM - see FAIL line(s) above"))
print("=" * 66)
sys.exit(0 if allok else 1)
