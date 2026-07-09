# Arena Real-Money Betting — Mechanics & Risk Snapshot (2026-07-09)

Here's the exact, current mechanics — pulled directly from the code and live state files, not the docs (which have drifted before).

## Architecture

`src/arena_betting.py` is a Flask blueprint. It talks to `https://stair-ai.com` (StairAI's Arena API, header `x-api-key`) for fixtures, order placement, wallet, and to Polymarket's CLOB/gamma APIs for live prices. It runs two loops:
- `autopilot_loop()` — background thread, calls `autopilot_cycle()` every `SCAN_INTERVAL = 60` seconds ([arena_betting.py:1366](../src/arena_betting.py#L1366), [2007-2020](../src/arena_betting.py#L2007-L2020)).
- Each cycle scans up to `AUTO_SCAN_LIMIT = 104` upcoming World Cup fixtures.

## Decision pipeline (three sequential gates — this is the part that matters)

**Gate 1 — `analyze()`** ([arena_betting.py:841](../src/arena_betting.py#L841)): computes `model_prob` (blend of a World-Cup Elo model + your Dixon-Coles model, weighted 65/35 — [line 105](../src/arena_betting.py#L105)) vs `market_mid` (Polymarket midpoint). A candidate "qualifies" if `model_prob >= conf_min` AND `edge >= edge_min`. The module-level defaults (`CONF_MIN_DEFAULT=0.0`, `EDGE_MIN_DEFAULT=-1.0`, [lines 91-92](../src/arena_betting.py#L91-L92)) are deliberately permissive — but the *actual* values used at runtime come from `data/arena_autopilot.json`'s `settings` block, which I just read: **`conf_min=0.40`, `edge_min=0.02`**. So gate 1 in practice requires ≥40% model confidence and ≥2pp edge, not "bet on everything."

**Gate 2 — Forebet confirmation** ([lines 1653-1657](../src/arena_betting.py#L1653-L1657)): even after qualifying, a pick only gets a **real order** if `tipster_confirmed` (the Forebet tipster's own 1X2 pick agrees) or `real_arb` (a guaranteed 3-way arbitrage). This was added 2026-07-06 because Forebet-confirmed picks are the only paper strategy whose 95% CI is entirely above zero (+41.7% ROI, n=259). Everything else that "qualifies" at gate 1 still gets logged to the tournament leaderboard ledger (no money), but does NOT get a real order.

**Gate 3 — AP2 SpendingMandate** ([ap2_mandate.py:19-25](../src/ap2_mandate.py#L19-L25), loaded from `data/settings.json`): a second, independent check run inside `place_order()` itself, right before the HTTP POST. Current live values: `max_per_order=$100`, `daily_cap=$999`, `wallet_buffer=$0.00`, `conf_min=0.40`, `edge_min=0.02`. Any of these failing blocks the order and logs it to an AP2 audit ledger regardless of gates 1-2.

**Gate 0 — the master switch** ([place_order:1232](../src/arena_betting.py#L1232)): none of the above matters unless `DEEPFIELD_ARENA_LIVE=1` in `.env`. It currently is `1`. `autopilot_enabled = arena_live and state["enabled"]` — and `state["enabled"]` in `data/arena_autopilot.json` is currently **`True`**. So the whole pipeline is live and firing.

## Position sizing

`_wallet_kelly_size()` ([lines 708-730](../src/arena_betting.py#L708-L730)): quarter-Kelly (`kelly_f × 0.25 × wallet_balance`), hard-capped at `min(wallet_balance × MAX_WALLET_FRACTION=1.0, $100)`. But then, for Forebet-confirmed picks specifically, [lines 1659-1671](../src/arena_betting.py#L1659-L1671) override this with a **floor of 40% of current wallet balance** ("never less than 40% of the wallet on a confirmed pick"), capped by remaining daily budget and the $100/order ceiling. So a confirmed pick stakes at least 40% of whatever's left in the wallet, up to $100.

## Dedup / retry (explains the 4 duplicate Argentina orders you saw)

Each pick has a key `fixture_id:outcome`. Once an order is placed successfully it goes into `placed_keys` and won't be re-bet ([line 1644](../src/arena_betting.py#L1644)). BUT — if Stair AI later reports that order as `rejected` (thin order book, FOK kill), a reconciliation pass ([lines 1825-1865](../src/arena_betting.py#L1825-L1865)) explicitly **frees that key** with a 30-minute cooldown so it can retry. That's exactly the ~31-minute gap pattern in the ledger: the system isn't double-betting a live position, it's retrying a position that the exchange rejected — by design, not a bug. The risk is real notional exposure across retries adds up if some fills partially succeed before rejection is detected.

## Where the money stands right now (live numbers, just read from `data/arena_autopilot.json`)

- `enabled: True`, `conf_min: 0.4`, `edge_min: 0.02`, `max_per_bet: $100`, `max_bets_per_run: 10`, `bet_window_hours: 24`
- Today's spend: **$87.05** of the (uncapped in practice, `daily_cap=$999`) daily budget
- **Total staked: $229.64** → **current mark-to-market value: $5.07** → **unrealized P&L: -$224.64**, realized: $0.00
- 47 entries in the placed-bet history this run
- Last cycle: 12 fixtures scanned, 4 qualifying, 0 new bets/ledger entries that pass

That $229.64 staked vs $5.07 current value is a ~98% mark-to-market drawdown on money actually committed — worth putting in front of your consultant plainly, separate from any confidence in the model itself.
