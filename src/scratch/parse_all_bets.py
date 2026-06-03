# mypy: ignore-errors
import codecs
import re

text = codecs.open("test_output.txt", encoding="utf-16").read()

lines = text.split("\n")
results = []

current_match = "Unknown"
current_player = "Unknown"
expected_passes = 0.0
expected_shots = 0.0
expected_sot = 0.0

for line in lines:
    if "EVALUATING MATCH" in line:
        current_match = line.strip()
    elif "Role:" in line and "Start prob:" in line:
        current_player = line.split("|")[0].strip()
    elif "Expected minutes:" in line:
        pass
    elif "Expected passes/90:" in line:
        p50_match = re.search(r"p50=([\d\.]+)", line)
        if p50_match:
            expected_passes = float(p50_match.group(1))
    elif "Expected shots/90:" in line:
        p50_match = re.search(r"p50=([\d\.]+)", line)
        if p50_match:
            expected_shots = float(p50_match.group(1))
    elif "Expected SOT/90:" in line:
        p50_match = re.search(r"p50=([\d\.]+)", line)
        if p50_match:
            expected_sot = float(p50_match.group(1))
    elif "Evaluating opportunity:" in line:
        # e.g. Evaluating opportunity: passes_over_30.5 | over 30.5 @ 1.9
        opp_match = re.search(r"Evaluating opportunity:\s*([\w_\.]+)", line)
        if opp_match:
            current_market = opp_match.group(1)
    elif "[PAPER TRADE] Would bet" in line:
        # e.g. [PAPER TRADE] Would bet $184.47 @ 1.9 | Edge: 27.83% | ID: PAPER-064aea29
        stake_match = re.search(r"\$([\d\.]+)", line)
        edge_match = re.search(r"Edge:\s*([\d\.]+)%", line)
        id_match = re.search(r"ID:\s*([\w\-]+)", line)

        # Decide which expected value to print based on market type
        exp_val = expected_passes
        if "shots" in current_market:
            exp_val = expected_shots
        elif "sot" in current_market:
            exp_val = expected_sot

        results.append(
            {
                "match": current_match,
                "player": current_player,
                "market": current_market,
                "expected_val": exp_val,
                "stake": float(stake_match.group(1)) if stake_match else 0.0,
                "edge": float(edge_match.group(1)) if edge_match else 0.0,
                "bet_id": id_match.group(1) if id_match else "N/A",
            }
        )

print(f"Total Bets Placed: {len(results)}")
print("\n" + "=" * 95)
print(
    f"{'PLAYER':<20} | {'MATCH':<25} | {'MARKET':<20} | {'EXP':<6} | {'EDGE':<6} | {'STAKE':<8}"
)
print("=" * 95)
# Sort by edge descending
results = sorted(results, key=lambda x: x["edge"], reverse=True)
for r in results:
    # Match short name
    m_name = r["match"].replace("--- EVALUATING MATCH ", "").replace(" ---", "")
    # E.g. 1001 | Opponent: Belgium -> Croatia vs Belgium
    print(
        f"{r['player']:<20} | {m_name:<25} | {r['market']:<20} | {r['expected_val']:<6.1f} | {r['edge']:<5.1f}% | ${r['stake']:<7.2f}"
    )
print("=" * 95)
