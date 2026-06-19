"""
train_lgbm_model.py
===================
Trains a LightGBM 1X2 classifier that combines:
  - Dixon-Coles expected goals / probabilities
  - De-vigged Pinnacle market odds (strongest predictor)
  - Rolling form (last 5 home / away games)
  - Head-to-head record (last 5 meetings)

Outputs:
  models/lgbm_1x2.pkl        — trained LGBMClassifier (joblib)
  models/lgbm_features.json  — feature names + importances
"""

import json
import math
import os
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime

import joblib
import numpy as np
from lightgbm import LGBMClassifier
from sklearn.metrics import accuracy_score, log_loss

# ── paths ────────────────────────────────────────────────────────────────────
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(ROOT, "data", "history.db")
DC_PATH = os.path.join(ROOT, "models", "dixon_coles.json")
OUT_PKL = os.path.join(ROOT, "models", "lgbm_1x2.pkl")
OUT_JSON = os.path.join(ROOT, "models", "lgbm_features.json")

# ── feature order (must match at inference time) ──────────────────────────────
FEATURE_NAMES = [
    "dc_home_prob",
    "dc_draw_prob",
    "dc_away_prob",
    "dc_exp_h",
    "dc_exp_a",
    "mkt_h_prob",
    "mkt_d_prob",
    "mkt_a_prob",
    "home_form_w5",
    "home_form_d5",
    "home_form_l5",
    "home_gf5",
    "home_ga5",
    "away_form_w5",
    "away_form_d5",
    "away_form_l5",
    "away_gf5",
    "away_ga5",
    "h2h_home_w5",
    "h2h_draw5",
    "h2h_away_w5",
]

MAX_GOALS = 10


# ── DC helpers ────────────────────────────────────────────────────────────────
def _pois(k, lam):
    return math.exp(-lam) * lam**k / math.factorial(k)


def _tau(hg, ag, lam, mu, rho):
    if hg == 0 and ag == 0:
        return 1.0 - lam * mu * rho
    if hg == 0 and ag == 1:
        return 1.0 + lam * rho
    if hg == 1 and ag == 0:
        return 1.0 + mu * rho
    if hg == 1 and ag == 1:
        return 1.0 - rho
    return 1.0


def _dc_probs_from_eg(lam, mu, rho):
    """Convert expected goals + rho to (ph, pd, pa) via joint Poisson."""
    ph = pd = pa = 0.0
    for i in range(MAX_GOALS + 1):
        for j in range(MAX_GOALS + 1):
            p = _pois(i, lam) * _pois(j, mu) * max(1e-9, _tau(i, j, lam, mu, rho))
            if i > j:
                ph += p
            elif i == j:
                pd += p
            else:
                pa += p
    tot = ph + pd + pa
    if tot <= 0:
        return None, None, None
    return ph / tot, pd / tot, pa / tot


def load_dc():
    """Load DC model; returns dict keyed by league or empty dict on failure."""
    try:
        with open(DC_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return data.get("leagues", {})
    except Exception as e:
        print(f"[warn] Could not load DC model: {e}")
        return {}


def dc_features(dc_leagues, league, home, away):
    """Return (dc_home_prob, dc_draw_prob, dc_away_prob, dc_exp_h, dc_exp_a)."""
    lg = dc_leagues.get(league)
    if not lg:
        return 0.0, 0.0, 0.0, 0.0, 0.0
    t = lg.get("teams", {})
    if home not in t or away not in t:
        return 0.0, 0.0, 0.0, 0.0, 0.0
    home_adv = lg.get("home_adv", 0.0)
    rho = lg.get("rho", 0.0)
    lam = math.exp(t[home]["att"] + t[away]["def"] + home_adv)
    mu = math.exp(t[away]["att"] + t[home]["def"])
    ph, pd, pa = _dc_probs_from_eg(lam, mu, rho)
    if ph is None:
        return 0.0, 0.0, 0.0, 0.0, 0.0
    return ph, pd, pa, lam, mu


# ── date parsing ──────────────────────────────────────────────────────────────
def parse_date(s):
    """Try DD/MM/YYYY then DD/MM/YY. Returns datetime or None."""
    if not s:
        return None
    for fmt in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(s.strip(), fmt)
        except ValueError:
            pass
    return None


# ── market de-vig ─────────────────────────────────────────────────────────────
def devig(oh, od, oa):
    """De-vig three odds; returns (ph, pd, pa) normalized or (1/3 each) on failure."""
    if not oh or not od or not oa:
        return 1 / 3, 1 / 3, 1 / 3
    try:
        ih, id_, ia = 1 / oh, 1 / od, 1 / oa
        tot = ih + id_ + ia
        if tot <= 0:
            return 1 / 3, 1 / 3, 1 / 3
        return ih / tot, id_ / tot, ia / tot
    except ZeroDivisionError:
        return 1 / 3, 1 / 3, 1 / 3


# ── form helpers ──────────────────────────────────────────────────────────────
def _empty_form():
    return {"w": 0, "d": 0, "l": 0, "gf": 0, "ga": 0, "dates": []}


def _form_features(form_dict):
    """Return (w5, d5, l5, gf5, ga5) from the running form dict."""
    return (
        form_dict["w"],
        form_dict["d"],
        form_dict["l"],
        form_dict["gf"],
        form_dict["ga"],
    )


def _update_form(form_dict, win, draw, lose, gf, ga, dt):
    """Update form dict in-place keeping only last 5 games."""
    form_dict["dates"].append((dt, win, draw, lose, gf, ga))
    # Keep last 5
    if len(form_dict["dates"]) > 5:
        form_dict["dates"] = form_dict["dates"][-5:]
    # Recompute counts from the window
    form_dict["w"] = sum(x[1] for x in form_dict["dates"])
    form_dict["d"] = sum(x[2] for x in form_dict["dates"])
    form_dict["l"] = sum(x[3] for x in form_dict["dates"])
    form_dict["gf"] = sum(x[4] for x in form_dict["dates"])
    form_dict["ga"] = sum(x[5] for x in form_dict["dates"])


# ── H2H helpers ───────────────────────────────────────────────────────────────
def _h2h_key(home, away):
    return tuple(sorted([home, away]))


# ── main data loader ──────────────────────────────────────────────────────────
def load_matches():
    """Load all valid matches from history.db, sorted by date."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.execute(
        """
        SELECT date, league, season, home, away,
               home_goals, away_goals, result,
               odds_h, odds_d, odds_a,
               odds_ch, odds_cd, odds_ca
        FROM matches
    """
    )
    rows = cur.fetchall()
    conn.close()

    matches = []
    skipped = 0
    for row in rows:
        r = dict(row)
        # Skip if result or goals missing
        if not r.get("result") or r["result"] not in ("H", "D", "A"):
            skipped += 1
            continue
        if r.get("home_goals") is None or r.get("away_goals") is None:
            skipped += 1
            continue

        dt = parse_date(r.get("date", ""))
        if dt is None:
            skipped += 1
            continue

        r["_dt"] = dt
        matches.append(r)

    print(f"Loaded {len(matches)} valid matches, skipped {skipped}.")
    matches.sort(key=lambda x: x["_dt"])
    return matches


# ── feature builder ───────────────────────────────────────────────────────────
def build_features(matches, dc_leagues):
    """
    Iterate matches chronologically.
    For each match, capture features BEFORE updating state.
    Returns X (np.ndarray), y (np.ndarray), seasons (list of str).
    """
    # Running form per team
    team_form = defaultdict(_empty_form)  # team -> form dict
    # H2H history: sorted(home,away) -> list of (dt, result_for_first_team)
    h2h_history = defaultdict(list)

    X_rows = []
    y_rows = []
    seasons = []

    for m in matches:
        home = m["home"]
        away = m["away"]
        league = m["league"]
        dt = m["_dt"]
        result = m["result"]
        hg = int(m["home_goals"])
        ag = int(m["away_goals"])
        season = str(m.get("season", ""))

        # ── DC features ──────────────────────────────────────────────────────
        dc_hp, dc_dp, dc_ap, dc_eh, dc_ea = dc_features(dc_leagues, league, home, away)

        # ── Market features (prefer closing, fall back to early) ─────────────
        oh = m.get("odds_ch") or m.get("odds_h")
        od = m.get("odds_cd") or m.get("odds_d")
        oa = m.get("odds_ca") or m.get("odds_a")
        mkt_h, mkt_d, mkt_a = devig(oh, od, oa)

        # ── Form features (snapshot BEFORE this match) ────────────────────────
        hf = team_form[home]
        af = team_form[away]
        h_w5, h_d5, h_l5, h_gf5, h_ga5 = _form_features(hf)
        a_w5, a_d5, a_l5, a_gf5, a_ga5 = _form_features(af)

        # ── H2H features (last 5 meetings before this match) ─────────────────
        key = _h2h_key(home, away)
        past = h2h_history[key][-5:]
        h2h_hw = sum(
            1 for (_, r_home, r_first) in past if r_first == home and r_home == "H"
        )
        h2h_aw = sum(
            1 for (_, r_home, r_first) in past if r_first == home and r_home == "A"
        )
        h2h_d = sum(1 for (_, r_home, r_first) in past if r_home == "D")

        row = [
            dc_hp,
            dc_dp,
            dc_ap,
            dc_eh,
            dc_ea,
            mkt_h,
            mkt_d,
            mkt_a,
            h_w5,
            h_d5,
            h_l5,
            h_gf5,
            h_ga5,
            a_w5,
            a_d5,
            a_l5,
            a_gf5,
            a_ga5,
            h2h_hw,
            h2h_d,
            h2h_aw,
        ]
        X_rows.append(row)
        y_rows.append({"H": 0, "D": 1, "A": 2}[result])
        seasons.append(season)

        # ── Update state AFTER capturing features ─────────────────────────────
        # Home team result
        h_win = 1 if result == "H" else 0
        h_draw = 1 if result == "D" else 0
        h_lose = 1 if result == "A" else 0
        _update_form(team_form[home], h_win, h_draw, h_lose, hg, ag, dt)

        # Away team result
        a_win = 1 if result == "A" else 0
        a_draw = 1 if result == "D" else 0
        a_lose = 1 if result == "H" else 0
        _update_form(team_form[away], a_win, a_draw, a_lose, ag, hg, dt)

        # H2H: store (dt, result_as_home_team_of_THIS_match, first_team_in_sorted_key)
        first_team = key[0]
        h2h_history[key].append((dt, result, home))

    X = np.array(X_rows, dtype=np.float32)
    y = np.array(y_rows, dtype=np.int32)
    return X, y, seasons


# ── ROI simulation ────────────────────────────────────────────────────────────
def roi_simulation(clf, X_test, y_test, matches_test):
    """
    Flat 1u on the model's top pick when EV > 0 vs de-vigged market.
    Returns (n_bets, roi_pct).
    """
    probs = clf.predict_proba(X_test)
    n_bets = 0
    profit = 0.0

    for i, (prob_row, true_label, m) in enumerate(zip(probs, y_test, matches_test)):
        # De-vigged market (use closing, fall back to early)
        oh = m.get("odds_ch") or m.get("odds_h")
        od = m.get("odds_cd") or m.get("odds_d")
        oa = m.get("odds_ca") or m.get("odds_a")
        mkt = devig(oh, od, oa)

        top = int(np.argmax(prob_row))
        model_prob = prob_row[top]
        mkt_prob = mkt[top]

        # EV = model_prob / mkt_prob - 1  (how much edge vs the market price)
        if mkt_prob <= 0:
            continue
        ev = model_prob / mkt_prob - 1
        if ev <= 0:
            continue

        # Use Pinnacle early odds for stake return calc
        odds_list = [oh, od, oa]
        odds = odds_list[top]
        if not odds or odds <= 1:
            continue

        n_bets += 1
        if true_label == top:
            profit += odds - 1
        else:
            profit -= 1

    roi = 100 * profit / n_bets if n_bets > 0 else 0.0
    return n_bets, roi


# ── main ──────────────────────────────────────────────────────────────────────
def main():
    print("=== LightGBM 1X2 trainer ===")

    # Load data
    print(f"\nLoading matches from {DB_PATH}")
    matches = load_matches()

    # Load DC model
    print(f"Loading DC model from {DC_PATH}")
    dc_leagues = load_dc()
    print(f"DC leagues available: {len(dc_leagues)}")

    # Build features
    print("\nBuilding feature matrix (chronological form tracking)...")
    X, y, seasons = build_features(matches, dc_leagues)
    print(f"Feature matrix shape: {X.shape}")
    print(f"Label distribution: H={np.sum(y==0)}, D={np.sum(y==1)}, A={np.sum(y==2)}")

    # Walk-forward split: train on all seasons except last, test on last
    unique_seasons = sorted(set(seasons))
    if len(unique_seasons) < 2:
        print("[warn] Only one season found — using 80/20 time split instead.")
        split = int(0.8 * len(X))
        train_idx = list(range(split))
        test_idx = list(range(split, len(X)))
        test_season = "last_20pct"
    else:
        last_season = unique_seasons[-1]
        test_season = last_season
        train_idx = [i for i, s in enumerate(seasons) if s != last_season]
        test_idx = [i for i, s in enumerate(seasons) if s == last_season]

    print(
        f"\nWalk-forward split: train on {len(train_idx)} rows, test on {len(test_idx)} rows (season '{test_season}')"
    )

    X_train, y_train = X[train_idx], y[train_idx]
    X_test, y_test = X[test_idx], y[test_idx]
    matches_test = [matches[i] for i in test_idx]

    # Train validation model
    print("\nTraining validation model...")
    clf_val = LGBMClassifier(
        n_estimators=500,
        learning_rate=0.05,
        max_depth=6,
        num_leaves=31,
        min_child_samples=20,
        subsample=0.8,
        colsample_bytree=0.8,
        reg_alpha=0.1,
        reg_lambda=0.1,
        objective="multiclass",
        num_class=3,
        random_state=42,
        n_jobs=-1,
        verbose=-1,
    )
    clf_val.fit(X_train, y_train)

    # Evaluate
    y_pred_train = clf_val.predict(X_train)
    y_pred_test = clf_val.predict(X_test)
    y_prob_test = clf_val.predict_proba(X_test)

    train_acc = accuracy_score(y_train, y_pred_train)
    test_acc = accuracy_score(y_test, y_pred_test)
    test_ll = log_loss(y_test, y_prob_test)

    print(f"\n--- Validation results (season '{test_season}') ---")
    print(f"  Train accuracy : {train_acc:.4f}")
    print(f"  Test  accuracy : {test_acc:.4f}")
    print(f"  Test  log-loss : {test_ll:.4f}")

    n_bets, roi = roi_simulation(clf_val, X_test, y_test, matches_test)
    print(f"  ROI simulation : {n_bets} bets, ROI={roi:+.1f}%")

    # Feature importances from validation model
    importances = clf_val.feature_importances_
    imp_dict = {name: float(imp) for name, imp in zip(FEATURE_NAMES, importances)}
    sorted_imp = sorted(imp_dict.items(), key=lambda x: -x[1])
    print("\n--- Top-10 features by importance ---")
    for name, imp in sorted_imp[:10]:
        print(f"  {name:25s}: {imp:.1f}")

    # Train final model on ALL data
    print("\nTraining final model on ALL data...")
    clf_final = LGBMClassifier(
        n_estimators=500,
        learning_rate=0.05,
        max_depth=6,
        num_leaves=31,
        min_child_samples=20,
        subsample=0.8,
        colsample_bytree=0.8,
        reg_alpha=0.1,
        reg_lambda=0.1,
        objective="multiclass",
        num_class=3,
        random_state=42,
        n_jobs=-1,
        verbose=-1,
    )
    clf_final.fit(X, y)
    final_acc = accuracy_score(y, clf_final.predict(X))
    print(f"  Final train accuracy (all data): {final_acc:.4f}")

    # Save model
    os.makedirs(os.path.dirname(OUT_PKL), exist_ok=True)
    joblib.dump(clf_final, OUT_PKL)
    print(f"\nSaved model to {OUT_PKL}")

    final_imp = {
        name: float(imp)
        for name, imp in zip(FEATURE_NAMES, clf_final.feature_importances_)
    }
    meta = {
        "features": FEATURE_NAMES,
        "importance": final_imp,
        "n_matches_total": len(matches),
        "train_size": len(train_idx),
        "test_size": len(test_idx),
        "test_season": test_season,
        "test_accuracy": round(test_acc, 6),
        "test_log_loss": round(test_ll, 6),
        "roi_n_bets": n_bets,
        "roi_pct": round(roi, 2),
    }
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)
    print(f"Saved feature metadata to {OUT_JSON}")
    print("\nDone.")


if __name__ == "__main__":
    main()
