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
