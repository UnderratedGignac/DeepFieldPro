"""
attribution_engine.py — Phase 3 (Paper vs Live Attribution) for the StairAI
Arena real-money betting path.

For every SETTLED bet in the Arena autopilot state, computes realized P&L
under counterfactual scenarios and attributes the gap between "what we
actually made" and "what a perfect-execution version would have made" to
distinct causes: prediction quality, execution, fees, and sizing.

Read-only: this module never places orders or mutates arena_autopilot.json.
It's a reporting tool over the SAME settled-bet history arena_betting.py
already accumulates in state["placed"] + state["settlements"].

Known limitations (stated explicitly per "verify assumptions" — do not treat
these numbers as more precise than they are):
  - Historical wallet_balance at placement time isn't recorded per-bet
    (state["placed"] entries don't carry it), so the "pure_kelly" sizing
    counterfactual uses the CURRENT wallet balance as a stand-in when one
    isn't supplied. This is an approximation, not a reconstruction of the
    true historical bankroll trajectory.
  - Polymarket's CLOB (as exposed through this StairAI proxy) does not charge
    an explicit per-trade fee visible in any API response seen so far. The
    "fees" attribution bucket is therefore reported as the (limit_price -
    market_mid) markup this system pays to help fills clear (LIMIT_BUFFER),
    NOT a separate exchange fee — if StairAI charges its own platform fee,
    it is not visible in the data this module reads, and this is flagged
    rather than assumed to be zero.
  - "Timing" attribution (what a differently-timed entry would have earned)
    needs multiple price snapshots per fixture over time, which this project
    only started collecting for STEAM/CLV analysis on a subset of bets. Where
    unavailable, this module reports timing_attribution=None rather than a
    fabricated number.
"""

STAKE_KEYS = ("staked_usd", "usd_size")


def binary_payout(stake_usd, price, won):
    """
    P&L in USD for a binary Polymarket "buy YES at `price`" position of
    `stake_usd` notional. A win pays $1 per share bought (stake_usd / price
    shares); a loss pays $0. Returns realized P&L (can be negative).
    """
    if not price or price <= 0:
        return -stake_usd if not won else 0.0
    shares = stake_usd / price
    return (shares * 1.0 - stake_usd) if won else -stake_usd


def settlement_map(state):
    """{fixture_id: winning_outcome} from state['settlements']."""
    out = {}
    for s in state.get("settlements", []) or []:
        fid = s.get("fixture_id")
        outcome = s.get("outcome")
        if fid and outcome:
            out[str(fid)] = outcome
    return out


def build_attribution_report(state, current_wallet_balance=None, kelly_fn=None):
    """
    Build the Phase 3 attribution report from an arena_autopilot.json-shaped
    `state` dict (as returned by arena_betting._load_state()).

    `kelly_fn` — optional callable(edge, market_mid, wallet_balance) -> usd,
    used for the pure_kelly counterfactual. Injected rather than imported
    directly so this module has no hard dependency on arena_betting.py
    (keeps it independently testable and avoids a circular import, since
    arena_betting.py may in turn want to call into this module later).

    Returns a dict with per-scenario totals and an attribution breakdown.
    Returns a valid (not error) zero-bet structure when there are no settled
    bets yet — expected early in a tournament, not a failure.
    """
    settled = settlement_map(state)
    rows = []
    for p in state.get("placed", []) or []:
        if not p.get("ok"):
            continue
        fid = p.get("fixture_id")
        winning_outcome = settled.get(str(fid))
        if winning_outcome is None:
            continue  # not settled yet
        stake = next((p.get(k) for k in STAKE_KEYS if p.get(k) is not None), None)
        if stake is None:
            continue
        won = p.get("outcome") == winning_outcome
        rows.append(
            {
                "fixture_id": fid,
                "match": p.get("match"),
                "outcome": p.get("outcome"),
                "won": won,
                "stake": float(stake),
                "limit_price": p.get("limit_price"),
                "market_mid": p.get("market_mid"),
                "edge": None,  # p["edge_pp"] is in percentage points, not fraction
                "edge_pp": p.get("edge_pp"),
                "model_prob": p.get("model_prob"),
            }
        )

    if not rows:
        return {
            "n_settled": 0,
            "scenarios": {},
            "attribution": {
                "prediction": None,
                "execution": None,
                "fees": None,
                "sizing": None,
                "timing": None,
            },
            "note": "No settled real-money bets yet — nothing to attribute.",
        }

    scenarios = {"actual": [], "midpoint": [], "zero_fee": [], "pure_kelly": []}
    for r in rows:
        limit_price = r["limit_price"]
        mid = r["market_mid"]
        won = r["won"]
        stake = r["stake"]

        scenarios["actual"].append(binary_payout(stake, limit_price, won))
        # midpoint: same stake, but as if filled at the raw mid (no
        # LIMIT_BUFFER markup paid to help the order clear).
        scenarios["midpoint"].append(binary_payout(stake, mid, won))
        # zero_fee: no separate exchange fee is visible in this system's data
        # (see module docstring) — currently identical to midpoint. Reported
        # separately so a future fee discovery only requires changing this
        # one line, not the report shape.
        scenarios["zero_fee"].append(binary_payout(stake, mid, won))

        if kelly_fn is not None and r["edge_pp"] is not None and mid:
            edge_frac = r["edge_pp"] / 100.0
            wb = current_wallet_balance if current_wallet_balance is not None else 999.0
            try:
                kelly_stake = kelly_fn(edge_frac, mid, wb)
            except Exception:
                kelly_stake = stake
            scenarios["pure_kelly"].append(binary_payout(kelly_stake, limit_price, won))
        else:
            scenarios["pure_kelly"].append(binary_payout(stake, limit_price, won))

    totals = {name: round(sum(vals), 2) for name, vals in scenarios.items()}
    total_staked = round(sum(r["stake"] for r in rows), 2)

    def _roi(pnl):
        return round(pnl / total_staked, 4) if total_staked else None

    return {
        "n_settled": len(rows),
        "total_staked": total_staked,
        "scenarios": {
            name: {"total_pnl": totals[name], "roi": _roi(totals[name])}
            for name in scenarios
        },
        "attribution": {
            # Execution: the gap between what we actually earned and what
            # perfect-midpoint execution would have earned, at the SAME stake.
            "execution": round(totals["actual"] - totals["midpoint"], 2),
            # Fees: gap between midpoint and zero_fee — see docstring, this is
            # 0 by construction today since no separate fee is observable.
            "fees": round(totals["midpoint"] - totals["zero_fee"], 2),
            # Sizing: gap between actual (production sizing) and pure_kelly
            # (what a stake computed purely from the Kelly formula would earn
            # at the SAME fill price) — isolates sizing-policy impact from
            # execution/prediction quality.
            "sizing": round(totals["actual"] - totals["pure_kelly"], 2),
            # Prediction: not separable from a single settled-bet history
            # without a counterfactual model — reported as the model's
            # realized hit rate vs its own average implied probability,
            # a calibration proxy, not a P&L attribution number.
            "prediction": _calibration_proxy(rows),
            "timing": None,  # see module docstring — insufficient snapshot data
        },
    }


def _calibration_proxy(rows):
    """
    Average model_prob vs realized win rate across settled rows — a rough
    "is the model's confidence honest" signal, used as the prediction-quality
    proxy in the attribution report (see build_attribution_report docstring;
    this is NOT a P&L-denominated attribution, unlike the other buckets).
    """
    probs = [r["model_prob"] for r in rows if r["model_prob"] is not None]
    if not probs:
        return None
    avg_prob = sum(probs) / len(probs)
    win_rate = sum(1 for r in rows if r["won"]) / len(rows)
    return {"avg_model_prob": round(avg_prob, 4), "realized_win_rate": round(win_rate, 4)}
