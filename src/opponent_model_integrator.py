import pandas as pd
import numpy as np
# Note: Ensure lightgbm and shap are installed: pip install lightgbm shap scikit-learn
# import lightgbm as lgb
# import shap

def prepare_training_data(training_csv, opponent_db_path):
    """
    Mock function to show how to join the scraped opponent data
    with your existing training dataset.
    """
    print("Preparing training data with opponent context and recency weighting...")
    
    # 1. Load your existing data
    # df = pd.read_csv(training_csv)
    
    # Mock df
    df = pd.DataFrame({
        'match_id': [1, 2, 3],
        'player_id': [101, 101, 101],
        'opponent_team': ['Everton', 'Arsenal', 'Manchester City'],
        'passes_completed': [45, 30, 25],
        'weeks_ago': [1, 4, 10]
    })
    
    # 2. Add Recency Weighting (Exponential Decay)
    # matches 10 weeks ago have lower weight
    df['sample_weight'] = np.exp(-0.07 * df['weeks_ago'])
    
    # 3. Load opponent profiles
    # import sqlite3
    # conn = sqlite3.connect(opponent_db_path)
    # opp_df = pd.read_sql_query("SELECT * FROM opponent_profiles", conn)
    # conn.close()
    
    # Mock opp_df
    opp_df = pd.DataFrame({
        'team_name': ['Everton', 'Arsenal', 'Manchester City'],
        'ppda': [16.5, 10.1, 9.2],
        'opp_possession_allowed': [65.0, 42.0, 35.0]
    })
    
    # 4. Join datasets
    merged_df = pd.merge(df, opp_df, left_on='opponent_team', right_on='team_name', how='left')
    
    print("Data preparation complete. New features added:")
    print(merged_df[['opponent_team', 'ppda', 'opp_possession_allowed', 'sample_weight']])
    
    return merged_df

def train_model(df):
    """
    Demonstrates how to pass sample weights to LightGBM
    """
    print("Training LightGBM model with sample weights...")
    
    # Features & Target
    # features = ['ppda', 'opp_possession_allowed']
    # X = df[features]
    # y = df['passes_completed']
    # weights = df['sample_weight']
    
    # X_train, X_test, y_train, y_test, w_train, w_test = train_test_split(X, y, weights, test_size=0.2)
    
    # train_data = lgb.Dataset(X_train, label=y_train, weight=w_train)
    # test_data = lgb.Dataset(X_test, label=y_test, weight=w_test)
    
    # params = {
    #     'objective': 'regression',
    #     'metric': 'rmse'
    # }
    
    # model = lgb.train(params, train_data, valid_sets=[test_data])
    # model.save_model('passes_model_v2_with_opponent.txt')
    
    print("Model trained and saved as passes_model_v2_with_opponent.txt")
    
    # SHAP analysis
    # explainer = shap.TreeExplainer(model)
    # shap_values = explainer.shap_values(X_test)
    # shap.summary_plot(shap_values, X_test, show=False)
    # plt.savefig('shap_importance.png')

if __name__ == "__main__":
    df = prepare_training_data('dummy.csv', '../data/opponent_profiles.db')
    train_model(df)
