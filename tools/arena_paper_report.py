"""Grade the arena's PAPER-mode shadow bets against real Polymarket settlements.

Reads data/arena_autopilot.json (read-only): joins placed entries carrying
paper=True with state["settlements"] (written by the autopilot's own
settlement checker from the real Polymarket resolution feed).

P&L model per paper bet: buying the outcome token at limit_price with $stake
pays stake/limit_price if the outcome wins (token settles at $1), else 0.
  win  -> pnl = stake * (1/limit_price - 1)
  loss -> pnl = -stake

Usage:  .venv\\Scripts\\python.exe tools\\arena_paper_report.py
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_FILE = os.path.join(ROOT, "data", "arena_autopilot.json")


def load_state(path=STATE_FILE):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def grade(state):
    settled = {str(s["fixture_id"]): s["outcome"] for s in state.get("settlements", [])}
    rows = []
    for p in state.get("placed", []):
        if not p.get("paper") or not p.get("ok"):
            continue
        stake = float(p.get("staked_usd") or 0)
        price = float(p.get("limit_price") or 0)
        winner = settled.get(str(p.get("fixture_id")))
        if winner is None:
            result, pnl = "OPEN", 0.0
        elif winner == p.get("outcome"):
            result = "WIN"
            pnl = stake * (1.0 / price - 1.0) if price > 0 else 0.0
        else:
            result, pnl = "LOSS", -stake
        rows.append(
            {
                "match": p.get("match"),
                "outcome": p.get("outcome"),
                "stake": stake,
                "price": price,
                "model_prob": p.get("model_prob"),
                "edge_pp": p.get("edge_pp"),
                "result": result,
                "pnl": round(pnl, 2),
                "ts": p.get("ts"),
            }
        )
    return rows


def summarize(rows):
    closed = [r for r in rows if r["result"] in ("WIN", "LOSS")]
    wins = sum(1 for r in closed if r["result"] == "WIN")
    staked = sum(r["stake"] for r in closed)
    pnl = sum(r["pnl"] for r in closed)
    return {
        "paper_bets": len(rows),
        "open": sum(1 for r in rows if r["result"] == "OPEN"),
        "settled": len(closed),
        "wins": wins,
        "win_rate_pct": round(100.0 * wins / len(closed), 1) if closed else None,
        "staked": round(staked, 2),
        "pnl": round(pnl, 2),
        "roi_pct": round(100.0 * pnl / staked, 1) if staked else None,
    }


def main():
    state = load_state()
    rows = grade(state)
    if not rows:
        print("No arena paper bets recorded yet (paper mode places them only "
              "when a pick passes every gate).")
        return
    for r in rows:
        print(
            f"{r['ts']}  {r['match']:<32} {r['outcome']:<5} "
            f"${r['stake']:>6.2f} @ {r['price']:.2f}  "
            f"model {r['model_prob']:.0%}  edge {r['edge_pp']:+.1f}pp  "
            f"{r['result']:<4} pnl ${r['pnl']:+.2f}"
        )
    print("\nSUMMARY:", json.dumps(summarize(rows)))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
