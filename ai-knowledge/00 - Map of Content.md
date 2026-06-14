---
title: Map of Content
tags: [moc]
---

# 🗺️ DeepFieldPro — Map of Content

The hub of this knowledge base. Every topic note links back here, so the graph
forms a clean hub-and-spoke around this node.

Entry point for agents: [[AGENTS]] · Canonical guide: [[CLAUDE]] · Home page: [[index]]

## Topics
- [[01 - Architecture]] — the big picture: scraper → daemon → models → dashboard
- [[02 - Data Flow]] — the exact path a fixture takes to the UI
- [[03 - Entry Points & Modules]] — file-by-file in `src/`
- [[04 - Databases & Data]] — `data/*.db` and the JSON state files
- [[05 - Configuration]] — `.env`, `settings.json`, `models/`
- [[06 - Safety & Risk]] — SHADOW mode and real-money guardrails
- [[07 - Known Issues & Gotchas]] — the landmines
- [[08 - Running the System]] — copy-paste commands
- [[09 - Conventions]] — how to work in this repo

## Two stacks (don't confuse them)
- **Primary**: Flask `live_dashboard_server.py` + `live_predictions_daemon.py` — see [[01 - Architecture]].
- **Newer / separate**: FastAPI `api/main.py` + `orchestrator.py` — a different service path.

## Reference docs
[[USER_GUIDE]] · [[DEEPFIELD_SYSTEM_ARCHITECTURE]] · [[IMPLEMENTATION_PLAN]] ·
[[FILE_INVENTORY_DEEPFIELDPRO]] · [[DEEPFIELD_AUDIT_REPORT]] · [[SYSTEM_AUDIT_DOCUMENTATION]]
