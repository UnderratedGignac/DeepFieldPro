"""probe_polymarket.py — Get WC Winner token IDs via market slug."""
import json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from src.arena_betting import _get, get_mid

# Get WC winner event + extract slugs and outcomePrices (available without CLOB)
sc, data = _get("/api/v1/data/proxy/polymarket-gamma/events",
                slug="world-cup-winner", limit=1)
body = data.get("body") if isinstance(data, dict) else data
events = body if isinstance(body, list) else []
if not events:
    print("no event"); sys.exit(1)

ev = events[0]
markets = ev.get("markets") or []
print(f"WC Winner event: {len(markets)} teams\n")

# Try CLOB via market slug for first few teams to get token IDs
slugs_to_try = []
for m in markets[:5]:
    team_name = m.get("question","").replace("Will ","").replace(" win the 2026 FIFA World Cup?","")
    slug = m.get("slug","")
    outcome_prices = json.loads(m.get("outcomePrices","[]") or "[]")
    yes_price = float(outcome_prices[0]) if outcome_prices else None
    slugs_to_try.append((team_name, slug, yes_price, m.get("conditionId","")))

print("Teams with Gamma prices (no CLOB needed for mid):")
for name, slug, yes_price, cid in slugs_to_try:
    print(f"  {name}: YES={yes_price:.3f} ({yes_price*100:.1f}%)")
    sc2, data2 = _get(f"/api/v1/data/proxy/polymarket-clob/markets/{slug}")
    if isinstance(data2, dict) and "body" in data2:
        bd = data2["body"]
        if isinstance(bd, dict):
            tokens = bd.get("tokens") or []
            yes_tok = next((t.get("token_id") for t in tokens if t.get("outcome","").lower()=="yes"), None)
            print(f"    CLOB by slug -> yes_token={yes_tok}")
        else:
            print(f"    CLOB by slug -> {str(bd)[:100]}")
    sc3, data3 = _get("/api/v1/data/proxy/polymarket-clob/markets",
                      market_slug=slug)
    if isinstance(data3, dict) and "body" in data3:
        bd = data3["body"]
        mkts = bd if isinstance(bd, list) else (bd.get("data") or [])
        for mk in mkts[:1]:
            tokens = mk.get("tokens") or []
            yes_tok = next((t.get("token_id") for t in tokens if t.get("outcome","").lower()=="yes"), None)
            print(f"    CLOB by market_slug -> yes_token={yes_tok}")
    print()
