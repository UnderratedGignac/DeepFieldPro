"""
strategies_blueprint.py — per-strategy pages (2026-07-14).

/strategies           — overview: one card per strategy with its OWN virtual
                        bankroll (computed from bet_log; see strategy_ledger).
/strategy/<source>    — detail: that strategy's ledger + recent bets.

Read-only; self-contained HTML (no external assets).
"""

import html
import os

from flask import Blueprint, abort

from src.strategy_ledger import strategy_bets, strategy_ledgers

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BET_LOG = os.path.join(BASE, "data", "bet_log.db")

strategies_bp = Blueprint("strategies", __name__)

_LABELS = {
    "TIPSTER_FOREBET": "Forebet",
    "TIPSTER_APIFB": "API-Football",
    "TIPSTER_CONSENSUS": "Consensus (mix)",
    "STEAM": "Steam (top leagues)",
    "STEAM_LL": "Steam (lower leagues)",
    "PINNACLE_STEAM": "Pinnacle Steam",
    "SHARP_STEAM": "Sharp Steam",
}

_STYLE = """
<style>
 body{font-family:Segoe UI,system-ui,sans-serif;background:#0d1117;color:#e6edf3;margin:0;padding:24px}
 a{color:#58a6ff;text-decoration:none} h1{font-size:22px} h2{font-size:16px;color:#8b949e}
 .cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:14px;margin-top:18px}
 .card{background:#161b22;border:1px solid #30363d;border-radius:10px;padding:16px}
 .bal{font-size:26px;font-weight:700} .pos{color:#3fb950} .neg{color:#f85149}
 .muted{color:#8b949e;font-size:12px} .row{display:flex;justify-content:space-between;margin:3px 0;font-size:13px}
 table{width:100%;border-collapse:collapse;margin-top:14px;font-size:13px}
 th,td{padding:6px 8px;text-align:left;border-bottom:1px solid #21262d} th{color:#8b949e;font-weight:600}
 .W{color:#3fb950;font-weight:700} .L{color:#f85149;font-weight:700} .OPEN{color:#d29922} .VOID{color:#8b949e}
</style>
"""


def _fmt(v, plus=False):
    s = f"{v:+,.2f}" if plus else f"{v:,.2f}"
    return s


@strategies_bp.route("/strategies")
def strategies_overview():
    ledgers = strategy_ledgers(BET_LOG)
    cards = []
    order = list(_LABELS) + sorted(set(ledgers) - set(_LABELS))
    for src in order:
        led = ledgers.get(src)
        if not led:
            continue
        cls = "pos" if led["settled_pnl"] >= 0 else "neg"
        cards.append(f"""
        <a class="card" href="/strategy/{html.escape(src)}">
          <div class="muted">{html.escape(_LABELS.get(src, src))}</div>
          <div class="bal {cls}">${_fmt(led['total_value'])}</div>
          <div class="row"><span>Liquid</span><span>${_fmt(led['balance'])}</span></div>
          <div class="row"><span>At risk</span><span>${_fmt(led['open_stake'])} ({led['n_open']} open)</span></div>
          <div class="row"><span>Settled P&amp;L</span><span class="{cls}">${_fmt(led['settled_pnl'], plus=True)}</span></div>
          <div class="row"><span>Record</span><span>{led['n_won']}W / {led['n_lost']}L &middot; ROI {led['roi']:+.1f}%</span></div>
          <div class="muted">virtual bankroll &middot; starts at ${_fmt(led['starting'])}</div>
        </a>""")
    return (
        f"<!doctype html><title>Strategies</title>{_STYLE}"
        f"<h1>Strategy Bankrolls</h1>"
        f"<h2>Each strategy runs an isolated virtual bankroll computed from the verified bet record"
        f" &middot; <a href='/'>&larr; dashboard</a></h2>"
        f"<div class='cards'>{''.join(cards)}</div>"
    )


@strategies_bp.route("/strategy/<source>")
def strategy_detail(source):
    ledgers = strategy_ledgers(BET_LOG)
    led = ledgers.get(source)
    if not led:
        abort(404)
    rows = []
    for b in strategy_bets(BET_LOG, source):
        pnl = f"{b['pnl']:+,.2f}" if b["result"] in ("W", "L") else "—"
        rows.append(
            f"<tr><td>{html.escape(str(b['placed_at']))}</td>"
            f"<td>{html.escape(str(b['match']))}</td>"
            f"<td>{html.escape(str(b['league'] or ''))}</td>"
            f"<td>{html.escape(str(b['side']))} ({html.escape(str(b['market']))})</td>"
            f"<td>{b['odds']}</td><td>${b['stake']}</td>"
            f"<td class='{html.escape(str(b['result']))}'>{html.escape(str(b['result']))}</td>"
            f"<td>{pnl}</td></tr>"
        )
    cls = "pos" if led["settled_pnl"] >= 0 else "neg"
    return (
        f"<!doctype html><title>{html.escape(source)}</title>{_STYLE}"
        f"<h1>{html.escape(_LABELS.get(source, source))}</h1>"
        f"<h2><a href='/strategies'>&larr; all strategies</a></h2>"
        f"<div class='cards'><div class='card'>"
        f"<div class='muted'>Virtual bankroll</div><div class='bal {cls}'>${_fmt(led['total_value'])}</div>"
        f"<div class='row'><span>Liquid</span><span>${_fmt(led['balance'])}</span></div>"
        f"<div class='row'><span>At risk</span><span>${_fmt(led['open_stake'])} ({led['n_open']} open)</span></div>"
        f"<div class='row'><span>Settled</span><span>{led['n_won']}W / {led['n_lost']}L &middot; ROI {led['roi']:+.1f}%</span></div>"
        f"</div></div>"
        f"<table><tr><th>Placed (UTC)</th><th>Match</th><th>League</th><th>Bet</th>"
        f"<th>Odds</th><th>Stake</th><th>Result</th><th>P&amp;L</th></tr>{''.join(rows)}</table>"
    )
