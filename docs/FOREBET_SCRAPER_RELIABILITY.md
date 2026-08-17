# Forebet scraper — reliability notes & runbook

This module gates REAL-MONEY arena orders (Forebet-confirmation gate) and the
paper TIPSTER_FOREBET ledger. Fail-safe direction: **no data in = nothing gets
confirmed = nothing is bet.** Every failure mode below degrades to "sit out",
never to "bet on stale/wrong data".

## Incident 2026-07-10 (root cause of missed semifinal confirmations)

Forebet's daily list pages (`football-tips-and-predictions-for-today` /
`-for-tomorrow`) **do not include World Cup fixtures**. WC matches are only on
the competition page `/en/predictions-world/world-cup`. The gate fetched only
the daily pages → every WC semifinal showed `tipster_confirmed: false` while
forebet.com visibly published picks. Fixed by merging the WC page into
`get_forebet_predictions()`, date-filtered per row via `<time datetime>` —
the WC page also lists PLAYED rounds with their old pre-match predictions,
which must never confirm a future fixture (repeat pairings, e.g. a final
between teams that already met).

A second bug fixed at the same time: for dates ≥2 days out the old code
silently returned the TODAY page (wrong day's data under a future label).
Now: daily page only for today/tomorrow; far dates come from the WC page only.

## Failure taxonomy (implemented in `_fetch_forebet`)

| Failure | Detection | Handling |
|---|---|---|
| Network timeout / conn error | exception | 3 attempts, exp backoff (2s → 5s), then None |
| 403 / 429 (block / rate limit) | status code | warn + same backoff; persistent block → picks stay empty (gate sits out) |
| Layout change | WC page 200 OK but 0 `div.rcnt` rows where there were >0 | WARNING log: "layout change? Confirmations will stall." |
| Forebet publishes late | page OK, target match absent | picks refresh every 30 min (gate TTL) / 15 min (WC page TTL) — resolves itself |

## Monitoring / verification

- **Probe (read-only), run before any match window:**
  `.venv\Scripts\python.exe tools\forebet_probe.py`
  Prints picks for today/tomorrow/+2 and, for each live arena candidate, the
  fresh agreement verdict vs what the running server last saw (flags drift —
  e.g. code updated but server not restarted).
- Unit tests: `tests/test_forebet_wc_page.py` (fixture: real WC page HTML,
  `tests/fixtures/forebet_wc_20260710.html`).
- Server logs: every fetch logs `[FOREBET] GET <url> -> <status> (<bytes>)`
  and per-page parsed-row counts.

## Runbook: "Forebet shows a pick but the arena won't confirm"

1. Run the probe. If the fresh verdict is True but `server saw=False` →
   the running server predates the fix or its 30-min cache hasn't expired:
   restart via `RESTART_CLEAN.ps1` (user action — restarting arms live betting).
2. If the probe shows no rows for the date: check the WC page in a browser.
   Layout change → update `_parse_forebet_wc_html` selectors; re-run tests.
3. If fetches log 403/429: Forebet is blocking. Do NOT hammer — the backoff
   handles it. If persistent, consider the Playwright path used by PredictZ.
4. Match-name mismatch (e.g. "USA" vs "United States"): `tipster_agrees` uses
   substring containment both ways; check both team strings, extend
   normalization if a real case appears.
