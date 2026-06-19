"""Probe Stair AI API to see what market types and mappings are available."""

import sys, os, json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from src.arena_betting import _get, list_upcoming_fixtures, get_mapping, ARENA

fixtures = list_upcoming_fixtures(10)
print(f"Found {len(fixtures)} upcoming WC fixtures\n")

for f in fixtures[:3]:
    fid = f["id"]
    name = f.get("name", "?")
    print(f"=== {name} (id={fid}) ===")

    mapping = get_mapping(fid)
    if mapping:
        print("Mapping keys:", [k for k in mapping.keys()])
        print("Tokens available:")
        for k, v in mapping.items():
            if "token" in k.lower() or "market" in k.lower() or "ticker" in k.lower():
                print(f"  {k}: {str(v)[:60]}")
    else:
        print("  No mapping")
    print()

# Check if Stair AI has a markets endpoint
print("Checking /api/v1/arena/markets ...")
sc, resp = _get("/api/v1/arena/markets")
print(f"  HTTP {sc}: {str(resp)[:200]}")

print("\nChecking /api/v1/arena/fixture-markets ...")
if fixtures:
    sc, resp = _get(f"/api/v1/arena/fixture-markets/{fixtures[0]['id']}")
    print(f"  HTTP {sc}: {str(resp)[:200]}")
