"""
feature_importance.py — Phase 9 (Feature Importance) for DeepFieldPro.

Generic feature-importance estimation over any (X, y, feature_names) triple
— no dependency on a specific data source, so it works equally on the
bet_log.db 1X2 history available today or on Arena's own execution_log.db
once enough settled real-money bets accumulate (see
tools/feature_importance_report.py for the current wiring).

Three methods, matching the master prompt: Random Forest, XGBoost, Logistic
Regression. XGBoost is optional at import time — if it's ever removed from
the environment, this degrades to reporting that method as unavailable
rather than crashing the other two.
"""

import numpy as np


def _rf_importance(X, y, feature_names, random_state=0):
    from sklearn.ensemble import RandomForestClassifier

    clf = RandomForestClassifier(n_estimators=200, random_state=random_state, max_depth=5)
    clf.fit(X, y)
    return _ranked(feature_names, clf.feature_importances_)


def _xgb_importance(X, y, feature_names, random_state=0):
    try:
        from xgboost import XGBClassifier
    except ImportError:
        return None
    clf = XGBClassifier(
        n_estimators=200, max_depth=3, random_state=random_state,
        eval_metric="logloss", verbosity=0,
    )
    clf.fit(X, y)
    return _ranked(feature_names, clf.feature_importances_)


def _logreg_importance(X, y, feature_names, random_state=0):
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler

    # Standardize first -- raw logistic coefficients aren't comparable across
    # features with different scales (e.g. edge_pct in [0,20] vs a 0/1 flag).
    Xs = StandardScaler().fit_transform(X)
    clf = LogisticRegression(max_iter=1000, random_state=random_state)
    clf.fit(Xs, y)
    return _ranked(feature_names, np.abs(clf.coef_[0]))


def _ranked(feature_names, raw_importances):
    total = float(np.sum(raw_importances))
    normalized = raw_importances / total if total > 0 else raw_importances
    pairs = sorted(zip(feature_names, normalized), key=lambda p: p[1], reverse=True)
    return [{"feature": f, "importance": round(float(v), 4)} for f, v in pairs]


METHODS = {
    "random_forest": _rf_importance,
    "xgboost": _xgb_importance,
    "logistic_regression": _logreg_importance,
}


def estimate_importance(X, y, feature_names, methods=("random_forest", "xgboost", "logistic_regression")):
    """
    X: list of feature vectors (same length as feature_names each);
    y: parallel list of binary labels (0/1).

    Returns {method: [{"feature":..., "importance":...}, ...] or None}.
    A method reports None (not a crash) when: fewer than 20 samples, only
    one class present in y, or (xgboost specifically) the package isn't
    installed. Every one of these is a real, expected possibility early in a
    new dataset's life, not an error condition.
    """
    result = {}
    n = len(y) if y else 0
    single_class = len(set(y)) < 2 if y else True
    if n < 20 or single_class:
        return {m: None for m in methods}

    X_arr = np.asarray(X, dtype=float)
    y_arr = np.asarray(y)
    for m in methods:
        fn = METHODS.get(m)
        if fn is None:
            result[m] = None
            continue
        try:
            result[m] = fn(X_arr, y_arr, feature_names)
        except Exception:
            result[m] = None
    return result
