# Settlement Correctness Audit — 2026-07-12

**Question:** are settled paper bets graded from their real match scores (not randomly / by bug)?

**Answer: mostly yes going forward, NO for a material slice of the historical record.**
The current pipeline (post-provenance + fixes below) grades correctly from real scores.
The legacy record (all 1,392 W/L bets settled before 2026-07-11) contains at least
78 provably wrong grades and 194 grades from an untrustworthy lookup path.

## Method
- P&L arithmetic check over all 1,662 settled bets: **0 violations**.
- Independent re-grade: re-fetched real finished scores (ESPN + TheSportsDB — the system's
  own primary settlement sources) for every bet's date window; matched with the current
  strict matcher (level guard, both orientations, ambiguity rule); re-graded 1X2 / O/U 2.5 /
  BTTS; compared with stored results. Artifacts: `mismatches.json` (78 rows).
- Log forensics: `deep_lookup_settles.txt` (215 deep-lookup grades retained in logs).
- End-to-end sandbox test of the live pipeline (real scrapers, sandboxed data copy):
  6/6 injected bets with known real outcomes graded correctly with provenance.

## Findings
1. **78 of 273 externally re-verifiable settled bets (28.6%) disagree with the real score.**
   44 stored-L are really W, 34 stored-W are really L. 36 are club/league matches with no
   extra-time ambiguity (unambiguously wrong); 42 are WC knockout matches where the stored
   AND re-fetched grades can differ from the 90-minute betting convention.
2. **Deep-lookup is the largest wrong-score mechanism.** 215 settles in retained logs
   (194 still standing as W/L, +$2,200.41 stored P&L). 12 graded from impossible scores
   (15-2, 0-12, 12-11, 10-0 …) — all from the `google` source, whose parser accepted any
   NN-NN ≤ 15 found in the Google page body (h2h records, dates, stat boxes). The
   flashscore-home/away team-page path also grabbed wrong-match rows
   (Fenix 0-2 vs real 3-1; Real Oruro 1-1 vs real 4-1).
3. **Same-fixture contradiction:** fixture 760489 (Germany vs Paraguay, real 1-1) carries
   Home W, Home L, and Away W @9.5 (+$485.01) simultaneously — the biggest single
   distortion found.
4. Live bugs found by the sandbox E2E and **fixed 2026-07-12** (TDD, suite 461 green):
   - review-queue insert silently lost mid-sweep (db lock; second connection) → same-connection queueing;
   - sim2 fallback matcher bypassed the U23/senior level guard ('Melbourne City NPL'
     graded off 'Melbourne City U21') → level guard now applied in sim2;
   - deep-lookup trust gate: google-sourced and implausible (>9 a side / >10 total)
     scores now NEVER grade — they queue for manual review with the suggestion recorded;
   - ambiguity guard treated AGREEING scores as disagreeing when sources mixed
     list/tuple containers ((3,2) != [3,2]) → scores normalized to tuples.

## Record repair (APPLIED 2026-07-12, user-approved "record only")
- The 39 unambiguous league mis-grades (`repair_worklist_league.json`) were re-graded in
  bet_log via tools/force_correct_bet.correct_bet with `settle_source='audit-regrade'`,
  `result_verified=1`, and the real score + evidence in settle_reason. Verified: re-running
  the re-grade audit drops mismatches 78 → 39 (only the knockout set remains); 39/39 carry
  provenance; 0 P&L arithmetic violations. **No bankroll ledger was touched** (per the known
  ~$330 ledger drift, ledgers need their own reconciliation pass).

## Follow-ups (operator decisions)
- The 39 knockout/international mismatches need 90-minute scores to grade properly
  (ESPN scoreboard shows after-ET finals); left as-is, listed in mismatches.json.
- Ledger reconciliation: fold the corrected bets' deltas into the ~$330 real_bankroll
  drift audit if/when the ledgers are rebuilt from bet_log.
- 2 Melbourne City NPL bets pending manual review: Flashscore lists the fixture as
  'Melbourne City U21 vs Heidelberg Utd (2-2)' — if the NPL side is the U21 squad,
  Draw @4.35 won; operator to confirm and force-settle.

## FOREBET-specific verification (later on 2026-07-12, user question "is Forebet real?")
- Re-verified all 89 since-07-09 settled TIPSTER_FOREBET bets against ESPN/TSDB + fresh
  Flashscore: 42 confirmed, **33 WRONG** (mostly the 2026-07-09 UEFA-qualifier day: CSKA Sofia
  +$125, Liepaja +$57.50, Kalju +$54.38, Minsk +$32.50 were fake wins; 20 false losses the
  other way), 14 unverifiable. All 33 repaired (record-only, settle_source='audit-regrade').
- Corrected era P&L: +$412.59 -> +$285.99 (+43.3% ROI), of which externally VERIFIED bets
  contribute only +$65.57; +$83.75 (Melbourne) manually verified; +$136.67 remains on 13
  unverifiable legacy grades (half of it Kazakh-reserves wins). All-time corrected: +$256.06.
- Verdict: Forebet is not proven profitable — the verified core is modestly positive on a
  tiny sample; the headline ROI was inflated ~$127 by settlement bugs.
