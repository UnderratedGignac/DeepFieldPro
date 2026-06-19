"""Preview the WhatsApp hot picks message without sending it."""
import json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

DATA = os.path.join(os.path.dirname(__file__), "..", "data", "todays_dashboard_state.json")
BANKROLL = 10.0

with open(DATA, encoding="utf-8") as f:
    state = json.load(f)

picks = []
for item in state:
    match = item.get("match", "")
    league = item.get("league", "Unknown")
    status = item.get("status_code", "")
    if status not in ("NS", "TBD", ""):
        continue
    pred = item.get("prediction") or {}
    markets = pred.get("markets") or {}
    for sel in markets.get("1X2") or []:
        ev = sel.get("ev") or sel.get("ev_best") or 0.0
        prob = sel.get("prob", 0.0)
        odds = sel.get("best_odds") or sel.get("odds") or 0.0
        selection = sel.get("selection", "")
        if ev <= 0 or prob <= 0 or odds <= 1.0:
            continue
        if "draw" in selection.lower() or "(x)" in selection.lower():
            continue
        p = prob / 100.0
        b = odds - 1.0
        kf = max(0.0, (p * odds - 1.0) / b) if b > 0 else 0.0
        stake = round(min(kf * 0.25 * BANKROLL, BANKROLL * 0.25), 2)
        stake = max(stake, 0.25)
        picks.append({
            "match": match, "league": league, "selection": selection,
            "odds": odds, "prob": prob, "ev": ev, "stake": stake,
        })

picks.sort(key=lambda x: x["ev"], reverse=True)
print(f"Found {len(picks)} qualifying picks.\n")

if not picks:
    print("No picks qualify — WhatsApp would not send.")
    sys.exit(0)

from datetime import datetime
today_str = datetime.now().strftime("%Y-%m-%d")
lines = [f"*DeepField Hot Bets - {today_str}*\n"]
total_stake = 0.0
for i, p in enumerate(picks[:3], 1):
    sel = p["selection"]
    if "(1)" in sel or "home" in sel.lower():
        parts = p["match"].split(" vs ")
        label = parts[0].strip() + " to win" if parts else sel
    elif "(2)" in sel or "away" in sel.lower():
        parts = p["match"].split(" vs ")
        label = parts[-1].strip() + " to win" if parts else sel
    else:
        label = sel
    lines.append(
        f"#{i} {p['match']} : {label}\n"
        f"League: {p['league']}\n"
        f"Odds: {p['odds']:.2f} | Conf: {p['prob']:.0f}% | EV: +{p['ev']*100:.1f}%\n"
        f"*Stake (${BANKROLL:.0f} bankroll): ${p['stake']:.2f}*\n"
    )
    total_stake += p["stake"]
lines.append(f"Total exposure: ${total_stake:.2f}")
lines.append("_DeepField Research - bet responsibly_")

print("--- MESSAGE PREVIEW ---")
print("\n".join(lines))
print("-----------------------")
print(f"\nTotal stake: ${total_stake:.2f} on a ${BANKROLL:.0f} bankroll")
