"""
Clear placed_keys for future WC fixtures so the autopilot can re-bet
them with the new wallet balance. Already-kicked-off fixtures are left locked.
Then immediately run one autopilot cycle.
"""

import sys, os, json, time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

STATE_FILE = os.path.join(
    os.path.dirname(__file__), "..", "data", "arena_autopilot.json"
)

with open(STATE_FILE, encoding="utf-8") as f:
    state = json.load(f)

now_ts = time.time()

# Build a map of fixture_id -> kickoff_ts from last_candidates
kickoff_map = {}
for c in state.get("last_candidates", []):
    kickoff_map[c["fixture_id"]] = c.get("kickoff_ts", 0)

old_keys = set(state.get("placed_keys", []))
keep_keys = set()
unlocked = []

for key in old_keys:
    fid = key.split(":")[0]
    ko_ts = kickoff_map.get(fid, 0)
    if ko_ts and ko_ts <= now_ts:
        # Already kicked off — keep locked
        keep_keys.add(key)
        print(f"  KEEP (live/done): {key}")
    else:
        unlocked.append(key)
        print(f"  UNLOCK (future):  {key}")

state["placed_keys"] = list(keep_keys)
# Reset daily spend so the cap doesn't block new bets
state["daily"] = {"date": time.strftime("%Y-%m-%d"), "spent": 0.0}

with open(STATE_FILE, "w", encoding="utf-8") as f:
    json.dump(state, f, indent=2)

print(f"\nUnlocked {len(unlocked)} future fixtures. Locked {len(keep_keys)} live/done.")
print("Running autopilot cycle now...")

from src.arena_betting import autopilot_cycle

summary = autopilot_cycle()
print(f"\nCycle result: {summary}")
