import json

bets_data = json.load(open('data/todays_single_bets.json', encoding='utf-8'))
bets = bets_data['bets']
batch = [b for b in bets if b['status'] == 'BATCH']
monitor = [b for b in bets if b['status'] == 'MONITOR']

print("=" * 64)
print("DEEPFIELDPRO — TONIGHT'S PREDICTIONS")
print(f"Generated : {bets_data['generated_at']}")
print(f"Bankroll  : ${bets_data['bankroll']:.2f}")
print(f"Total markets analysed: {len(bets)}")
print(f"BATCH bets (place now) : {len(batch)}")
print(f"MONITOR bets           : {len(monitor)}")
print("=" * 64)

print("\n── TOP SINGLE BETS (BATCH) ─────────────────────────────────\n")
for i, b in enumerate(batch[:25], 1):
    ev_pct = round(b['ev'] * 100, 1)
    fixture = b['fixture']
    market = b['market']
    selection = b['selection']
    odds = b['raw_odds']
    fp = round(b['fair_prob'] * 100, 1)
    stake = b['kelly_stake']
    stake_pct = b['stake_pct']
    conf = b['confidence']
    print(f"#{i} | {fixture}")
    print(f"   Market    : {market}")
    print(f"   Selection : {selection}")
    print(f"   Odds      : {odds}")
    print(f"   Fair Prob : {fp}%")
    print(f"   EV        : +{ev_pct}%")
    print(f"   Stake     : ${stake} ({stake_pct}% of bankroll)")
    print(f"   Confidence: {conf}")
    print()

# Load parlays
try:
    pdata = json.load(open('data/todays_single_bets.json', encoding='utf-8'))
    parlays = pdata.get('parlays', [])
    if parlays:
        print("\n── TOP PARLAYS ─────────────────────────────────────────────\n")
        for i, p in enumerate(parlays[:5], 1):
            legs_list = []
            for leg_sel, fixture in zip(p.get('legs', []), p.get('fixtures', [])):
                legs_list.append(f"{fixture} [{leg_sel}]")
            legs = " + ".join(legs_list)
            combined_odds = p.get('parlay_odds', '?')
            parlay_ev = round(p.get('parlay_ev', 0) * 100, 1) if isinstance(p.get('parlay_ev'), (int, float)) else p.get('parlay_ev', 0)
            stake = p.get('parlay_stake', 0)
            print(f"PARLAY #{i}: {legs}")
            print(f"   Combined Odds: {combined_odds}  |  EV: +{parlay_ev}%  |  Stake: ${stake}")
            print()
except Exception as e:
    print(f"(Parlays: {e})")
