---
title: Configuration
tags: [config]
---

# ⚙️ Configuration

Back to [[00 - Map of Content]] · Settings file details: [[04 - Databases & Data]]

## `.env` (loaded via python-dotenv / pydantic-settings)
Keys include:
- `API_FOOTBALL_KEY`
- `STAIR_AI_API_KEY` — used by [[06 - Safety & Risk|Arena real-money]] path
- `WHATSAPP_*` — optional alerts
- `DEEPFIELD_*` — risk params (and `DEEPFIELD_PORT`, `DEEPFIELD_DISABLE_DAEMON`)
- `BROWSER_*`
- `BETFAIR_*` — ⚠️ **placeholders** (`your_username`); Betfair is NOT configured.

> Required dep NOT in `requirements.txt` historically: **`pydantic-settings`** (now pinned). The daemon needs it.

## Models
- ML models/artifacts live in `models/`.
- `requirements.txt` pins `scikit-learn==1.8.0`; legacy 1.6.1 tree models were re-pickled (`*.sk161.bak` backups kept). All 15 artifacts load cleanly.

## Toggles worth knowing
| Env var | Effect |
|---|---|
| `DEEPFIELD_PORT` | Dashboard port (default 5050). |
| `DEEPFIELD_DISABLE_DAEMON=1` | UI only — no scraping/predictions/betting. |

Related: [[03 - Entry Points & Modules]] · [[08 - Running the System]]
