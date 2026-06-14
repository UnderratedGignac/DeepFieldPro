---
title: Safety & Risk
tags: [safety]
---

# 🛡️ Safety & Risk — READ BEFORE RUNNING

Back to [[00 - Map of Content]]

## Shadow mode (the default safety net)
- `place_bet()` runs the **SHADOW_MODE** branch (default `True` in `dfp_config.py`) → records mock **"SHADOW"** bets to DB only.
- The **LIVE branch is an unimplemented placeholder** ("Real capital execution not yet fully linked").
- ⚠️ `auto_place_bets` in `settings.json` does **NOT** actually gate placement — don't assume it's a kill switch.

## What the daemon DOES do externally when running
Even in shadow mode, running the daemon makes real external calls:
- STAIR-AI order POSTs (to `staging.stair-ai.com`)
- Optional WhatsApp alerts
- Live web scraping (Playwright/Chromium)

## The one real-money path
- `arena_betting.py` → `/arena/api/place` is the **only** path that can spend real money.
- Guardrails: requires POST `{"confirm": true}`, **capped at $5/order**, wallet buffer, `MAX_BETS_PER_RUN`. `/arena/api/analyze` is read-only.

> Bottom line for an agent: assume **no real-money betting** by default, but know the daemon still hits the network, and the Arena path *can* place real orders if explicitly confirmed.

Related: [[03 - Entry Points & Modules]] · [[07 - Known Issues & Gotchas]]
