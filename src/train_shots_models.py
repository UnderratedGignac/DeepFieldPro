import lightgbm as lgb
import pandas as pd
import os

print("Loading shots training dataset...")
df = pd.read_csv('C:/Users/Elie/DeepFieldPro/data/shots_training_dataset.csv')

df['Percentage of Minutes Played'] = df['Min%']

# Encode Position
position_map = {
    'MF': 3, 'DF': 2, 'FW': 1, 'GK': 0, 'MF,FW': 2, 'DF,MF': 2,
    'Center Midfield': 3, 'Defensive Midfield': 3, 'Attacking Midfield': 3,
    'Left Midfield': 3, 'Right Midfield': 3,
    'Center Defensive Midfield': 3, 'Left Center Midfield': 3, 'Right Center Midfield': 3,
    'Left Defensive Midfield': 3, 'Right Defensive Midfield': 3,
    'Center Back': 2, 'Left Back': 2, 'Right Back': 2,
    'Left Center Back': 2, 'Right Center Back': 2,
    'Left Wing Back': 2, 'Right Wing Back': 2,
    'Left Wing': 1, 'Right Wing': 1, 'Center Forward': 1,
    'Left Center Forward': 1, 'Right Center Forward': 1,
    'Secondary Striker': 1, 'Goalkeeper': 0,
}
df['Position_encoded'] = df['Position'].map(position_map).fillna(2)

# FEATURES
FEATURES = [
    'Age',
    'Position_encoded',                       
    'Minutes Played',                 
    'Mn/Start',                       
    'Percentage of Minutes Played',   
    'Crs',                            
    'Interceptions',                  
    'Tackles Won',                    
    'ppda',                           
    'opp_possession_allowed',         
    'sample_weight',                  
]

df = df.dropna(subset=FEATURES + ['shots_per_90', 'sot_per_90'])

X = df[FEATURES].apply(pd.to_numeric, errors='coerce')
y_sh = df['shots_per_90']
y_sot = df['sot_per_90']
weights = df['sample_weight']

os.makedirs('C:/Users/Elie/DeepFieldPro/models', exist_ok=True)

# 1. Train Shots Models
print("\nTraining SHOTS quantile models...")
shots_models = {}
for q in [0.10, 0.50, 0.90]:
    params = {
        'objective': 'quantile',
        'alpha': q,
        'metric': 'quantile',
        'num_leaves': 63,         
        'learning_rate': 0.03,
        'n_estimators': 500,
        'min_child_samples': 15,
        'verbose': -1
    }
    m = lgb.LGBMRegressor(**params)
    m.fit(X, y_sh, sample_weight=weights)
    shots_models[f'p{int(q*100)}'] = m
    print(f"  Quantile model q={q} trained. Sample prediction: {m.predict(X.head(1))[0]:.1f} shots/90")

for name, m in shots_models.items():
    m.booster_.save_model(f'C:/Users/Elie/DeepFieldPro/models/shots_{name}.txt')

# 2. Train Shots on Target Models
print("\nTraining SHOTS ON TARGET (SoT) quantile models...")
sot_models = {}
for q in [0.10, 0.50, 0.90]:
    params = {
        'objective': 'quantile',
        'alpha': q,
        'metric': 'quantile',
        'num_leaves': 63,         
        'learning_rate': 0.03,
        'n_estimators': 500,
        'min_child_samples': 15,
        'verbose': -1
    }
    m = lgb.LGBMRegressor(**params)
    m.fit(X, y_sot, sample_weight=weights)
    sot_models[f'p{int(q*100)}'] = m
    print(f"  Quantile model q={q} trained. Sample prediction: {m.predict(X.head(1))[0]:.1f} sot/90")

for name, m in sot_models.items():
    m.booster_.save_model(f'C:/Users/Elie/DeepFieldPro/models/sot_{name}.txt')

print("\nAll shots and sot models trained and saved to models/ directory successfully!")
