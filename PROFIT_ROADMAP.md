# DeepFieldPro — Autonomous Profit Build (overnight session)

Goal (user mandate): maximize profitability using FREE data; build every edge that's
genuinely +EV; orchestrate subagents for research + build; keep going autonomously.

## Guardrails (protect the money — non-negotiable)
- **Real edge over volume.** The model has no proven 1X2 edge; props are −EV. Build the
  VALIDATED edges (steam, CLV, line-shopping) + genuinely-predictive new signals (xG).
  Never crank out −EV bet types to "do more."
- **Real money stays gated.** The $74 Arena keeps its conservative thresholds + the
  DEEPFIELD_ARENA_LIVE env gate. No loosening to force −EV bets.
- **Backtest before trust.** Every new signal is validated against the closing line
  (CLV) on held-out data before it's allowed to influence bets.
- **Leave it healthy.** Every change ends with a clean restart + green health_check.

## Validated truths (from the project's own backtests — the foundation)
- STEAM (line movement ≥5%): +20.9% ROI backtest — the strongest real signal.
- Line-shopping (best price): +1.9% CLV — real but small alone.
- 1X2 model: no edge (selectivity sweep degrades). Props: −59% to −80%.
- Edge is in SOFT/EARLY books, never beating Pinnacle's close.

## Workstreams (this session)
- [x] Live in-play match display (Flashscore, keyless)
- [x] Corners/Cards real settlement (Flashscore stats)
- [ ] **xG signal** — Flashscore stats has real xG; build collector + xG-based model + backtest
- [ ] **More free sharp/odds books** — strengthen steam + best-price CLV
- [ ] **Steam strategy hardening + auto-report** (the validated edge — make it the core)
- [ ] **CLV surfaced on dashboard** (the honest scoreboard)
- [ ] **Research orchestrator** — subagents research free-data edges → prioritized specs
- [ ] Backtest framework for any new signal

## Log — overnight session (2026-06-15 → 06-16)
DONE & committed + pushed (each verified, system left healthy):
1. **Live in-play matches** on the dashboard (Flashscore, keyless display-only).
2. **Corners/Cards real settlement** (Flashscore stats feed — real corner/card/xG, no fabrication).
3. **CLV mirage fixed** — CLV now grades vs the last PRE-KICKOFF snapshot (+ |CLV|<=40% guard);
   STEAM's fake +62% → honest +1.2%. Also capture real xG per match.
4. **Stopped the bankroll bleed** — AI/1X2 model shadow-staked at $0 (no proven edge, was ~95%
   of bets); real stop-loss enabled (30% drawdown / 10% daily / 50% volume, were all OFF);
   STEAM stake now bankroll-proportional (2%, floor $1 cap 3%).
5. **Pinnacle-graded CLV (clv_sharp)** — the trustworthy scoreboard; edge_status.py gates on it
   (vs the sharp close), Betarabia self-CLV demoted to diagnostic.
6. **2nd free soft book (Kambi/Unibet)** + line_shop.py (best price, strict match + ratio guard);
   STEAM records best_odds/best_book as metadata → tools/line_shop_report.py measures the uplift.
7. **Pinnacle softness report** (tools/softness_report.py) — rank fixtures by maxRiskStake (low =
   soft = most cross-book edge) to concentrate capital.

NET EFFECT: stopped the -EV AI bleed, made the CLV scoreboard honest + sharp-graded, added the
infrastructure to capture the validated line-shopping edge, and added risk circuit-breakers.
The system now LOSES less and MEASURES the real edges truthfully — the foundation for profit.

NOT done (deliberately — uncertain/large, flagged for daylight):
- #2 PS3838 mirror (defensive vs Pinnacle key revocation).
- #7 xG regression-to-mean backtest (needs understat ingest; must clear a selectivity sweep
  or be discarded — likely -EV like other model signals).
TRAPS confirmed to AVOID (from research): player props, real Pinnacle↔Betarabia "arb",
full Kelly, keyed aggregator APIs, raw understat via requests, DNB/double-chance recombinations.

### Overnight pass 1 (06-16 ~02:55) — autonomous, guardrailed
- Health GREEN. No new actionable signal yet: STEAM 8 settled (-9.4% ROI, tiny sample),
  0 sharp-CLV / 0 line-shop data (steam fired only on obscure non-Pinnacle/non-Kambi leagues
  + low overnight volume). No bug — recording code verified correct, just no qualifying bets.
- **#7 xG groundwork DONE + verified:** confirmed free historical xG IS accessible via the
  `soccerdata` package (Understat, tls-client; raw requests is Cloudflare-stripped). Built
  `tools/ingest_xg_understat.py` (standalone data/xg_history.db, hard null-guard) — verified
  380 EPL matches with real xG ingested. Does NOT touch the live system.
- **NEXT (daylight):** `tools/backtest_xg_regression.py` — join xg_history with history.db
  closing odds (match by date+teams), compute each team's trailing (goals-xG) over prior
  matches (walk-forward, prior-only), back the under-performer at best soft early price.
  GATE: deploy ONLY if the selectivity sweep is monotone-positive; else discard (likely -EV
  like goals-DC). Ingest more leagues/seasons first (`python tools/ingest_xg_understat.py`).

### Overnight pass 2 (06-16 ~04:45) — autonomous, guardrailed
- Health GREEN. xG ingest extended + verified: La Liga added → 760 rows (EPL+La Liga) in
  data/xg_history.db. Multi-league path works.
- **KEY FINDING (needs daylight backtest before acting):** all 20 clean-era STEAM bets have
  0 sharp-CLV AND 0 line-shop data — steam is firing ONLY on obscure leagues with NO
  Pinnacle/Kambi coverage, where it's losing (~-$31) and is UNMEASURABLE (no sharp close to
  beat). The +20.9% steam backtest was on LIQUID major leagues; thin-market line moves on
  obscure Betarabia fixtures are likely NOISE (stale/garbled-odds artifacts), not informed
  money. HYPOTHESIS: restrict steam to Pinnacle-covered (liquid) matches only — this aligns
  the live strategy with the backtest's domain AND makes every steam bet measurable via
  clv_sharp. DO NOT change the live gate on a 20-bet sample; first backtest steam-on-covered
  vs steam-on-obscure. Candidate: add a default-OFF `steam_covered_only` setting + a gate
  check `sharp_edge._match_key(home,away,ko) is not None` so the user can enable after review.

### Overnight pass 3 (06-16 ~06:45) — autonomous, guardrailed
- Health GREEN. Built + ran tools/backtest_xg_regression.py (signal-validity gate, read-only
  on xg_history, no odds, no live change).
- **RESULT: xG-regression is a DEAD END for betting — DISCARD #7.** n=1320 team-matches:
  UNLUCKY next-PPG = 1.407, LUCKY next-PPG = 1.407 (diff +0.000). xG over/under-performance
  mean-reverts slightly in xG terms (lucky next-luck -0.140 vs unlucky -0.088) but produces
  ZERO difference in next-match POINTS — the market already prices fundamentals. Confirms the
  project's core truth: edge is in line-movement / soft pricing, not better models. Did NOT
  build the odds-join backtest (saved the larger effort). Focus stays on steam-coverage
  (pass 2) + line-shopping + CLV measurement — the only paths with a real basis.
