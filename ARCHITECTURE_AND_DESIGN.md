# DeepFieldPro — Architecture & Design

This document explains **how the system works** and, more importantly, **why it is built
the way it is**. Many of the design choices are reactions to hard lessons (mirages, stale
data, zombie sockets, fabricated settlements). Each section pairs the *mechanism* with the
*rationale* so future changes don't accidentally re-introduce a problem that was already
solved.

> Companion docs: `README.md` (how to run) and `CLAUDE.md` (working notes / gotchas).

---

## 1. The big picture

DeepFieldPro is a single long-running process that does five things in a loop:

```
        ┌─────────────────────────────────────────────────────────────┐
        │  src/live_dashboard_server.py  (Flask, one process)         │
        │                                                             │
        │   ┌─ web routes ──────────────► browser dashboard           │
        │   │                                                         │
        │   └─ daemon thread (run_daemon, ~30s loop):                 │
        │        1. scrape Betarabia odds  → odds_stream.db           │
        │        2. fetch fixtures         (keyless, with fallback)   │
        │        3. predict (Dixon-Coles)  → probabilities            │
        │        4. write dashboard state  → todays_dashboard_state.json│
        │        5. place PAPER bets       (AI / STEAM / SHARP)       │
        │        6. settle finished bets   (real scores only)         │
        │                                                             │
        │   + helper threads: closing-line capture, sharp snapshots,  │
        │                     Arena autopilot (real money, gated)     │
        └─────────────────────────────────────────────────────────────┘
```

**Why one process instead of microservices?** Earlier the repo had several launchers
(`START_ALL.bat`, `RUN_SYSTEM.bat`) that each spawned servers in persistent `cmd /k`
windows. The result was *dueling orphan processes* fighting over the port and overwriting
each other's state files. Collapsing to one gated instance launched by **`RESTART_CLEAN.bat`**
removed an entire class of bugs. Simplicity is a safety feature here.

---

## 2. Data flow, stage by stage

### 2.1 Odds (Betarabia) — keyless
`src/betarabia_scraper.py` is a Playwright/Kickertech scraper that writes fixtures and
markets into `data/odds_stream.db` (`fixture`, `market` tables). The daemon launches it
each cycle, **but only if the previous run finished** (anti-stacking guard).

**Design lesson — the staleness bug (the highest-value fix ever made here):** the scraper
originally called `clear_todays_data()` at the *start* of a run, then scraped for ~3
minutes, writing only at the end. Any scrape that didn't finish (stacked, crashed, killed
by a restart) left today's odds **wiped with no replacement** — hours-to-days-stale prices
that silently corrupted every paper bet. Two fixes:
- Move the clear to **after** a successful scrape, right before the write loop (writes are
  `INSERT OR REPLACE` upserts, so clearing-first was both needless and destructive).
- An **anti-stacking guard** in the daemon (`_scraper_proc.poll()`): never launch a new
  scrape while one is running (stacked 3-min scrapes were OOM-ing Chromium so none finished).

Plus freshness defense: `find_betarabia_odds` exposes the matched fixture's odds age, and
the bet gate refuses any bet on odds older than `max_odds_staleness_min` (default 60 min).

### 2.2 Fixtures — keyless with fallback
The daemon calls `get_todays_fixtures_free()` (Sofascore public API). **Sofascore is
frequently bot-blocked and returns empty**, so on empty it falls back to building fixtures
from `odds_stream.db` (the Betarabia data we already have). Either way: **no API key**.

### 2.3 Predictions — local models, no network
`predict_match` uses a **Dixon-Coles** model (`models/dixon_coles.json`): continuous
per-league team attack/defense ratings + home advantage + a low-score correlation term
(`rho`). It produces expected goals for each side, from which 1X2 / Over-Under / BTTS
probabilities follow. Unknown teams/leagues (e.g. World Cup internationals) fall back to a
heuristic. A Platt calibrator (`models/calibrator_1x2.json`) corrects favourite
over-confidence.

**Why Dixon-Coles over the old approach?** The previous core hardcoded expected goals by a
crude 3-way bucket. Dixon-Coles is the standard, validated football model and backtests
better (log-loss 1.001 vs the old 1.059, approaching the market's 0.968). It is *more
accurate* — but see §4: accuracy is **not** the same as a betting edge.

### 2.4 Settlement — real scores only, keyless primary
`settle_open_bets()` grades open bets using finished-match scores from
`src/free_results_scraper.py` (**ESPN site API + TheSportsDB**, both keyless) as the
**primary** feed. API-Football is merged in as a *bonus* when its free quota allows, wrapped
in try/except so it can never break settlement.

**Design lesson — never fabricate an outcome.** Settlement used to fall back to
`hash(bet_id)` to invent prop results (corners, cards, goalscorer, player shots, parlay
legs) when real data was missing. That manufactured fake wins/losses — the literal source
of the "+$988 1X2 profit" mirage (longshots "winning" 34% at 16% implied odds). **All
fabrication was removed**: if real data is missing, the bet stays **OPEN** until it arrives.
A bet is only ever graded W/L from a real score.

**Design lesson — settlement ambiguity guard.** Fuzzy name-matching once settled a bet
against the *wrong* finished game. Now, if two different finished matches both name-match a
bet and disagree on the score, settlement **refuses** to grade it rather than risk a wrong
result.

### 2.5 Dashboard — local file
The daemon writes `data/todays_dashboard_state.json`; the UI reads it via `GET /api/state`
(a fast local file read) and streams updates via SSE. **An empty dashboard means the daemon
isn't running or the state file is `[]`** — the UI alone never populates matches.

---

## 3. The betting strategies

All are **paper** except Arena. They are tagged by `bet_source` in `bet_log` so each can be
measured independently.

### 3.1 AI (model)
The Dixon-Coles probability vs the de-vigged market price; bets when EV and confidence
clear thresholds; staked with **fractional Kelly** (`kelly_multiplier` 0.2). A
**conviction cap** (`edge_cap_pct`) *rejects* bets where the model disagrees with the market
by too much — because the backtests showed the model's biggest disagreements are where it's
most *wrong* (see §4).

### 3.2 STEAM (line movement) — the most promising signal
The daemon logs every scraped price into `odds_history`. `_steam_moves()` de-vigs the
earliest vs latest snapshot per selection to measure how far the line moved toward a side.
When the move ≥ `steam_min_move_pct` (default 5%), `log_steam_bet()` places a flat-stake
($25) paper bet. **Flat, not Kelly** — the edge is the *movement*, not a model probability.

**Why steam?** It's the **only** signal the project's own backtests validated as positive:
ROI rises monotonically with move size, reaching +20.9% at ≥5% moves (the opposite of the
model, where more conviction = worse). The backtested number is a diagnostic ceiling; the
live ledger must accumulate a few hundred settled bets before the production ROI is trusted.

### 3.3 SHARP / SHARPV (Pinnacle vs Betarabia)
`src/sharp_scraper.py` pulls Pinnacle 1X2 via its **public guest API** (a shared guest
token — *not* a personal account, so still "keyless" in the sense that matters). `src/sharp_edge.py`
snapshots those prices and computes two edges:
- **SHARP steam** — Pinnacle's de-vigged probability moving toward a side.
- **SHARPV lagging value** — Betarabia's price is still better than Pinnacle's fair price.

A Betarabia bet fires only when the signal holds. Cross-book matching is **deliberately
strict** (per-team `SequenceMatcher ≥ 0.82`, ambiguity margin, kickoff within 15 min)
because a loose 0.60 threshold once falsely matched *Iraq/Venezuela → Iran/New Zealand*. A
`TRAP_EV_CAP` (0.20) blocks implausible "+50% EV" bets that are really just stale/garbled
prices, not value.

### 3.4 Arena (the real-money path)
`src/arena_betting.py` compares the model's 1X2 probability to the live Polymarket midpoint
for World Cup fixtures and bets only when `model_prob ≥ conf` AND `model_prob − mid ≥ edge`.
This is the **only** path that can move real money, and it's wrapped in the safety locks in
§5.

---

## 4. Why "the model has no edge" — and what that means

This is the most important thing to understand about the system.

- A historical paper record once showed **1X2 at +151% ROI**. That was a **mirage**: 53
  bets, hash-settled noise, **zero CLV**.
- A proper out-of-sample test (`tools/backtest_1x2_lines.py`, ~2,386 picks, walk-forward,
  real closing prices) measured CLV at three prices. Verdict: betting the model's picks is
  **−4% to −7% ROI**, and crucially a **selectivity sweep makes it worse** (−3.4% at a 2%
  edge bar → −19.7% at 20%). A real edge *improves* with selectivity; this *degrades* —
  proof the model's biggest disagreements with the market are where it's most wrong.
- The **only** positive 1X2 signals found: **line-shopping** (+1.9% CLV, real but too small
  alone) and **STEAM** (line movement, the strongest lead).
- Over/Under 2.5 was validated too — and **loses into the close** (−2 to −3% ROI). It is
  kept **off** the betting whitelist; its calibration is display-only.

**Consequences baked into the system:**
- `allowed_markets: ["1X2"]` and `exclude_draws: true` — only the one market that isn't a
  guaranteed loser, minus the draw leg that bled money.
- All prop markets are **off** (Goalscorer, Player Shots, O/U, BTTS, Cards, Corners — every
  one was net-negative; together they lost ~$431 historically).
- **Parlays are disabled.** They *multiply* per-leg edge; with no proven +EV single bet, a
  parlay is structurally *more* −EV than its legs (live record: 22% hit, ~−31% ROI). The
  generator is commented out in the daemon; settlement is left intact to grade out any open
  parlays. Do **not** re-enable until a single bet proves +CLV.

**The strategy, therefore, is CLV-first measurement, not betting.** Let the paper daemon
accumulate clean Closing-Line-Value data; trust a strategy only once `tools/edge_status.py`
shows it beats the close over ≥100 settled bets with CLV > 0 at 95% confidence. Real money
stays narrow and gated until then.

---

## 5. Real-money safety (defense in depth)

Real money can only move through `arena_betting.place_order()`, behind **two independent
locks that must both be set**:

1. **`DEEPFIELD_ARENA_LIVE=1`** in the launching shell — *session-scoped on purpose*. A
   crashed or zombie process cannot silently re-arm it, and multiple orphaned daemons had
   previously been re-enabling the state file. The env gate makes a real bet impossible
   regardless of any flag/zombie/frontend state.
2. **`data/arena_autopilot.json` → `enabled: true`** — the state lock.

Further constraints: $5/order cap, wallet buffer, `MAX_BETS_PER_RUN`, `confirm: true`
required on the place endpoint, World-Cup-only, pre-kickoff re-check. The **paper** daemon's
own order-POST is separately hard-gated off (`DEEPFIELD_DAEMON_LIVE_ORDERS`, never set it),
because the paper daemon bets across markets that are heavily −EV.

**Why session-scoped rather than a config flag?** Because the failure mode that actually
happened was a config flag getting re-enabled by a stray process. An environment variable
that dies with its shell is immune to that.

---

## 6. Keyless by design

The **only** key the system *depends* on is `STAIR_AI_API_KEY`, and only for placing real
money (paper mode needs no key at all). Every other stage runs keyless:

| Stage | Source | Key? |
|---|---|---|
| Fixtures | Sofascore public → Betarabia fallback | none |
| Odds | Betarabia (Playwright) | none |
| Sharp odds | Pinnacle public **guest** token | none (shared token) |
| Results / settlement | ESPN + TheSportsDB | none |
| Predictions | local models | none |
| Dashboard | local JSON | none |
| Real money | StairAI | **yes (intentional)** |

API-Football (free tier) and WhatsApp (alerts) are **bonus extras**, fully guarded: missing
keys return empty/skip, never raise. The WhatsApp "massive edge" alert in `log_ai_bet` is
isolated in try/except so an alert failure can't skip the bet placement below it.

**Prove it anytime:** `resilience_check.py` blanks *every* non-StairAI key and confirms all
seven core stages still deliver. Exit 0 = fully keyless-resilient.

**Why this matters:** free API keys get revoked, rate-limited, or quota-exhausted without
warning. A research system that silently stops working when a free key dies is worse than
useless — it gives you stale data while looking healthy. Keylessness is reliability.

---

## 7. Operational gotchas (and why the tooling exists)

### 7.1 The zombie socket
After many restarts, a port (e.g. 5050) can be left in `LISTEN` state owned by a **dead
PID** — a zombie socket that accepts TCP but serves nothing, so the dashboard "hangs" (HTTP
times out) even though the server code is fine. It's unkillable without a reboot. This once
caused a long false-alarm debug (GIL/perf theories were all wrong; the code was fine).

**Fix, baked into tooling:** `RESTART_CLEAN.bat` auto-scans `[5050, 5058–5063]` for a free
port and records the choice in `current_port.txt`. `health_check.py` reads that file, so the
checker and the server always agree on the live port. If 5050 looks dead, the system just
moves to 5058 — no reboot needed.

### 7.2 The venv redirector
The venv's `python.exe` is a *redirector*: every launch spawns a base-Python child, so one
server legitimately shows as **two** `python.exe` processes (a stub parent + its child).
This is harmless — only the child binds the port. Don't mistake it for an orphan.

### 7.3 Database growth
`odds_history`, `sharp_odds_history`, and old Betarabia fixtures are purged beyond 3 days to
bound DB growth. Paper `bankroll.db` `current_balance` is *liquid* cash — when it hits $0
(all staked in open bets) the daemon silently places nothing; `tools/reset_paper_bankroll.py`
restores it (paper only).

---

## 8. Tooling map

**Health / resilience (top-level):**
- `health_check.py` — one-shot PASS/FAIL: dashboard up, odds fresh, sharp live, bankroll,
  no crashes. Port-aware. Exit 0/1.
- `resilience_check.py` — proves the core loop is keyless (blanks all non-StairAI keys).

**Decision / analytics (`tools/`, read-only unless noted):**
- `edge_status.py` — the verdict: GO / LEAN / WAIT / NO-GO per strategy (AI/STEAM/SHARP/
  SHARPV), needs ≥100 settled bets with CLV > 0 at 95% CI. Excludes pre-2026-06-15 noise.
- `clv_report.py`, `steam_report.py`, `league_report.py`, `settlement_audit.py` — drill-downs.
- `backtest_1x2_lines.py`, `backtest_1x2_model.py`, `backtest_market_signals.py`,
  `backtest_ou_model.py` — the out-of-sample tests that produced §4's conclusions.
- `train_dixon_coles.py`, `train_1x2_calibrator.py`, `train_ou_calibrator.py` — model fitting.
- `ingest_history.py` — builds `data/history.db` (13k matches + closing odds) for backtests.
- `reset_paper_bankroll.py` — restores paper bankroll (paper only).

---

## 9. Design principles (the short version)

1. **CLV-first.** Prove an edge before scaling it. Accuracy ≠ profit.
2. **Settlement never lies.** Real scores only; missing data → bet stays OPEN.
3. **Keyless core, one keyed exception.** Reliability over convenience.
4. **Two-lock real money, session-scoped.** No single failure (or zombie) can place a bet.
5. **One process, one launcher.** Simplicity eliminates whole bug classes.
6. **Narrow the surface.** Only 1X2; no draws, no props, no parlays — until measured otherwise.
7. **Make it provable.** `health_check.py` and `resilience_check.py` turn claims into exit codes.
