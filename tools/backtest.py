"""
backtest.py — replay the recorded bet history under different betting rules.
============================================================================
Pure analysis over data/bet_log.db. Never places bets, never touches the live
system. Use it to SEE what a rule change would have done before risking money.

For each settled bet we recover:
    model_prob = 1 / fair_odds      (fair_odds = round(100/prob_pct, 3))
    market_odds = entry_odds
    won = result starts with 'W'

A strategy is a set of filters + a staking rule. We re-simulate the bankroll
sequentially (ordered by placed_at) so drawdown and growth are realistic.

Usage:
    .venv\\Scripts\\python.exe tools\\backtest.py
    .venv\\Scripts\\python.exe tools\\backtest.py --markets 1X2 --no-draws --start-bankroll 53
"""

import argparse
import os
import sqlite3

DB = os.path.join(os.path.dirname(__file__), "..", "data", "bet_log.db")


def load_settled():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    rows = [
        dict(r) for r in con.execute("SELECT * FROM bet_log ORDER BY placed_at ASC")
    ]
    con.close()
    out = []
    for r in rows:
        res = str(r.get("result", "")).upper()
        if res not in ("W", "L", "WIN", "LOSS", "WON", "LOST"):
            continue
        try:
            fo = float(r["fair_odds"])
            eo = float(r["entry_odds"])
        except (TypeError, ValueError):
            continue
        if fo <= 0 or eo <= 1:
            continue
        out.append(
            {
                "ts": r.get("placed_at"),
                "market": r.get("market_type"),
                "side": r.get("side") or "",
                "odds": eo,
                "model_prob": 1.0 / fo,  # recovered model probability
                "won": res.startswith("W"),
            }
        )
    return out


def kelly_fraction(p, odds, mult, cap):
    b = odds - 1.0
    if b <= 0:
        return 0.0
    f = (p * odds - 1.0) / b
    return max(0.0, min(cap, f * mult))


def simulate(
    bets,
    *,
    markets=None,
    exclude_draws=False,
    sides=None,
    min_ev=None,
    min_odds=None,
    max_odds=None,
    calibrate=None,
    start_bankroll=1000.0,
    kelly_mult=0.20,
    kelly_cap=0.05,
    flat_stake=None,
):
    """Return summary dict. calibrate: optional fn(model_prob)->cal_prob."""
    bankroll = start_bankroll
    peak = start_bankroll
    max_dd = 0.0
    n = wins = 0
    staked = pnl = 0.0
    curve = [start_bankroll]
    for bt in bets:
        if markets and bt["market"] not in markets:
            continue
        if exclude_draws and bt["market"] == "1X2" and "Draw" in bt["side"]:
            continue
        if sides and not any(s in bt["side"] for s in sides):
            continue
        p = calibrate(bt["model_prob"]) if calibrate else bt["model_prob"]
        odds = bt["odds"]
        if min_odds is not None and odds < min_odds:
            continue
        if max_odds is not None and odds > max_odds:
            continue
        ev = p * odds - 1.0
        if min_ev is not None and ev < min_ev:
            continue
        if flat_stake is not None:
            stake = min(flat_stake, bankroll)
        else:
            f = kelly_fraction(p, odds, kelly_mult, kelly_cap)
            stake = round(bankroll * f, 2)
        if stake <= 0:
            continue
        n += 1
        staked += stake
        if bt["won"]:
            wins += 1
            gain = stake * (odds - 1.0)
        else:
            gain = -stake
        pnl += gain
        bankroll += gain
        peak = max(peak, bankroll)
        max_dd = max(max_dd, (peak - bankroll) / peak if peak > 0 else 0.0)
        curve.append(round(bankroll, 2))
        if bankroll <= 0:
            break
    return {
        "n": n,
        "wins": wins,
        "hit": (wins / n if n else 0.0),
        "staked": staked,
        "pnl": pnl,
        "roi": (pnl / staked if staked else 0.0),
        "start": start_bankroll,
        "final": bankroll,
        "growth": (bankroll / start_bankroll - 1.0) if start_bankroll else 0.0,
        "max_dd": max_dd,
        "busted": bankroll <= 0,
    }


def fmt(name, s):
    bust = "  *** BUSTED ***" if s["busted"] else ""
    return (
        f"{name:34s} n={s['n']:4d} hit={s['hit']:5.1%} "
        f"ROI={s['roi']:+7.1%} | ${s['start']:.0f}->${s['final']:8.2f} "
        f"({s['growth']:+.0%}) maxDD={s['max_dd']:4.0%}{bust}"
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--markets", nargs="*", default=None)
    ap.add_argument("--no-draws", action="store_true")
    ap.add_argument("--sides", nargs="*", default=None)
    ap.add_argument("--start-bankroll", type=float, default=1000.0)
    ap.add_argument("--kelly-mult", type=float, default=0.20)
    ap.add_argument("--min-ev", type=float, default=None)
    args = ap.parse_args()

    bets = load_settled()
    print(f"Loaded {len(bets)} settled bets from bet_log.db\n")
    sb = args.start_bankroll

    print("=== HEAD-TO-HEAD: each rule applied on top of the previous ===")
    # 0. Baseline: everything, flat $ proportional to recorded behaviour (Kelly on all markets)
    print(
        fmt(
            "0 baseline (all markets, Kelly)",
            simulate(bets, start_bankroll=sb, kelly_mult=args.kelly_mult),
        )
    )
    # 1. 1X2 only
    print(
        fmt(
            "1 +1X2 only",
            simulate(
                bets, markets={"1X2"}, start_bankroll=sb, kelly_mult=args.kelly_mult
            ),
        )
    )
    # 2. 1X2, no draws
    print(
        fmt(
            "2 +no draws",
            simulate(
                bets,
                markets={"1X2"},
                exclude_draws=True,
                start_bankroll=sb,
                kelly_mult=args.kelly_mult,
            ),
        )
    )
    # 3. 1X2, no draws, require +EV
    print(
        fmt(
            "3 +require EV>0",
            simulate(
                bets,
                markets={"1X2"},
                exclude_draws=True,
                min_ev=0.0,
                start_bankroll=sb,
                kelly_mult=args.kelly_mult,
            ),
        )
    )
    # 4. + Home/Away only
    print(
        fmt(
            "4 +home/away only",
            simulate(
                bets,
                markets={"1X2"},
                exclude_draws=True,
                min_ev=0.0,
                sides=["Home", "Away"],
                start_bankroll=sb,
                kelly_mult=args.kelly_mult,
            ),
        )
    )

    print("\n=== STAKING comparison on the disciplined slice (1X2, no draws, EV>0) ===")
    common = dict(markets={"1X2"}, exclude_draws=True, min_ev=0.0, start_bankroll=sb)
    print(fmt("flat $1", simulate(bets, flat_stake=1.0, **common)))
    print(fmt("1/8 Kelly", simulate(bets, kelly_mult=0.125, **common)))
    print(fmt("1/5 Kelly", simulate(bets, kelly_mult=0.20, **common)))
    print(fmt("1/2 Kelly (aggressive)", simulate(bets, kelly_mult=0.50, **common)))
    print(fmt("Full Kelly (reckless)", simulate(bets, kelly_mult=1.0, **common)))

    print("\nNote: results are in-sample on a SMALL history. Treat as directional,")
    print("not a promise — the value is the RANKING of rules, not the exact ROI.")


if __name__ == "__main__":
    main()
