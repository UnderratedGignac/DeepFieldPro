"""Unit tests for Phase 9 (Feature Importance) — src/feature_importance.py."""

import random

import pytest

from src import feature_importance as fi


def test_insufficient_data_returns_none_for_all_methods():
    result = fi.estimate_importance([[1, 2]] * 5, [0, 1, 0, 1, 0], ["a", "b"])
    assert result["random_forest"] is None
    assert result["logistic_regression"] is None


def test_single_class_returns_none_for_all_methods():
    X = [[1, 2]] * 30
    y = [1] * 30  # only one class present
    result = fi.estimate_importance(X, y, ["a", "b"])
    assert result["random_forest"] is None
    assert result["logistic_regression"] is None


def test_dominant_feature_ranks_highest_random_forest():
    random.seed(0)
    X, y = [], []
    for _ in range(300):
        dominant = random.random()
        noise = random.random()
        X.append([dominant, noise])
        y.append(1 if dominant > 0.5 else 0)
    result = fi.estimate_importance(X, y, ["dominant", "noise"], methods=("random_forest",))
    ranked = result["random_forest"]
    assert ranked is not None
    assert ranked[0]["feature"] == "dominant"
    assert ranked[0]["importance"] > ranked[1]["importance"]


def test_dominant_feature_ranks_highest_logistic_regression():
    random.seed(1)
    X, y = [], []
    for _ in range(300):
        dominant = random.random() * 10  # different scale -- tests standardization
        noise = random.random()
        X.append([dominant, noise])
        y.append(1 if dominant > 5 else 0)
    result = fi.estimate_importance(X, y, ["dominant", "noise"], methods=("logistic_regression",))
    ranked = result["logistic_regression"]
    assert ranked is not None
    assert ranked[0]["feature"] == "dominant"


def test_importances_sum_to_one_when_positive():
    random.seed(2)
    X = [[random.random(), random.random()] for _ in range(100)]
    y = [1 if x[0] > 0.5 else 0 for x in X]
    result = fi.estimate_importance(X, y, ["a", "b"], methods=("random_forest",))
    total = sum(r["importance"] for r in result["random_forest"])
    assert total == pytest.approx(1.0, abs=1e-6)


def test_xgboost_method_present_or_gracefully_none():
    random.seed(3)
    X = [[random.random(), random.random()] for _ in range(100)]
    y = [1 if x[0] > 0.5 else 0 for x in X]
    result = fi.estimate_importance(X, y, ["a", "b"], methods=("xgboost",))
    # Either xgboost is installed and returns a ranked list, or it's
    # unavailable and returns None -- both are valid, non-crashing outcomes.
    assert result["xgboost"] is None or isinstance(result["xgboost"], list)


def test_unknown_method_name_returns_none_not_error():
    X = [[1, 2]] * 30
    y = [0, 1] * 15
    result = fi.estimate_importance(X, y, ["a", "b"], methods=("not_a_real_method",))
    assert result["not_a_real_method"] is None
