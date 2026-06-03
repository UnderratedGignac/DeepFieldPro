import codecs
import re

text = codecs.open("test_output.txt", encoding="utf-16").read()

lines = text.split("\n")
results = []

current_match = "Unknown"
current_player = "Unknown"
expected_goals = 0.0
expected_cards = 0.0
expected_offsides = 0.0
expected_shots = 0.0
expected_sot = 0.0

for idx, line in enumerate(lines):
    if "EVALUATING MATCH" in line:
        current_match = (
            line.replace("--- EVALUATING MATCH ", "").replace(" ---", "").strip()
        )
    elif "Role:" in line and "Start prob:" not in line:
        # e.g.   Luka Modric | Role: central_mid
        current_player = line.split("|")[0].strip()
    elif "Expected goals/match:" in line or "Expected goals/match" in line:
        g_match = re.search(r"goals/match:\s*([\d\.]+)", line)
        c_match = re.search(r"cards/match:\s*([\d\.]+)", line)
        o_match = re.search(r"offsides/match:\s*([\d\.]+)", line)
        if g_match:
            expected_goals = float(g_match.group(1))
        if c_match:
            expected_cards = float(c_match.group(1))
        if o_match:
            expected_offsides = float(o_match.group(1))
    elif "[PAPER TRADE] Would bet" in line:
        stake_match = re.search(r"\$([\d\.]+)", line)
        edge_match = re.search(r"Edge:\s*([\d\.]+)%", line)
        id_match = re.search(r"ID:\s*([\w\-]+)", line)

        # Look back up to 5 lines for "Evaluating opportunity"
        market_label = "Unknown"
        line_val = 0.0
        for offset in range(1, 10):
            prev_line = lines[idx - offset]
            if "Evaluating opportunity:" in prev_line:
                # e.g. Evaluating opportunity: goals_first | over 0.0 @ 1.9
                opp_match = re.search(
                    r"Evaluating opportunity:\s*([\w_]+)\s*\|\s*over\s*([\d\.]+)",
                    prev_line,
                )
                if opp_match:
                    market_label = opp_match.group(1)
                    line_val = float(opp_match.group(2))
                break

        # Decide which expected value to print based on market type
        exp_val = expected_goals
        if "cards" in market_label:
            exp_val = expected_cards
        elif "offsides" in market_label:
            exp_val = expected_offsides
        elif "shots" in market_label:
            # Let's search lines below the player line
            # Default to average shots (we don't have it parsed easily, but let's approximate or print rates)
            exp_val = 1.1  # average rate
        elif "sot" in market_label:
            exp_val = 0.5  # average rate

        results.append(
            {
                "match": current_match,
                "player": current_player,
                "market": market_label,
                "line": line_val,
                "expected_val": exp_val,
                "stake": float(stake_match.group(1)) if stake_match else 0.0,
                "edge": float(edge_match.group(1)) if edge_match else 0.0,
                "bet_id": id_match.group(1) if id_match else "N/A",
            }
        )

print(f"Total Bets Placed: {len(results)}")
print("\n" + "=" * 110)
print(
    f"{'PLAYER':<20} | {'MATCH':<25} | {'MARKET':<20} | {'LINE':<6} | {'EXP/90':<6} | {'EDGE':<6} | {'STAKE':<8}"
)
print("=" * 110)
# Sort by edge descending
results = sorted(results, key=lambda x: x["edge"], reverse=True)
for r in results:
    print(
        f"{r['player']:<20} | {r['match']:<25} | {r['market']:<20} | {r['line']:<6.1f} | {r['expected_val']:<6.2f} | {r['edge']:<5.1f}% | ${r['stake']:<7.2f}"
    )
print("=" * 110)
