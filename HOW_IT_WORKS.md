# How DeepFieldPro Actually Works (as of 2026-07-13)

This is a from-scratch, verified-against-the-actual-code explainer, written after the
Stair AI Arena removal. It describes what the system does *today*, not what older docs
claim — several of those (`CLAUDE.md`, `TOURNAMENT_PLAYBOOK.md`) had drifted or, in one
case, contained a flatly false claim that everything here was a fake simulation. Treat
this file as the current source of truth; if it disagrees with an older doc, this one wins.

---

## 1. What this is

A football (soccer) betting **research** platform. It scrapes fixtures and odds, runs a
statistical model to estimate match probabilities, compares those probabilities to the
market price, and logs **paper bets** (fake stakes against real outcomes) so the
strategies can be judged on a real track record before anyone would ever consider
risking real money on them.

**Money status right now: none of it is real.** Every bet the system places is a row in
a SQLite database with a fake stake. There is no code path left anywhere in this app that
can spend real money — the one path that ever existed (the Stair AI Arena) was fully
removed on 2026-07-13. See `docs/removed_features.md` §4 for the full record of what was
cut and why.

---

## 2. How to run it

```powershell
# Full dashboard + background prediction daemon
.venv\Scripts\python.exe src\live_dashboard_server.py
# → http://127.0.0.1:5050

# UI only, no scraping/predicting/betting
$env:DEEPFIELD_DISABLE_DAEMON="1"
.venv\Scripts\python.exe src\live_dashboard_server.py

# Daemon only, no browser dashboard
.venv\Scripts\python.exe src\live_predictions_daemon.py
```

Or double-click `LAUNCH.bat` — it walks through environment checks, model freshness,
and starts the dashboard in paper/SHADOW mode. There is no "live" option anymore; the
menu only offers SHADOW, DAEMON-only, and the AI REPL.

---

## 3. The pipeline, end to end

```
Betarabia/Kickertech/Sofascore scrapers
        │  (fixtures + odds → data/odds_stream.db)
        ▼
live_predictions_daemon.py :: run_daemon()  (loops every ~3 min)
        │
        ├─ 1. Get today's fixtures (Sofascore via patchright, falls back to Betarabia)
        ├─ 2. Predict each fixture (Dixon-Coles model, see §4)
        ├─ 3. Check tipster confirmation (Forebet / API-Football, see §5)
        ├─ 4. Log a PAPER bet if the gates pass (log_ai_bet / tipster placement)
        ├─ 5. Write data/todays_dashboard_state.json (what the UI shows)
        └─ 6. Settle yesterday's OPEN bets against real final scores
        ▼
live_dashboard_server.py (Flask)
        │  GET /api/state   → current predictions/matches
        │  GET /api/stream  → SSE live updates
        ▼
Browser dashboard (src/templates/index.html)
```

**Empty dashboard almost always means the daemon isn't running or wrote `[]`** — the UI
never generates matches on its own.

---

## 4. The prediction model

- **Dixon-Coles** team-strength ratings (`models/dixon_coles.json`) — per-league
  attack/defense ratings + home advantage, trained on 13k+ historical matches
  (`data/history.db`, football-data.co.uk). Falls back to a simpler heuristic for
  leagues/teams it hasn't seen (e.g. some international fixtures).
- A Platt calibrator (`models/calibrator_1x2.json`) corrects favourite-overconfidence.
- O/U 2.5 and BTTS ride the same expected-goals numbers, with their own calibrator.
- `settings.market_blend_weight` (0.5) shades the model's probability toward the
  de-vigged market price before it's used for anything — this measurably reduces
  model-error bets.

**Important finding, not just marketing**: a proper walk-forward backtest
(`tools/backtest_1x2_lines.py`, ~2,386 held-out picks) showed the model has **no
real edge over the market's closing price** on 1X2 — betting the model's own picks
loses money, and the losses get *worse* the more the model disagrees with the market
(the opposite of what a real edge would look like). The model is well-calibrated and
accurate, but "accurate" isn't the same as "beats the market." This is why raw
model-only betting is currently switched off (see §6).

---

## 5. What's actually validated (and what isn't)

| Signal | Status | Evidence |
|---|---|---|
| **Forebet tipster confirmation** | ✅ Only strategy with 95% CI entirely above zero | +41.7% ROI, n=259 (walk-forward) |
| **STEAM (line movement)** | ✅ Real signal, strongest one found | +20.9% ROI at ≥5% moves (backtest ceiling; live tracking ongoing) |
| **Line-shopping (best price across books)** | ✅ Real but small | +1.9% CLV, beats close 57% of the time |
| Raw model probability (no market/tipster check) | ❌ No edge | See §4 |
| Soft-book "value" hunting | ❌ Actively bad | −6% to −12%, worse with bigger "value" |
| Prop markets (Corners, Cards, Goalscorer, O/U, BTTS, Player Shots) | ❌ Removed | See `docs/removed_features.md` §3 |

**Practical upshot**: the system is deliberately conservative. It doesn't bet its own
model's opinion just because the model is confident — it requires independent
confirmation (a tipster agreeing, or the market itself moving toward a side) before
logging a paper bet.

---

## 6. What's actually placing bets right now

Live config lives in `data/settings.json`. As of now:

- `tipster_only_mode: true` — this is the master switch. When true, it **disables**
  raw AI-model bets (`log_ai_bet`) and STEAM bets entirely, regardless of their own
  individual enable flags. Only tipster-confirmed bets go through.
- Active source: **Forebet-confirmed 1X2 picks** (`bet_source='TIPSTER_FOREBET'`) and
  **API-Football predictions** (`bet_source='APIFB'`) — a second, independent signal run
  in parallel for an A/B comparison against Forebet, gated to a small daily request
  budget (free-tier API, 100 req/day).
- Everything else is off in settings right now: `steam_betting_enabled: false`,
  `pinnacle_value_betting_enabled: false`, `ah_betting_enabled: false`,
  `crowd_betting_enabled: false`, `model_predictions_disabled: false` but moot because
  `tipster_only_mode` overrides it.
- `allowed_markets: ["1X2", "Over/Under 2.5", "BTTS"]` (Corners/Cards/Goalscorer/Player
  Shots stay permanently off — see §5).

To change any of this, edit `data/settings.json` directly or through the dashboard's
Settings tab — there's no code change needed to flip a strategy on/off.

---

## 7. Money: two separate paper ledgers

- **`data/bankroll.db`** — the general paper bankroll (all leagues, `research`/`AI`
  sources). Fractional-Kelly staking (`kelly_multiplier` × edge, capped by
  `max_exposure_pct`).
- **`data/real_bankroll.db`** — a *separate* $200 paper ledger that only tracks
  `TIPSTER_FOREBET` bets specifically, kept apart so the one validated strategy's
  real track record isn't diluted by everything else. (The name is historical —
  it does **not** mean real money; nothing here does.)
- **`data/research_bankroll.db`** — a third paper ledger used by `research_betting.py`'s
  broader sweep across all leagues, independent dedup keys from the daemon's own bets.

All three are SQLite files with fake `current_balance` columns. None connect to a bank,
card, wallet, or exchange of any kind.

---

## 8. Settlement — how a paper bet gets graded

1. **Primary**: `free_results_scraper.py` — key-less finished scores from ESPN (broad
   coverage) + TheSportsDB fallback, cached per date.
2. **Bonus**: API-Football results when its daily quota allows.
3. **Deep lookup** (last resort, for stuck/obscure fixtures): `tools/score_lookup.py` —
   Flashscore search + feed fuzzy-matching + a Google fallback. This is where the
   settlement-correctness work in this repo's history has concentrated, because fuzzy
   name matching is where things go wrong — e.g. accidentally grading a senior team's
   bet using a same-club U21/reserve side's score. `src/name_matching.py`'s
   `_level_signature()` now guards every fuzzy matcher (daemon primary pass, daemon
   sim2 fallback, and `score_lookup.py`'s feed-fuzzy + team-page matchers) against
   exactly this collision class.
4. If nothing verified can settle a bet, it's left `OPEN` and queued into a
   `settlement_review` table for manual review — the system refuses to guess.

---

## 9. Real-time signal detectors (informational / research, feed the gates above)

- **STEAM detector** (`live_predictions_daemon._steam_moves`): compares the earliest vs
  latest logged odds snapshot per selection; a big move toward a side is the strongest
  validated signal (§5). Feeds `settings.require_steam_confirm` if you turn that on, and
  writes to a separate `steam_signals` research ledger regardless.
- **Red card monitor** (`src/redcard_monitor.py`): polls ESPN every 30s during live World
  Cup matches, computes an updated Poisson win-probability after a red card
  (peer-reviewed +124% goal-rate boost for the other team). Purely informational now —
  it used to compare against a live Polymarket price to decide whether to bet; that
  comparison was removed with the Arena. It still detects and logs the event, and can
  push a notification.

---

## 10. Safety architecture

- `dfp_config.py`'s `SHADOW_MODE` (default `True`) gates `execution_engine.py`'s
  `place_bet()` — its LIVE branch is an unimplemented placeholder, so this can't spend
  money even if someone flipped the flag.
- `src/gatekeeper.py`'s `check_real_money_gate()` is a general-purpose kill switch
  (checks `DEEPFIELD_ARENA_LIVE == "1"` first, then shadow-validation criteria, then
  bankroll/exposure sanity) meant to be the single chokepoint for *any future*
  real-money integration. **Nothing currently calls it** — there's no real-money code
  left to gate. `DEEPFIELD_ARENA_LIVE` stays unset/`0` in `.env`.
- If real-money betting is ever reconsidered, it should go through this gate, require
  `min_paper_bets_for_live: 500` settled bets with positive CLV/ROI first
  (`settings.json`'s `shadow_mode_enforced` block), and above all needs the user's
  explicit, in-the-moment go-ahead — not a standing "gate is armed" instruction sitting
  in a config file.

---

## 11. Key files map

| File | Role |
|---|---|
| `src/live_dashboard_server.py` | Flask app, `/api/*`, starts the daemon thread |
| `src/live_predictions_daemon.py` | The engine — scrape → predict → gate → log → settle loop |
| `src/tipster_scraper.py` | Forebet / PredictZ / SoccerPunter / API-Football prediction fetchers |
| `src/name_matching.py` | Shared fuzzy team-name matcher + squad-level guard |
| `tools/score_lookup.py` | Deep-coverage settlement lookup for stuck bets |
| `src/redcard_monitor.py` | Live red-card win-probability alerter (informational) |
| `src/gatekeeper.py` | General real-money kill switch (currently unused) |
| `src/research_betting.py` | Broad paper-bet sweep across all leagues for research data |
| `data/settings.json` | Every strategy on/off switch and threshold — edit this to change behavior |
| `docs/removed_features.md` | Record of every strategy that was tried and cut, with why |

---

## 12. What changed on 2026-07-13

The Stair AI Arena — the only real-money path this project ever had, a real-USDC
leaderboard tournament on Polymarket — was removed in full after real losses chasing a
top rank. That includes the code, the UI tab, ~16 one-off operational scripts, 9 test
files, the tournament playbook doc, and a false "Simulation Notice" that had been added
to `CLAUDE.md` claiming (incorrectly) that nothing in this repo was ever real money. Full
details: `docs/removed_features.md` §4.
