---
title: AGENTS — AI Agent Orientation
tags: [moc, entrypoint]
---

# 🤖 AGENTS.md — Start Here (AI Agent Orientation)

> Standard entry file for AI coding agents. Read this first, then follow the map.

**DeepFieldPro** is a *local* football (soccer) betting **research & operations**
platform. It scrapes fixtures + odds, runs ML models to produce probabilities,
compares them to live market prices, and surfaces value bets on a local Flask
dashboard. **Betting execution is SHADOW (paper) only by default.**

## Read these first (authoritative)
- [[CLAUDE]] — the canonical project guide (env, run, modules, gotchas). **Trust this over everything else.**
- [[00 - Map of Content]] — the navigable knowledge map (hub of this vault).

## Fast facts an agent needs
| Thing | Value |
|---|---|
| Language / runtime | Python **3.12** in a project venv |
| Interpreter | `.venv\Scripts\python.exe` (NOT bare `python`) |
| Primary run | `.venv\Scripts\python.exe src\live_dashboard_server.py` |
| Dashboard URL | `http://127.0.0.1:5050` (or `DEEPFIELD_PORT`) |
| OS / shell | Windows / PowerShell |
| Safety default | `SHADOW_MODE=True` → `place_bet()` records mock bets only |
| Real-money path | `arena_betting.py` (capped $5/order, requires `confirm:true`) |

## The map (one note per topic)
1. [[01 - Architecture]] — components & how they fit
2. [[02 - Data Flow]] — how a match reaches the dashboard
3. [[03 - Entry Points & Modules]] — what each `src/` file does
4. [[04 - Databases & Data]] — the DBs and state files
5. [[05 - Configuration]] — `.env`, settings, models
6. [[06 - Safety & Risk]] — shadow mode, real-money guardrails
7. [[07 - Known Issues & Gotchas]] — traps to avoid
8. [[08 - Running the System]] — exact commands
9. [[09 - Conventions]] — house rules for working here

## Source-of-truth docs (longer, human-written)
[[USER_GUIDE]] · [[DEEPFIELD_SYSTEM_ARCHITECTURE]] · [[IMPLEMENTATION_PLAN]] ·
[[FILE_INVENTORY_DEEPFIELDPRO]] · [[DEEPFIELD_AUDIT_REPORT]] · [[SYSTEM_AUDIT_DOCUMENTATION]]
