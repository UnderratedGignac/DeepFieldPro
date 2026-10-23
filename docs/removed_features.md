# Removed Features — Why They Were Cut

**Date removed:** 2026-06-19

---

## 1. SHARP Strategy (`bet_source = 'SHARP'`)

**What it was:**  
The SHARP strategy placed a paper bet whenever Pinnacle's line steamed toward a side (moved ≥5% probability from open to latest) AND Betarabia's price for that same side was still higher than Pinnacle's de-vigged fair line. The idea: bet the "lagging" soft book before it catches up to the sharp price.

**Why it failed:**  
The theory assumed Betarabia prices lag the sharp market in a systematic, tradeable way. In practice, when Betarabia showed a generous price on a big underdog, it was usually because the match was obscure or low-liquidity — not because Betarabia was slow. Those markets had no reliable closing-line benchmark, and the "steam" signal was noise from thin markets updating sporadically.

**Empirical result (settled paper bets):**  
| Metric | Value |
|--------|-------|
| Bets settled | 5 (1W / 4L) |
| Total staked | $125 |
| Net P&L | −$41.25 |
| ROI | **−41.2%** |

**Data deleted:** 5 records from `bet_log` where `bet_source = 'SHARP'`.

**Code removed:**
- `log_sharp_bet()` function in `live_predictions_daemon.py`
- SHARP detection block in the prediction loop (lines 3859–3932, pre-removal)
- `sharp_edge.start_sharp_snapshots()` background thread call in `run_daemon()`
- CLV-vs-SHARP computation in `settle_open_bets()`
- `src/sharp_edge.py` (entire module, 332 lines)
- `src/sharp_scraper.py` (entire module, 164 lines)

---

## 2. SHARPV Strategy (`bet_source = 'SHARPV'`)

**What it was:**  
SHARPV was a "pure value" variant of the SHARP strategy. Instead of requiring a line move, it fired whenever Betarabia's price implied a higher probability of winning than Pinnacle's de-vigged fair line (EV between +2% and +10%). The idea: systematically take Betarabia whenever the spread to the sharp line is in a narrow "value" window — not too small to be juice, not so large it's a mispriced favourite.

**Why it failed:**  
The capped EV window (2–10%) meant SHARPV concentrated on heavy underdogs — matches where Betarabia offered 5.7× odds when Pinnacle implied ~4.5×. These underdogs lost at the rate you'd expect. Betarabia's 5.7× on a true 22% chance is not value when the implied probability is 22% in the first place. The strategy was chasing soft-book prices on weak selections and confusing "better odds than Pinnacle" with "positive expected value from the true probability."

**Empirical result (settled paper bets):**  
| Metric | Value |
|--------|-------|
| Bets settled | 13 (2W / 11L) |
| Total staked | $325 |
| Net P&L | −$190.00 |
| ROI | **−54.3%** |
| Average odds | 5.71 |
| Hit rate | 15.4% (needed ~17.5% to break even) |

**Data deleted:** 19 records from `bet_log` where `bet_source = 'SHARPV'` (13 settled + 6 open/void).

**Code removed:** Same block as SHARP above — both strategies shared `log_sharp_bet()` and the same module files.

---

## 3. Prop Markets — Corners, Cards, Goalscorer, Player Shots, O/U, BTTS

**What they were:**  
The AI model generated predictions and placed paper bets across every market Betarabia offered:
- **Corners** — total corners over/under thresholds
- **Total Cards** — total yellow/red cards over/under
- **Goalscorer** — which player scores (anytime/first)
- **Player Shots** — shots on target for specific players
- **Over/Under 2.5** — total goals line
- **BTTS** (Both Teams To Score)

**Why they all failed:**  
These markets share the same root problem: the AI model was trained on match-level outcome data (1X2 results, score aggregates) and has no player-level or event-level signal. Predicting which player scores, how many corners there will be, or whether a midfielder takes ≥2 shots requires lineup data, player form, and in-game positional tracking — none of which the system has. The model assigned probabilities to these markets by fitting coefficients to historical frequencies with no genuine predictive signal, producing bets that were systematically priced below fair value.

Settlement was also unreliable: most prop bets fell back to `hash(bet_id) % 2` when stats were unavailable, generating artificial wins and losses that polluted the historical record.

**Empirical result (settled paper bets):**  
| Market | Bets | Staked | P&L | ROI |
|--------|------|--------|-----|-----|
| Corners | 33 | $36.7 | −$13.32 | −36.3% |
| Total Cards | 37 | $38.2 | −$15.97 | −41.8% |
| Goalscorer | 88 | $88.0 | −$70.30 | −79.9% |
| Player Shots | 168 | $167.9 | −$104.86 | −62.5% |
| Over/Under 2.5 | 89 | $322.5 | −$195.81 | −60.7% |
| BTTS | 14 | $76.6 | −$21.74 | −28.4% |
| **Total** | **429** | **$729.9** | **−$422.00** | **−57.8%** |

**Data deleted:** 431 records from `bet_log` where `market_type IN ('Corners', 'Total Cards', 'Goalscorer', 'Player Shots', 'Over/Under 2.5', 'Over/Under 3.0', 'Over/Under 2.0', 'BTTS', 'Double Chance', 'Draw No Bet', 'Asian Handicap')`.

**Code changed:**  
- `allowed_markets` in `settings.json` set to `["1X2"]` only — the daemon's `is_recommended` and STEAM gates both check this list before placing any bet. No code paths for prop markets remain active.

---

## 4. Stair AI Arena (`src/arena_betting.py` and its real-money order path)

**Date removed:** 2026-07-13

**What it was:**
The only real-money path this project ever had. `arena_betting.py` (~3,600 lines) compared
the project's 1X2 model probability to the live Polymarket midpoint on Stair AI's World Cup
2026 Arena — a real-USDC leaderboard tournament — and placed real orders when the edge
cleared a threshold. It had its own Flask blueprint (`/arena`), a "World Cup Arena" dashboard
tab, an autopilot loop, AP2 mandate/ledger auditing, attribution/CLV/execution-analytics
reporting, a red-card in-play alerter, a lineup-price-lag detector, and roughly a dozen
one-off operational scripts (`FIRE_SEMIS.ps1`, `arg_fill_hunter.py`, `mar_leg_watcher.py`,
`resume_after_payout.py`, ...) written during the tournament to chase specific fills. A
second, independent real-order path also existed directly in `live_predictions_daemon.py`
(gated by `DEEPFIELD_DAEMON_LIVE_ORDERS`), never actually armed.

**Why it was removed:**
The user lost most of the real money in the account chasing a #1 leaderboard rank and asked
to discard the feature entirely, not just disable it. The line/CLV research
(`tools/backtest_1x2_lines.py`, see the 1X2 line/CLV analysis notes) had already shown the
core model has no real 1X2 edge over the market — the Arena was operating on an unvalidated
signal even before the tournament-chasing behavior compounded the losses.

**Code removed:**
- `src/arena_betting.py`, `src/templates/arena.html` — the blueprint, UI tab, and order path
- `src/ap2_ledger.py`, `src/ap2_mandate.py`, `src/attribution_engine.py`,
  `src/execution_analytics.py`, `src/clv_analysis.py`, `src/adaptive_kelly.py`,
  `src/stairai_reasoning_engine.py`, `src/agents/arena_monitor.py`, `src/reporting.py`,
  `src/polymarket_steam.py` — Arena-exclusive support modules
- The daemon's independent `DEEPFIELD_DAEMON_LIVE_ORDERS` order path, `init_stair_ai_agent()`,
  `_stair_api_key()`, and the `stairai_reasoning_engine.run_cycle()` call in
  `live_predictions_daemon.py` (real-money bookkeeping simplified to always-SHADOW)
- The Arena-only WC real-order sweep in `research_betting.py` (`_sweep_wc()`); its O/U/BTTS
  paper sweep, which didn't depend on Arena, was kept
- Polymarket-dependent market comparison in `redcard_monitor.py` (kept red-card detection +
  win-probability math, dropped the now-impossible market-edge check) and all of
  `lineup_price_lag.py` (100% Polymarket-dependent, no independent value)
- ~16 `tools/*.py` scripts and 9 `tests/test_*.py` files exclusively about the Arena
- `LAUNCH.bat`'s `[L] LIVE` menu and `[I] INSIGHTS` menu (Polymarket market scan), and the
  real-money-order scripts `FIRE_SEMIS.ps1`, `logs/_server_live.bat`
- `STAIR_AI_API_KEY` from `dfp_config.py`, `.env`, `.env.example`
- `TOURNAMENT_PLAYBOOK.md`, `MATCH_OF_THE_DAY_ARG_EGY.md`,
  `docs/ARENA_RISK_ANALYSIS_2026-07-09.md`, `docs/RISK_MANAGEMENT_UPGRADE_2026-07-09.md`

**Data deleted:** `data/arena_ledger.db`, `data/arena_autopilot.json`,
`data/knockout_mapping.json`, `data/polymarket_steam.db` (permanent, per explicit user
request — these were untracked/local except `arena_autopilot.json`).

**What's still in place:** `src/gatekeeper.py`'s `check_real_money_gate()` — a general
real-money kill switch (`DEEPFIELD_ARENA_LIVE` must be `"1"`) that any *future* real-money
path would have to pass through. It's currently unused (nothing calls it), and
`DEEPFIELD_ARENA_LIVE` stays unset/`0`. There is no real-money execution path left in this
app.

---

## 5. SKILL_* Strategies (`src/skill_strategies.py`)

**Date removed:** 2026-10-23

**What it was:**
A standalone loop (`scripts/run_skill_strategies.cmd`) that read `/api/state` and placed
paper bets under ten `SKILL_*` sources (De-vig Edge, Half-Kelly Value, Soft-Book
Overround, Consensus Confirm, Low-Vig Steal, Parlay Value, ...), using formulas adapted
from an external `betting` agent skill. It ran for one day (2026-10-22).

**Why it was removed:**
It lost heavily and broke settlement for everything else. Its 128 graded singles went
18W-110L (−$1,263 on $1,748 staked, −72%) and its 33 parlays all lost (−$230). The
model probabilities it bet on were mostly a few repeated fallback values (fair price 2.74
on 47 bets, 2.79 on 25, 1.59 on 17), not real per-match predictions. Its parlays had
legs with no `market`/`selection`, which crashed `settle_open_bets()` every cycle and
re-credited the research ledger with phantom payouts (see the CLAUDE.md "Settlement crash
loop" section). The user asked to remove it and keep the original strategies.

**Code removed:** `src/skill_strategies.py`, `scripts/run_skill_strategies.cmd`, and the
`SKILL_*` labels in `src/strategies_blueprint.py` (all uncommitted at the time).

**Data removed:** 184 `bet_log` rows (`bet_source LIKE 'SKILL_%'`), 33 `parlay_log` rows
(`parlay_id LIKE 'SPV_%'`) and 89 `settlement_review` rows, archived losslessly first to
`data/skill_strategies_archive_2026-10-22.db`.

**What's still in place:** the settlement crash guard added while diagnosing it
(single-bet grades are committed before the parlay loop; a malformed parlay is skipped,
not fatal). The research ledger's phantom credit was not repaired.

---

## What Remains

Only one strategy places real (paper) bets going forward:

**STEAM** (`bet_source = 'STEAM'`): fires when a 1X2 Betarabia line moves ≥5% toward a side on a match that Pinnacle also covers. Flat $25 paper stake. Deduped per fixture/market/selection.

- Backtested ROI at ≥5% move: **+20.9%** (2,386-bet held-out season)
- Live paper record: 16W / 24L, net **+$12.52** (+1.6%) on $787 staked
- Only 1X2 Home/Away (draws excluded per `exclude_draws: true`)

The AI model continues to generate predictions shown on the dashboard but places **zero-stake tracking bets only** (`ai_real_staking_enabled: false`). Its 2,386-bet out-of-sample test showed no genuine edge vs the closing line (−4.3% to −6.9% ROI at all selectivity thresholds), so it does not stake real money until a new CLV analysis proves otherwise.
