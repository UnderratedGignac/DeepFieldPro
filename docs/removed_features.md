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

## What Remains

Only one strategy places real (paper) bets going forward:

**STEAM** (`bet_source = 'STEAM'`): fires when a 1X2 Betarabia line moves ≥5% toward a side on a match that Pinnacle also covers. Flat $25 paper stake. Deduped per fixture/market/selection.

- Backtested ROI at ≥5% move: **+20.9%** (2,386-bet held-out season)
- Live paper record: 16W / 24L, net **+$12.52** (+1.6%) on $787 staked
- Only 1X2 Home/Away (draws excluded per `exclude_draws: true`)

The AI model continues to generate predictions shown on the dashboard but places **zero-stake tracking bets only** (`ai_real_staking_enabled: false`). Its 2,386-bet out-of-sample test showed no genuine edge vs the closing line (−4.3% to −6.9% ROI at all selectivity thresholds), so it does not stake real money until a new CLV analysis proves otherwise.
