"""
mar_leg_watcher.py — completes the FRA-MAR 1X2 triplet (draw leg already filled).

Two pending legs on France vs Morocco (fixture 19606972), polled every 10 min
until kickoff (2026-07-09 20:00 UTC):
  FRA — book currently has NO asks <= 0.32 (young market). Retry a $10 FOK
        whenever a seller appears at a sane price.
  MAR — Polymarket away token not linked in the Stair AI mapping yet. Place a
        $6 FOK as soon as the token appears.

Each leg fires once (registered in the autopilot's placed_keys). Exits when
both legs are done or at kickoff. Safe to re-run.

Launched detached:
    .venv\\Scripts\\python.exe tools\\mar_leg_watcher.py >> logs\\mar_watcher.log
"""

import datetime
import json
import os
import sys
import time

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

FIXTURE_ID = "19606972"
KICKOFF_UTC = datetime.datetime(2026, 7, 9, 20, 0, tzinfo=datetime.timezone.utc)
POLL_SEC = 600
STATE = os.path.join(BASE, "data", "arena_autopilot.json")

# leg key -> (team_code, usd_size, worst_price_fn)
FRA_SIZE = 10.0
FRA_MAX_PRICE = 0.45  # never pay more than 45c even if model says 73%
MAR_SIZE = 6.0
MAR_PRICE_PAD = 0.05  # cap = market mid + 5c
# 2026-07-06: MAR leg cancelled (user delegated for max EV — paying ~0.55 for
# a ~15-20% model shot is -EV; the draw @0.25 already covers the upset case).
SKIP_MAR = True


def log(msg):
    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%H:%M:%S")
    print(f"[TRIPLET-WATCHER {ts}] {msg}", flush=True)


def _placed_keys():
    try:
        return set(json.load(open(STATE, encoding="utf-8")).get("placed_keys") or [])
    except Exception:
        return set()


def register_key(outcome):
    try:
        ap = json.load(open(STATE, encoding="utf-8"))
        pk = set(ap.get("placed_keys") or [])
        pk.add(f"{FIXTURE_ID}:{outcome}")
        ap["placed_keys"] = sorted(pk)
        json.dump(ap, open(STATE, "w", encoding="utf-8"), indent=2)
    except Exception as e:
        log(f"placed_keys register failed (non-fatal): {e}")


def _fill_ok(sc, resp):
    """Only an explicit filled/completed status counts. FOK submissions come
    back 'unfilled' (pending) and often flip to 'rejected' seconds later —
    the list_orders recheck on the next poll is what confirms those."""
    if sc not in (200, 201):
        return False
    data = resp.get("data", resp) if isinstance(resp, dict) else {}
    return (data.get("status") or "").lower() in ("completed", "filled", "settled")


def main():
    done = _placed_keys()
    need_fra = f"{FIXTURE_ID}:home" not in done or True  # FRA FOKs rejected so far
    # placed_keys has :home registered to stop the AUTOPILOT double-betting;
    # track our own FRA fill separately in the log-driven loop below.
    fra_filled = False
    mar_filled = f"{FIXTURE_ID}:away" in done
    log(
        f"Watching FRA (fill pending) + MAR (token pending) on fixture {FIXTURE_ID} "
        f"until {KICKOFF_UTC:%Y-%m-%d %H:%M} UTC"
    )
    while datetime.datetime.now(datetime.timezone.utc) < KICKOFF_UTC:
        try:
            from src.arena_betting import (
                get_mapping,
                get_mid,
                list_orders,
                submit_order_fok,
            )

            # Re-check FRA fill status from the exchange (a completed FRA order
            # from any earlier attempt means the leg is done).
            if not fra_filled:
                try:
                    for o in list_orders(status="completed,filled,settled,closed") or []:
                        if (
                            str(o.get("fixture_id")) == FIXTURE_ID
                            and (o.get("team_code") or "").upper() == "FRA"
                        ):
                            fra_filled = True
                            log("FRA leg confirmed filled.")
                            break
                except Exception:
                    pass

            m = get_mapping(FIXTURE_ID) or {}

            # --- FRA leg: retry while book has no acceptable ask ---
            if not fra_filled:
                token_h = m.get("polymarket_home_token_yes")
                mid_h = None
                if token_h:
                    try:
                        mid_h = get_mid(token_h)
                    except Exception:
                        mid_h = None
                worst = round(min(FRA_MAX_PRICE, max(0.30, (mid_h or 0.145) + 0.10)), 2)
                sc, resp = submit_order_fok(FIXTURE_ID, "FRA", FRA_SIZE, worst)
                if _fill_ok(sc, resp):
                    fra_filled = True
                    log(f"FRA ${FRA_SIZE} FOK accepted @ worst {worst} (mid {mid_h}).")
                # rejected = still no seller; stay quiet and retry next poll

            # --- MAR leg: waits for the away token to link ---
            if SKIP_MAR:
                mar_filled = True  # treated as done; leg cancelled
            if not mar_filled:
                token_a = m.get("polymarket_away_token_yes")
                if token_a:
                    try:
                        mid_a = get_mid(token_a) or 0.0
                    except Exception:
                        mid_a = 0.0
                    worst = round(min(0.99, (mid_a or 0.60) + MAR_PRICE_PAD), 2)
                    log(f"MAR token linked! mid={mid_a} — placing ${MAR_SIZE} FOK @ worst {worst}")
                    sc, resp = submit_order_fok(FIXTURE_ID, "MAR", MAR_SIZE, worst)
                    log(f"MAR order result: {sc} {str(resp)[:200]}")
                    if _fill_ok(sc, resp):
                        mar_filled = True
                        register_key("away")

            if fra_filled and mar_filled:
                log("Triplet complete (FRA + draw + MAR all filled) — exiting.")
                return
        except Exception as e:
            log(f"poll error (will retry): {e}")
        time.sleep(POLL_SEC)
    log(
        f"Kickoff reached. Final state: FRA filled={fra_filled}, MAR filled={mar_filled}."
    )


if __name__ == "__main__":
    main()
