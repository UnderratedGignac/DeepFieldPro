import pandas as pd, lightgbm as lgb, numpy as np, sys
sys.path.insert(0, '.')
from pricing_engine import calculate_over_prob
from utils import remove_vig

df = pd.read_csv('../data/training_dataset.csv')
row = df.iloc[0]

MINUTES_FEATURES = ['Age','Starts','Percentage of Minutes Played','Mn/Start','Mn/MP','PPM','ppda','opp_possession_allowed','sample_weight']
PASSES_FEATURES  = ['Age','Position_encoded','Minutes Played','Mn/Start','Percentage of Minutes Played','Crs','Interceptions','Tackles Won','Goals Scored While on Pitch','ppda','opp_possession_allowed','sample_weight']

pos_map = {'MF':3,'CM':3,'DM':3,'AM':3,'DF':2,'CB':2,'LB':2,'RB':2,'FW':1,'CF':1,'LW':1,'RW':1}
pos_enc = pos_map.get(str(row.get('Position','')), 2)

feats_min = {
    'Age': float(row.get('Age',26)),
    'Starts': float(row.get('Starts',1)),
    'Percentage of Minutes Played': float(row.get('Min%',0.8)),
    'Mn/Start': float(row.get('Mn/Start',75)),
    'Mn/MP': float(row.get('Mn/MP',75)),
    'PPM': float(row.get('PPM',0.5)),
    'ppda': float(row.get('ppda',12.0)),
    'opp_possession_allowed': float(row.get('opp_possession_allowed',50.0)),
    'sample_weight': 1.0,
}
feats_pass = {
    'Age': float(row.get('Age',26)),
    'Position_encoded': pos_enc,
    'Minutes Played': float(row.get('Minutes Played',75)),
    'Mn/Start': float(row.get('Mn/Start',75)),
    'Percentage of Minutes Played': float(row.get('Min%',0.8)),
    'Crs': float(row.get('Crs',1.0)),
    'Interceptions': float(row.get('Interceptions',1.0)),
    'Tackles Won': float(row.get('Tackles Won',1.0)),
    'Goals Scored While on Pitch': float(row.get('Gls',0.0)),
    'ppda': float(row.get('ppda',12.0)),
    'opp_possession_allowed': float(row.get('opp_possession_allowed',50.0)),
    'sample_weight': 1.0,
}

MODEL_DIR = 'C:/Users/Elie/DeepFieldPro/models'
models = {
    'start_clf': lgb.Booster(model_file=f'{MODEL_DIR}/minutes_start_classifier.txt'),
    'min_p10':   lgb.Booster(model_file=f'{MODEL_DIR}/minutes_p10_regressor.txt'),
    'min_p50':   lgb.Booster(model_file=f'{MODEL_DIR}/minutes_p50_regressor.txt'),
    'min_p90':   lgb.Booster(model_file=f'{MODEL_DIR}/minutes_p90_regressor.txt'),
    'pass_p10':  lgb.Booster(model_file=f'{MODEL_DIR}/passes_p10.txt'),
    'pass_p50':  lgb.Booster(model_file=f'{MODEL_DIR}/passes_p50.txt'),
    'pass_p90':  lgb.Booster(model_file=f'{MODEL_DIR}/passes_p90.txt'),
}

X_min  = pd.DataFrame([feats_min],  columns=MINUTES_FEATURES)
X_pass = pd.DataFrame([feats_pass], columns=PASSES_FEATURES)

start_prob = float(models['start_clf'].predict(X_min)[0])
min_p10    = float(models['min_p10'].predict(X_min)[0])
min_p50    = float(models['min_p50'].predict(X_min)[0])
min_p90    = float(models['min_p90'].predict(X_min)[0])
pass_p10   = float(models['pass_p10'].predict(X_pass)[0])
pass_p50   = float(models['pass_p50'].predict(X_pass)[0])
pass_p90   = float(models['pass_p90'].predict(X_pass)[0])

print(f'Position: {row.get("Position")} | pos_enc={pos_enc}')
print(f'start_prob={start_prob:.3f}  min p10/p50/p90={min_p10:.0f}/{min_p50:.0f}/{min_p90:.0f}')
print(f'pass p10/p50/p90={pass_p10:.1f}/{pass_p50:.1f}/{pass_p90:.1f}')
print(f'actual passes_per_90={row["passes_per_90"]}')

for line in [30.5, 40.5, 50.5]:
    fair_prob, exp = calculate_over_prob(pass_p10, pass_p50, pass_p90, min_p10, min_p50, min_p90, line)
    sim_over  = round(1.0/(fair_prob + 0.025), 3)
    sim_under = round(1.0/((1-fair_prob) + 0.025), 3)
    try:
        fair_probs, ov = remove_vig([sim_over, sim_under])
        edge = fair_prob - fair_probs[0]
        print(f'Line {line}: fair_prob={fair_prob:.4f} sim_over={sim_over} edge={edge*100:.2f}%')
    except Exception as e:
        print(f'Line {line}: error {e}')
