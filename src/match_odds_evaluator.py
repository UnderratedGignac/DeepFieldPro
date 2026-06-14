"""
DeepFieldPro — Match Odds Evaluator
====================================
Aggregates Player xG from our models into Team xG,
calculates match outcome probabilities using Poisson distributions,
and compares them against live API-Football match odds to find +EV bets.
"""

import pandas as pd
import sys
import io
from scipy.stats import poisson

sys.stdout = io.TextIOWrapper(
    sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True
)

from engine_predictor import run_predictions  # noqa: E402
from engine_bettor import expected_value, fetch_bookmaker_odds  # noqa: E402


def aggregate_team_xg(predictions_df: pd.DataFrame) -> dict:
    """Sum player xG by team for each match, using only the top 11 players by expected minutes to simulate a starting XI."""
    match_xg = {}
    for match_str, grp in predictions_df.groupby("match"):
        match_xg[match_str] = {}
        for team, t_grp in grp.groupby("team"):
            # Sort by expected minutes to get the likely starting XI + subs, but scaling to 11 full matches
            # A better proxy for team xG: take top 14 players (starters + subs) whose xMin > 30, and scale down to 10 outfield players.
            # But simplest is just sum top 10 outfield players by xG
            top_10 = t_grp.sort_values("exp_Gls", ascending=False).head(10)
            team_xg = top_10["exp_Gls"].sum()
            match_xg[match_str][team] = team_xg
    return match_xg


def compute_match_probs(home_xg: float, away_xg: float):
    """Compute 1X2 and O/U 2.5 probabilities using independent Poisson."""
    max_goals = 10
    home_probs = [poisson.pmf(i, max(0.01, home_xg)) for i in range(max_goals)]
    away_probs = [poisson.pmf(i, max(0.01, away_xg)) for i in range(max_goals)]

    p_home_win = 0.0
    p_draw = 0.0
    p_away_win = 0.0
    p_over_2_5 = 0.0
    p_btts_yes = 0.0

    for h in range(max_goals):
        for a in range(max_goals):
            prob = home_probs[h] * away_probs[a]

            if h > a:
                p_home_win += prob
            elif h == a:
                p_draw += prob
            else:
                p_away_win += prob

            if h + a > 2.5:
                p_over_2_5 += prob

            if h > 0 and a > 0:
                p_btts_yes += prob

    p_under_2_5 = 1.0 - p_over_2_5
    p_btts_no = 1.0 - p_btts_yes

    return {
        "Home Win": p_home_win,
        "Draw": p_draw,
        "Away Win": p_away_win,
        "Over 2.5": p_over_2_5,
        "Under 2.5": p_under_2_5,
        "BTTS Yes": p_btts_yes,
        "BTTS No": p_btts_no,
        "Home/Draw": p_home_win + p_draw,
        "Home/Away": p_home_win + p_away_win,
        "Draw/Away": p_draw + p_away_win,
    }


def find_match_value_bets():
    preds = run_predictions()
    if preds.empty:
        print("No predictions available.")
        return

    fixtures = preds[["fixture_id", "match", "team", "league"]].drop_duplicates()
    fids = fixtures["fixture_id"].dropna().unique().tolist()

    print("\n[1] Aggregating Player xG into Team xG...")
    match_xg = aggregate_team_xg(preds)

    print(f"\n[2] Fetching live match odds for {len(fids)} fixtures...")
    odds_data = fetch_bookmaker_odds([int(f) for f in fids])

    value_bets = []

    for fid in fids:
        fix_info = fixtures[fixtures["fixture_id"] == fid].iloc[0]
        match_str = fix_info["match"]
        teams = list(match_xg.get(match_str, {}).keys())
        if len(teams) != 2:
            continue

        # We need to know who is home and away from the match string
        home_team = match_str.split(" vs ")[0]
        away_team = match_str.split(" vs ")[1]

        home_xg = match_xg[match_str].get(home_team, 0)
        away_xg = match_xg[match_str].get(away_team, 0)

        print(f"\n  {match_str} | xG: {home_xg:.2f} - {away_xg:.2f}")

        probs = compute_match_probs(home_xg, away_xg)

        fix_odds = odds_data.get(fid, {})

        # 1X2 Market
        if "Match Winner" in fix_odds:
            mw = fix_odds["Match Winner"]
            lines = [
                ("Home Win", mw.get("Home", 0)),
                ("Draw", mw.get("Draw", 0)),
                ("Away Win", mw.get("Away", 0)),
            ]
            for selection, odd in lines:
                if odd > 1.0:
                    model_p = probs[selection]
                    ev = expected_value(model_p, odd)
                    if ev > 0.02:  # 2% EV threshold
                        value_bets.append(
                            {
                                "Match": match_str,
                                "Market": "Match Winner",
                                "Selection": selection,
                                "Odds": odd,
                                "Model Prob": f"{model_p*100:.1f}%",
                                "EV": f"{ev*100:.1f}%",
                            }
                        )

        # O/U Market
        if "Goals Over/Under" in fix_odds:
            ou = fix_odds["Goals Over/Under"]
            lines = [
                ("Over 2.5", ou.get("Over 2.5", 0)),
                ("Under 2.5", ou.get("Under 2.5", 0)),
            ]
            for selection, odd in lines:
                if odd > 1.0:
                    model_p = probs[selection]
                    ev = expected_value(model_p, odd)
                    if ev > 0.02:
                        value_bets.append(
                            {
                                "Match": match_str,
                                "Market": "Goals Over/Under",
                                "Selection": selection,
                                "Odds": odd,
                                "Model Prob": f"{model_p*100:.1f}%",
                                "EV": f"{ev*100:.1f}%",
                            }
                        )

        # BTTS Market
        if "Both Teams Score" in fix_odds:
            btts = fix_odds["Both Teams Score"]
            lines = [("BTTS Yes", btts.get("Yes", 0)), ("BTTS No", btts.get("No", 0))]
            for selection, odd in lines:
                if odd > 1.0:
                    model_p = probs[selection]
                    ev = expected_value(model_p, odd)
                    if ev > 0.02:
                        value_bets.append(
                            {
                                "Match": match_str,
                                "Market": "Both Teams To Score",
                                "Selection": selection.replace("BTTS ", ""),
                                "Odds": odd,
                                "Model Prob": f"{model_p*100:.1f}%",
                                "EV": f"{ev*100:.1f}%",
                            }
                        )

        # Double Chance
        if "Double Chance" in fix_odds:
            dc = fix_odds["Double Chance"]
            lines = [
                ("Home/Draw", dc.get("Home/Draw", 0)),
                ("Home/Away", dc.get("Home/Away", 0)),
                ("Draw/Away", dc.get("Draw/Away", 0)),
            ]
            for selection, odd in lines:
                if odd > 1.0:
                    model_p = probs[selection]
                    ev = expected_value(model_p, odd)
                    if ev > 0.02:
                        value_bets.append(
                            {
                                "Match": match_str,
                                "Market": "Double Chance",
                                "Selection": selection,
                                "Odds": odd,
                                "Model Prob": f"{model_p*100:.1f}%",
                                "EV": f"{ev*100:.1f}%",
                            }
                        )

    print(f"\n{'='*65}")
    print("BEST BETS TO PLACE TO MAKE MONEY (Match Odds)")
    print(f"{'='*65}")
    if not value_bets:
        print("No +EV match bets found. Bookmakers have sharp lines today.")
    else:
        df = pd.DataFrame(value_bets).sort_values("EV", ascending=False)
        print(df.to_string(index=False))


if __name__ == "__main__":
    find_match_value_bets()
