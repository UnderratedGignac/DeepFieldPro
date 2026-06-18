import numpy as np
import lightgbm as lgb
from scipy.special import expit


def zip_objective(preds, train_data, pi=0.1):
    """
    Custom ZIP Objective for LightGBM.
    'preds' are raw scores corresponding to log(lambda).
    'pi' is the probability of structural zeros (inflation parameter).
    """
    y_true = train_data.get_label()
    lam = np.exp(preds)

    # Gradient and Hessian vectors
    grad = np.zeros_like(preds)
    hess = np.zeros_like(preds)

    # Case y = 0
    idx_zero = y_true == 0
    p0 = pi + (1 - pi) * np.exp(-lam[idx_zero])
    # dLL/d_lambda * d_lambda/df
    grad[idx_zero] = -((1 - pi) * np.exp(-lam[idx_zero]) * lam[idx_zero]) / p0
    # Simplified Hessian for y=0
    hess[idx_zero] = lam[idx_zero]  # Fallback to Poisson-like hessian

    # Case y > 0
    idx_positive = y_true > 0
    grad[idx_positive] = lam[idx_positive] - y_true[idx_positive]
    hess[idx_positive] = lam[idx_positive]

    # LightGBM minimizes the objective, so we return grad and hess of negative LL
    return grad, hess


def zip_metric(preds, train_data, pi=0.1):
    """
    Custom ZIP Evaluation Metric (Log-Loss).
    """
    y_true = train_data.get_label()
    lam = np.exp(preds)

    ll = np.zeros_like(preds)

    # Case y = 0
    idx_zero = y_true == 0
    ll[idx_zero] = np.log(pi + (1 - pi) * np.exp(-lam[idx_zero]))

    # Case y > 0
    idx_positive = y_true > 0
    # Using Stirling's approximation or just ignoring log(y!) for relative comparison
    ll[idx_positive] = (
        np.log(1 - pi)
        - lam[idx_positive]
        + y_true[idx_positive] * np.log(lam[idx_positive])
    )

    return "zip_ll", -np.mean(ll), True


# --- Training Script Snippet ---
"""
import lightgbm as lgb
from src.models.custom_distributions import zip_objective, zip_metric

train_set = lgb.Dataset(X_train, label=y_train)
valid_set = lgb.Dataset(X_val, label=y_val, reference=train_set)

params = {
    "learning_rate": 0.05,
    "num_leaves": 31,
    "feature_fraction": 0.8,
}

model = lgb.train(
    params,
    train_set,
    num_boost_round=1000,
    valid_sets=[valid_set],
    fobj=zip_objective,
    feval=zip_metric,
    callbacks=[lgb.early_stopping(stopping_rounds=50)]
)
"""
