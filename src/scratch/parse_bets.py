import codecs
import re

text = codecs.open("test_output.txt", encoding="utf-16").read()

# We want to match:
#   Player Name
#   Start prob
#   Expected passes/90 (p50)
#   Bet type / line
#   Edge
#   Stake

# We split the text by "Evaluating opportunity: "
sections = text.split("Evaluating opportunity: ")

results = []
current_player = "Unknown"
expected_passes = 0.0

# Let's iterate through lines to parse information
lines = text.split("\n")
current_match = "Unknown"
for line in lines:
    if "EVALUATING MATCH" in line:
        current_match = line.strip()
    elif "Role:" in line and "Start prob:" in line:
        # Player name is before the |
        current_player = line.split("|")[0].strip()
    elif "Expected passes/90:" in line:
        # e.g. Expected passes/90: p10=27.5 p50=54.4 p90=94.9
        p50_match = re.search(r"p50=([\d\.]+)", line)
        if p50_match:
            expected_passes = float(p50_match.group(1))
    elif "[PAPER TRADE] Would bet" in line:
        # e.g. [PAPER TRADE] Would bet $184.47 @ 1.9 | Edge: 27.83% | ID: PAPER-064aea29
        stake_match = re.search(r"\$([\d\.]+)", line)
        edge_match = re.search(r"Edge:\s*([\d\.]+)%", line)
        id_match = re.search(r"ID:\s*([\w\-]+)", line)

        # Let's find the line evaluated
        # This will be in the prior lines, we can check the most recent Evaluating opportunity
        results.append(
            {
                "match": current_match,
                "player": current_player,
                "expected_passes": expected_passes,
                "stake": float(stake_match.group(1)) if stake_match else 0.0,
                "edge": float(edge_match.group(1)) if edge_match else 0.0,
                "bet_id": id_match.group(1) if id_match else "N/A",
            }
        )

print(f"Total Bets Placed: {len(results)}")
print("\n" + "=" * 80)
print(
    f"{'PLAYER':<25} | {'MATCH':<35} | {'EXP PASSES':<10} | {'EDGE':<6} | {'STAKE':<8}"
)
print("=" * 80)
# Sort by edge descending
results = sorted(results, key=lambda x: x["edge"], reverse=True)
seen = set()
for r in results:
    key = (r["player"], r["match"])
    if key in seen:
        continue
    seen.add(key)
    print(
        f"{r['player']:<25} | {r['match']:<35} | {r['expected_passes']:<10.1f} | {r['edge']:<5.1f}% | ${r['stake']:<7.2f}"
    )
print("=" * 80)
