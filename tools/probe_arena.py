"""
probe_arena.py — Dump all available Polymarket token fields from the mapping API.
Run: .venv\Scripts\python.exe tools\probe_arena.py
"""

import json, os, sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from src.arena_betting import _get, list_upcoming_fixtures, get_mapping, get_mid

fixtures = list_upcoming_fixtures(limit=5)
print(f"Found {len(fixtures)} upcoming fixtures\n")

for f in fixtures[:3]:
    fid = f["id"]
    name = f.get("name", "?")
    print(f"=== {name} (id={fid}) ===")
    sc, raw = _get("/api/v1/web/mapping", fixture_id=fid)
    print(f"HTTP {sc}")
    print(json.dumps(raw, indent=2))
    print()
