"""
resume_after_payout.py — hold all betting until Polymarket pays out the QF book.

User directive (2026-07-06): don't spend the remaining cash; wait for the
quarter-final positions (England 19606965, Belgium 19606963, Spain 19606964,
Colombia 19606961) to settle and pay, THEN resume betting with the payout.

Polls every 10 minutes. Triggers when EITHER:
  - wallet available balance >= $27 (any single payout pushes it past this;
    current reserve is ~$16.73), OR
  - all four QF fixtures no longer appear in open holdings (fully resolved —
    even if they all lost, betting resumes with whatever remains).

On trigger: re-enables the arena autopilot (Forebet-only aggressive mode) and
relaunches tools/mar_leg_watcher.py to finish the France-Morocco triplet.
Gives up 2026-07-20 (after the final).

Launched detached:
    .venv\\Scripts\\python.exe tools\\resume_after_payout.py >> logs\\resume_watcher.log
"""

import datetime
import json
import os
import subprocess
import sys
import time

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

QF_FIXTURES = {"19606965", "19606963", "19606964", "19606961"}
BALANCE_TRIGGER = 27.0
DEADLINE = datetime.datetime(2026, 7, 20, tzinfo=datetime.timezone.utc)
POLL_SEC = 600
STATE = os.path.join(BASE, "data", "arena_autopilot.json")


def log(msg):
    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%m-%d %H:%M:%S")
    print(f"[RESUME-WATCHER {ts}] {msg}", flush=True)


def resume():
    try:
        ap = json.load(open(STATE, encoding="utf-8"))
        ap["enabled"] = True
        json.dump(ap, open(STATE, "w", encoding="utf-8"), indent=2)
        log("Autopilot RESUMED (enabled=true).")
    except Exception as e:
        log(f"FAILED to re-enable autopilot: {e}")
        return False
    try:
        py = os.path.join(BASE, ".venv", "Scripts", "python.exe")
        watcher = os.path.join(BASE, "tools", "mar_leg_watcher.py")
        out = open(os.path.join(BASE, "logs", "mar_watcher.log"), "a")
        subprocess.Popen([py, watcher], stdout=out, stderr=subprocess.STDOUT,
                         close_fds=False)
        log("Triplet watcher relaunched.")
    except Exception as e:
        log(f"triplet watcher relaunch failed (non-fatal): {e}")
    return True


def main():
    log(
        f"Holding all bets. Trigger: balance >= ${BALANCE_TRIGGER:.0f} "
        f"OR all QF positions {sorted(QF_FIXTURES)} resolved."
    )
    while datetime.datetime.now(datetime.timezone.utc) < DEADLINE:
        try:
            from src.arena_betting import get_exposure, get_wallet

            w = get_wallet() or {}
            bal = float(w.get("available_balance_usdc") or 0)
            if bal >= BALANCE_TRIGGER:
                log(f"Payout detected — balance ${bal:.2f} >= ${BALANCE_TRIGGER:.0f}.")
                if resume():
                    return
            exp = get_exposure() or {}
            holdings = exp.get("holdings") or exp.get("positions") or []
            open_qf = {
                str(h.get("fixture_id"))
                for h in holdings
                if str(h.get("fixture_id")) in QF_FIXTURES
                and float(h.get("value_usdc", 0) or 0) > 0
            }
            if not open_qf:
                log(f"All QF positions resolved (balance ${bal:.2f}) — resuming.")
                if resume():
                    return
        except Exception as e:
            log(f"poll error (will retry): {e}")
        time.sleep(POLL_SEC)
    log("Deadline reached — resuming as a failsafe so the tournament isn't idle.")
    resume()


if __name__ == "__main__":
    main()
