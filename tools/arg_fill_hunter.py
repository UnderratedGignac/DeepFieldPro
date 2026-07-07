"""
arg_fill_hunter.py — persistent fill-hunter for the Argentina QF bet.

The ARG-EGY Polymarket book has no asks <= 0.70 yet (empty ask side). This
script polls every 10 minutes until kickoff (2026-07-07 16:00 UTC):
  1. If ANY completed ARG order exists on the exchange (ours or the
     autopilot's), register the dedup key and exit — the bet is done.
  2. Otherwise fire a $49 FOK capped at 0.70 (still +EV vs the model's
     0.73-0.79 win probability; above ~0.75 the edge is gone, so never chase).

Launched detached:
    .venv\\Scripts\\python.exe tools\\arg_fill_hunter.py >> logs\\arg_hunter.log
"""

import datetime
import json
import os
import sys
import time

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

FIXTURE_ID = "19606962"
TEAM_CODE = "ARG"
USD_SIZE = 49.0
WORST_PRICE = 0.70
KICKOFF_UTC = datetime.datetime(2026, 7, 7, 16, 0, tzinfo=datetime.timezone.utc)
POLL_SEC = 600
STATE = os.path.join(BASE, "data", "arena_autopilot.json")


def log(msg):
    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%m-%d %H:%M:%S")
    print(f"[ARG-HUNTER {ts}] {msg}", flush=True)


def register_key():
    try:
        ap = json.load(open(STATE, encoding="utf-8"))
        pk = set(ap.get("placed_keys") or [])
        pk.add(f"{FIXTURE_ID}:home")
        ap["placed_keys"] = sorted(pk)
        json.dump(ap, open(STATE, "w", encoding="utf-8"), indent=2)
    except Exception as e:
        log(f"placed_keys register failed (non-fatal): {e}")


def main():
    log(f"Hunting ARG fill: ${USD_SIZE} capped at {WORST_PRICE} until {KICKOFF_UTC:%m-%d %H:%M} UTC")
    while datetime.datetime.now(datetime.timezone.utc) < KICKOFF_UTC:
        try:
            from src.arena_betting import get_wallet, list_orders, submit_order_fok

            # 1. Already filled by anyone?
            for o in list_orders(status="completed,filled,settled,closed") or []:
                if (
                    str(o.get("fixture_id")) == FIXTURE_ID
                    and (o.get("team_code") or "").upper() == TEAM_CODE
                ):
                    log(
                        f"ARG already filled: ${o.get('usd_size')} @ {o.get('fill_price')} — done."
                    )
                    register_key()
                    return

            # 2. Size to available cash (payouts may have changed the wallet)
            w = get_wallet() or {}
            bal = float(w.get("available_balance_usdc") or 0)
            size = round(min(USD_SIZE, max(0.0, bal - 0.5)), 2)
            if size < 1.0:
                log(f"balance ${bal:.2f} too low to bet — waiting.")
            else:
                sc, resp = submit_order_fok(FIXTURE_ID, TEAM_CODE, size, WORST_PRICE)
                data = resp.get("data", resp) if isinstance(resp, dict) else {}
                status = (data.get("status") or "").lower()
                if sc in (200, 201) and status in ("completed", "filled"):
                    log(f"FILLED: ${size} @ {data.get('avg_fill_price')}")
                    register_key()
                    return
                # 'unfilled' acceptances usually flip to rejected; the next
                # poll's step-1 check catches a genuine late fill.
                log(
                    f"attempt ${size} @ cap {WORST_PRICE}: sc={sc} status={status or '?'}"
                    f" — no sellers at/below cap yet"
                )
        except Exception as e:
            log(f"poll error (will retry): {e}")
        time.sleep(POLL_SEC)
    log("Kickoff reached without an acceptable fill — no ARG bet (never chased past 0.70).")


if __name__ == "__main__":
    main()
