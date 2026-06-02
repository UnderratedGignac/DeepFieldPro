import codecs
import re

text = codecs.open('test_output.txt', encoding='utf-16').read()

lines = text.split('\n')
opportunities = []

current_match = "Unknown"
current_player = "Unknown"
expected_val = 0.0

for idx, line in enumerate(lines):
    if "EVALUATING MATCH" in line:
        current_match = line.replace('--- EVALUATING MATCH ', '').replace(' ---', '').strip()
    elif "Role:" in line and "goals/match:" in lines[idx + 1]:
        current_player = line.split('|')[0].strip()
    elif "Evaluating opportunity:" in line:
        # e.g. Evaluating opportunity: goals_anytime | over 0.0 @ 1.9
        opp_match = re.search(r'Evaluating opportunity:\s*([\w_]+)\s*\|\s*over\s*([\d\.]+)', line)
        if opp_match:
            market = opp_match.group(1)
            line_val = float(opp_match.group(2))
            
            # Check edge and details in subsequent lines
            edge = 0.0
            model_prob = 0.0
            status = "SKIP"
            for search in range(1, 10):
                next_line = lines[idx + search]
                if "Model fair prob:" in next_line:
                    prob_match = re.search(r'Model fair prob:\s*([\d\.]+)', next_line)
                    if prob_match: model_prob = float(prob_match.group(1))
                elif "True edge:" in next_line:
                    edge_match = re.search(r'True edge:\s*([\d\.-]+)%', next_line)
                    if edge_match: edge = float(edge_match.group(1))
                elif "[PAPER TRADE] Would bet" in next_line:
                    status = "PLACED"
                    break
                elif "SKIP:" in next_line:
                    status = "SKIP"
                    break
            
            if edge >= 5.0: # Only show high value (>5% edge)
                opportunities.append({
                    'match': current_match,
                    'player': current_player,
                    'market': market,
                    'line': line_val,
                    'prob': model_prob,
                    'edge': edge,
                    'status': status
                })

print(f"Total High-Edge Opportunities Found: {len(opportunities)}")
print("\n" + "="*115)
print(f"{'PLAYER':<20} | {'MATCH':<22} | {'MARKET':<18} | {'LINE':<5} | {'PROB':<6} | {'EDGE':<6} | {'STATUS':<8}")
print("="*115)
opportunities = sorted(opportunities, key=lambda x: x['edge'], reverse=True)
for o in opportunities:
    print(f"{o['player']:<20} | {o['match']:<22} | {o['market']:<18} | {o['line']:<5.1f} | {o['prob']*100:<5.1f}% | {o['edge']:<+5.1f}% | {o['status']:<8}")
print("="*115)
