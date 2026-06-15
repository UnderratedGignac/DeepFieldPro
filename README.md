# DeepFieldPro

A football (soccer) **betting research platform**. It scrapes fixtures and odds, runs
ML models to estimate match probabilities, compares those to live market prices, and
surfaces recommendations on a local web dashboard. It can place **real money** on one
narrow, disciplined path (StairAI Arena) and runs everything else as **paper/shadow**
bets for measurement.

> **The honest headline:** the system does **not** yet have a proven betting edge. Its
> core value right now is *measurement* — accumulating clean Closing-Line-Value (CLV)
> data to find out whether any strategy actually beats the market before risking money.
> See [Design philosophy](#design-philosophy) and `ARCHITECTURE_AND_DESIGN.md`.

---

## Quick start

```powershell
# 1. Start everything (dashboard + prediction daemon + scrapers + autopilot)
RESTART_CLEAN.bat

# 2. Open the dashboard (the bat prints the exact port; default 5058)
#    http://127.0.0.1:5058/

# 3. Verify it's running correctly
.venv\Scripts\python.exe health_check.py
```

`RESTART_CLEAN.bat` is the **only launcher you should use**. It kills stray Python,
auto-picks a free port (avoiding zombie sockets — see below), records it in
`current_port.txt`, arms the real-money gate, and launches a single server instance.

To stop everything: `taskkill /F /IM python.exe`

---

## What runs

One process (`src/live_dashboard_server.py`) hosts a Flask dashboard **and** a background
daemon thread that loops every ~30s:

```
scrape odds (Betarabia) ─┐
fetch fixtures ──────────┼─► run ML models ─► write dashboard state ─► place paper bets ─► settle finished bets
sharp odds (Pinnacle) ───┘
```

Plus three helper threads: closing-line capture (for true CLV), sharp-odds snapshots,
and the StairAI Arena autopilot (real money, gated off by default).

---

## The three betting strategies (all paper unless noted)

| Source | Signal | Stake | Status |
|---|---|---|---|
| **AI** | Dixon-Coles model probability vs market | fractional Kelly | Paper. No proven edge (see docs). |
| **STEAM** | Line moved ≥5% toward a side (validated signal) | flat $25 | Paper. The most promising signal. |
| **SHARP / SHARPV** | Pinnacle steam + Betarabia lagging the sharp price | flat $25 | Paper. Needs data to judge. |
| **Arena** | 1X2-only, model vs Polymarket, World Cup | capped, confirm-gated | **REAL MONEY** — see Safety. |

Only **1X2** (home/draw/away) is bet. All prop markets are disabled (they lose — see docs).

---

## Daily operations

| Task | Command |
|---|---|
| Start / restart cleanly | `RESTART_CLEAN.bat` |
| Health check (is it working?) | `.venv\Scripts\python.exe health_check.py` |
| Prove it needs no free API key | `.venv\Scripts\python.exe resilience_check.py` |
| Is any strategy profitable yet? | `.venv\Scripts\python.exe tools\edge_status.py` |
| Steam strategy report | `.venv\Scripts\python.exe tools\steam_report.py` |
| CLV report | `.venv\Scripts\python.exe tools\clv_report.py` |
| Reset paper bankroll (paper only) | `.venv\Scripts\python.exe tools\reset_paper_bankroll.py` |

A recurring health check is scheduled in-session (every 30 min) when you run `/loop`.

---

## Safety — read before running

Real money flows through **exactly one path** and is protected by **two independent locks
that must both be set**:

1. **Environment gate** — `DEEPFIELD_ARENA_LIVE=1` must be set in the *same shell* that
   launches the server. It is session-scoped on purpose (a crashed/zombie process can't
   silently re-arm it). `RESTART_CLEAN.bat` sets it; remove that line to run paper-only.
2. **State gate** — `data/arena_autopilot.json` must have `enabled: true`.

Additional real-money protections: $5/order cap, wallet buffer, `MAX_BETS_PER_RUN`,
`confirm: true` required on the place endpoint, World-Cup-only, pre-kickoff-only.

The paper daemon's own order-POST is **hard-gated off** (`DEEPFIELD_DAEMON_LIVE_ORDERS`,
do **not** set it). Wallet is ~$53.

---

## Keyless by design

The **only** API key the system depends on is `STAIR_AI_API_KEY`, and only for placing
real money. Everything else — fixtures, odds, sharp prices, results/settlement,
predictions, dashboard — runs on **keyless** sources. If your free API-Football key dies
or its quota runs out, nothing breaks. Prove it anytime:

```powershell
.venv\Scripts\python.exe resilience_check.py
```

---

## Design philosophy

- **CLV-first.** Don't add bet types; prove an edge. A strategy is only trusted once it
  beats the closing line over ≥100 settled bets (`tools/edge_status.py`).
- **Settlement never lies.** Bets are graded from real scores only; if data is missing the
  bet stays OPEN. Nothing is ever fabricated.
- **Keyless core, single keyed exception.** Resilience over convenience.
- **Two-lock real money.** Defense in depth so no single failure can place a real bet.

Full reasoning, component-by-component, in **`ARCHITECTURE_AND_DESIGN.md`**.

---

## Key files

```
src/live_dashboard_server.py    Flask app + starts the daemon thread
src/live_predictions_daemon.py  the engine (scrape→predict→bet→settle)
src/betarabia_scraper.py        keyless odds scraper (Playwright/Kickertech)
src/sharp_scraper.py            Pinnacle 1X2 via public guest API
src/sharp_edge.py               sharp-steam + lagging-value engine
src/arena_betting.py            StairAI Arena (the real-money path)
src/free_results_scraper.py     keyless settlement results (ESPN + TheSportsDB)
tools/                          analytics + training (edge_status, backtests, calibrators)
data/                           SQLite DBs + settings.json + dashboard state
health_check.py                 one-shot PASS/FAIL system check
resilience_check.py             proves the core loop is keyless
RESTART_CLEAN.bat               the only launcher to use
```

## Requirements

- Python 3.12 in the project venv: `.venv\Scripts\python.exe`
- `pip install -r requirements.txt` (plus `pydantic-settings`)
- Windows / PowerShell. Always run Python via the venv interpreter explicitly.
