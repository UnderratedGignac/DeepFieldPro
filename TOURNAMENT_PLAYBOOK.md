# WC2026 Stair AI Arena — Tournament Playbook
### Handoff document for the next session. Read this fully before touching anything.

**Context**: The Stair AI Arena is a VIRTUAL-$100 tournament (verified — AI agents
paper-trade Polymarket WC markets for leaderboard rank; no real money). The user's
goal: finish #1. We are competing aggressively by explicit user mandate.

**Account as of 2026-07-07 ~17:00 UTC**: **$162.56 total**
($113.18 cash · $45 on Colombia (SUI-COL, 20:00 tonight, pays $104.60) ·
$5 FRA-MAR draw (July 9, pays $20)). Leaders were ~$160 on July 5.
Started from $24 total value on July 5. QF record: England W, Spain W,
Belgium W, 2 draw-hedges L, Argentina deliberately skipped (see Lesson #1).

---

## 1. THE STRATEGY (validated by 800+ tracked research bets — see /research)

Bet ONLY when ALL of these hold:

1. **Signal**: Forebet.com's published pick agrees with the outcome
   (the ONLY strategy in our research ledger whose 95% CI is entirely above
   zero: +41.7% ROI, n=259). NEVER reveal Forebet as the source publicly —
   competitors read the threads. Say "our signal stack."
2. **Price**: entry price ≤ model_fair_probability − 5pp. NEVER buy above fair
   value no matter how much the model loves the team (Lesson #1: Argentina).
3. **Liquidity is REAL**: verify the actual order book, not the midpoint —
   `https://clob.polymarket.com/book?token_id=<id>` (token ids from
   `get_mapping(fid)` in src/arena_betting.py). A 5¢-bid/95¢-ask placeholder
   book shows a fake ~8¢ "midpoint". If asks are junk → the FOK will reject →
   fine, retry later. Books get real close to kickoff.
4. **Window**: fixture kicks off within 24h (capital-velocity rule — money
   locked days early can't compound). Trading closes AT kickoff
   (`fixture_not_open`) — never plan on in-play bets.

**Exceptions to the Forebet filter:**
- TRUE ARBITRAGE (sum of all outcome asks < $1.00): bet immediately, max size.
  The autopilot detects this automatically (real_arb priority 1000).
- FOREBET DRAW PICKS: the autopilot structurally cannot bet draws (models never
  rate draws ≥ conf_min), so place them MANUALLY via order_fok when Forebet
  calls a draw and the price is ≤30¢: $10-15 stake. Went 0-for-2 on July 6 but
  the prices were right (+EV); keep doing it, keep stakes moderate.

**Sizing**: autopilot floors confirmed picks at 40% of wallet, full Kelly above
that, $100/bet cap. Manual bets: match this spirit; on coin-flip-ish confirmed
picks ~25-50% of wallet is right. Never leave the whole bankroll idle, never
put >70% on one match.

## 2. RANK-RACE GAME THEORY

- **Behind** → concentrate + seek variance (higher-multiple value like draws;
  fewer, bigger bets).
- **At/near the lead (current state)** → keep betting +EV but SPREAD it;
  don't bust chasing a lead you already hold. As the final approaches with a
  lead, shrink stakes toward what protects rank (the chasers must gamble —
  let them bust).
- Leaderboard rank: `state["leaderboard_rank"]` via /arena/api/status (often
  null; the obside.com arena page shows the public race).

## 3. SCHEDULE + PLAYS REMAINING

| Date | Match | Action |
|------|-------|--------|
| Jul 7 20:00 | SUI-COL (QF) | $45 riding COL. No action — settle & collect. |
| Jul 9 20:00 | FRA-MAR (QF) | Hold $5 draw. `tools/mar_leg_watcher.py` hunts FRA $10 at ≤0.45 (MAR leg cancelled, -EV). When Forebet publishes its pick (Jul 8-9), if it confirms France the AUTOPILOT adds at full size in-window. |
| Jul 10-11 | Semifinals (Norway-England Jul 11 + winner-side semi) | THE BIG DEPLOYMENT: ~$100+ per Forebet-confirmed pick, in-window, price-verified. Egypt led ARG 0-1 at last check — if Egypt advanced, bracket chaos = mispriced favorites = our edge. |
| ~Jul 14-15 | 3rd-place match | Small value bet only if confirmed + priced right. |
| ~Jul 19 | FINAL | Deploy per rank position: big if behind, protective if leading. |

**Every match day**: (1) Forebet picks refresh ~daily — the autopilot fetches
today+tomorrow automatically; (2) verify fills — an accepted FOK with status
`unfilled` usually dies; only `completed` is a fill (check /arena/api/orders);
(3) payouts credit HOURS after matches — don't panic about "missing" money.

## 4. INFRASTRUCTURE MAP

- **Server**: `.venv\Scripts\python.exe src\live_dashboard_server.py` with env
  `DEEPFIELD_PORT=5050`, `DEEPFIELD_ARENA_LIVE=1`. After reboot: LAUNCH_ALL.BAT
  (arms the arena; research daemon rides along).
- **Autopilot**: thread inside the server. Scans ~1-3min. Forebet-only filter +
  24h window + 40% floor live in `autopilot_cycle()` (src/arena_betting.py).
- **Watchers** (detached python, relaunch after reboot if their matches pend):
  `tools/mar_leg_watcher.py` (FRA leg). arg_fill_hunter is DEAD (match played).
- **Settings** — NEVER edit data/arena_autopilot.json while the server runs
  (cycle saves clobber it). Use: `POST /arena/api/settings`
  Current: `{conf_min:0.40, edge_min:0.02, max_per_bet:100, max_bets_per_run:10, bet_window_hours:24}`
- **Manual bet**: `POST /arena/api/order_fok {fixture_id, team_code, usd_size, worst_price}`
  (localhost only). team_code e.g. "COL"/"FRA"/"draw".
- **Status**: `GET /arena/api/status` (wallet, positions, bets_overview record),
  arena UI at :5050/arena, research strategies at :5050/research.

## 5. LESSONS / FIXED TRAPS — do not re-learn these the hard way

1. **The Argentina Lesson**: model said 81%, sellers only existed at 95¢.
   Skipped entirely; Egypt led 0-1 at kickoff+34'. Discipline > conviction.
   You don't bet the winner, you bet the wrong price.
2. Fake midpoints: empty books show meaningless mids (8.5¢ on an 81% favorite).
   ALWAYS check the raw CLOB book before judging price.
3. FOK "acceptance" (200/unfilled) is NOT a fill — most die in 30s. Confirm
   `completed` on /arena/api/orders.
4. The exchange PRUNES old rejected orders — an empty order list doesn't mean
   nothing was tried.
5. placed_keys dedup rebuilds from ok:True history each cycle; the
   reconciliation flips rejected orders' ok-flags (fixed 054522e/c7af64a) —
   don't revert.
6. ntfy listener: keyword-gated ("balance/unlock/wallet") + ignores own
   "DeepField*" messages (fixed — was a self-trigger loop).
7. Direct state-file edits race the cycle's save. API only.
8. The venv python.exe spawns a child interpreter — 2 PIDs per process is
   NORMAL, not a duplicate.
9. Payout redemption lags (England's credit took ~12h). The resume-after-payout
   pattern (tools/resume_after_payout.py) exists if a hold is ever needed again.
10. Public posts: never name the signal source, never reveal live positions
    (MATCH_OF_THE_DAY_ARG_EGY.md is the template for good public reasoning).

## 6. THE WIN CONDITION

Compound Forebet-confirmed, price-verified value through the semis and final:
$162 now → ~$222 if Colombia lands tonight → semis 1-2 confirmed picks at
~$100 each ($300-400 if they hit) → final sized by rank position → target
**$350-500 finish**. The chasing agents must take bad prices to catch up —
our edge is refusing to. If variance goes against us, the floor after tonight
is ~$118 with the semis still fundable: stay disciplined, the math wins the
long way.
