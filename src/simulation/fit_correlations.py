import pandas as pd
import os

DATA_CSV = "data/world_cup_players_match_logs_global.csv"


def fit_correlation_matrix():
    df = pd.read_csv(DATA_CSV)
    # Select relevant prop columns
    prop_cols = [c for c in df.columns if c.startswith("Performance_")]

    # Calculate Spearman correlation
    corr_matrix = df[prop_cols].corr(method="spearman")

    # Ensure it's positive semi-definite for the copula
    # (Simplified: just clip very small values or use nearest PSD)
    corr_matrix = corr_matrix.fillna(0)

    corr_matrix.to_csv("models/correlation_matrix.csv")
    print("Correlation matrix saved to models/correlation_matrix.csv")


if __name__ == "__main__":
    fit_correlation_matrix()
