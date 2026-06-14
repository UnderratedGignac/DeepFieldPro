---
title: Conventions
tags: [ops]
---

# 📐 Conventions

Back to [[00 - Map of Content]]

- **Use the venv interpreter explicitly** — `.venv\Scripts\python.exe`, never bare `python` (the system only has the Windows Store stub).
- **Windows / PowerShell** is the environment. Background the server; tail `server*.log`.
- **Respect [[06 - Safety & Risk|SHADOW mode]]** — don't flip to LIVE; it's an unimplemented placeholder anyway.
- **Don't break the fallback metadata** — see the `fetch_betarabia_odds()` warning in [[07 - Known Issues & Gotchas]].
- **Authoritative doc is [[CLAUDE]]** — when these notes and the code disagree, re-read the code and CLAUDE.md.

Related: [[08 - Running the System]] · [[03 - Entry Points & Modules]]
