import os
import sys
import json
import math
import logging

# Add src root to pythonpath
sys.path.insert(0, os.path.dirname(__file__))

from model_runner import (
    load_models,
    get_player_historical_stats,
    build_feature_vector,
    poisson_prob_ge,
)

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


def generate_predictions():
    logger.info("Loading predictive models...")
    models = load_models()

    # Games and key players to evaluate
    games = [
        {
            "fixture_id": "HTI_NZL_2026",
            "matchup": "Haiti vs New Zealand",
            "competition_type": 1,
            "opp_ppda": 18.2,
            "opp_possession_allowed": 60.0,
            "players": ["Chris Wood", "Liberato Cacace", "Frantzdy Pierrot"],
        },
        {
            "fixture_id": "PHI_GUM_2026",
            "matchup": "Philippines vs Guam",
            "competition_type": 1,
            "opp_ppda": 22.0,
            "opp_possession_allowed": 70.0,
            "players": ["Neil Etheridge", "Gerrit Holtmann"],
        },
        {
            "fixture_id": "KGZ_KEN_2026",
            "matchup": "Kyrgyzstan vs Kenya",
            "competition_type": 1,
            "opp_ppda": 14.0,
            "opp_possession_allowed": 50.0,
            "players": ["Michael Olunga"],
        },
        {
            "fixture_id": "DEN_DRC_2026",
            "matchup": "Denmark vs DR Congo",
            "competition_type": 1,
            "opp_ppda": 10.5,
            "opp_possession_allowed": 45.0,
            "players": ["Christian Eriksen", "Rasmus Hojlund", "Yoane Wissa"],
        },
        {
            "fixture_id": "ALB_ISR_2026",
            "matchup": "Albania vs Israel",
            "competition_type": 1,
            "opp_ppda": 12.0,
            "opp_possession_allowed": 50.0,
            "players": ["Armando Broja", "Manor Solomon"],
        },
        {
            "fixture_id": "POL_NGA_2026",
            "matchup": "Poland vs Nigeria",
            "competition_type": 1,
            "opp_ppda": 8.5,
            "opp_possession_allowed": 42.0,
            "players": [
                "Robert Lewandowski",
                "Piotr Zielinski",
                "Victor Osimhen",
                "Ademola Lookman",
            ],
        },
        {
            "fixture_id": "NED_ALG_2026",
            "matchup": "Netherlands vs Algeria",
            "competition_type": 1,
            "opp_ppda": 11.2,
            "opp_possession_allowed": 48.0,
            "players": ["Virgil van Dijk", "Cody Gakpo", "Riyad Mahrez"],
        },
        {
            "fixture_id": "LUX_ITA_2026",
            "matchup": "Luxembourg vs Italy",
            "competition_type": 1,
            "opp_ppda": 25.0,
            "opp_possession_allowed": 75.0,
            "players": ["Federico Chiesa", "Nicolo Barella", "Gianluigi Donnarumma"],
        },
    ]

    predictions = []

    for game in games:
        logger.info(f"\nAnalyzing: {game['matchup']}")

        game_preds = {
            "fixture_id": game["fixture_id"],
            "matchup": game["matchup"],
            "player_projections": [],
        }

        opp_profile = {
            "ppda": game.get("opp_ppda", 12.0),
            "opp_possession_allowed": game.get("opp_possession_allowed", 50.0),
        }

        CompetitionType_V = game.get("competition_type", 0)

        for player_name in game["players"]:
            # Fetch historical stats with _P parameters
            stats = get_player_historical_stats(
                player_name,
                FallbackPosition_P="FW",
                FallbackLeague_P="ENG-Premier League",
            )
            if stats is None:
                logger.warning(
                    f"  [MISSING] {player_name} not found and fallback failed."
                )
                continue

            IsFallback_V = stats.get("is_fallback", False)

            features = build_feature_vector(stats, opp_profile)
            import pandas as pd

            MINUTES_FEATURES = [
                "Age",
                "Starts",
                "Percentage of Minutes Played",
                "Mn/Start",
                "Mn/MP",
                "PPM",
                "ppda",
                "opp_possession_allowed",
                "sample_weight",
            ]
            PASSES_FEATURES = [
                "Age",
                "Position_encoded",
                "Minutes Played",
                "Mn/Start",
                "Percentage of Minutes Played",
                "Crs",
                "Interceptions",
                "Tackles Won",
                "ppda",
                "opp_possession_allowed",
                "sample_weight",
            ]
            NEW_SOT_FEATURES = [
                "age_",
                "competition_type",
                "min_",
                "pos_encoded",
                "Performance_Sh",
                "Performance_Crs",
                "Performance_Int",
                "Performance_TklW",
                "sample_weight",
            ]

            X_minutes = pd.DataFrame([features], columns=MINUTES_FEATURES)
            X_passes = pd.DataFrame([features], columns=PASSES_FEATURES)
            features["competition_type"] = CompetitionType_V
            X_sot_new = pd.DataFrame([features], columns=NEW_SOT_FEATURES)

            try:
                MinP50_V = float(models["min_p50"].predict(X_minutes)[0])
                GoalsRate_V = float(models["goals_mean"].predict(X_passes)[0])

                # TASK 1: Select SoT model based on competition type
                if CompetitionType_V == 1:
                    if "sot_intl" in models:
                        SotMean_V = float(models["sot_intl"].predict(X_sot_new)[0])
                    else:
                        SotMean_V = float(models["sot_p50"].predict(X_passes)[0])
                    IntlPpdaNorm_V = opp_profile["ppda"] / 9.5
                    IntlMinutesFactor_V = 0.88
                else:
                    if "sot_club" in models:
                        SotMean_V = float(models["sot_club"].predict(X_sot_new)[0])
                    else:
                        SotMean_V = float(models["sot_p50"].predict(X_passes)[0])
                    IntlPpdaNorm_V = opp_profile["ppda"] / 12.0
                    IntlMinutesFactor_V = 1.0

                PassP10_V = float(models["pass_p10"].predict(X_passes)[0])
                PassP50_V = float(models["pass_p50"].predict(X_passes)[0])
                PassP90_V = float(models["pass_p90"].predict(X_passes)[0])
                PassMean_V = (PassP10_V + 4 * PassP50_V + PassP90_V) / 6.0

                ShotsP10_V = float(models["shots_p10"].predict(X_passes)[0])
                ShotsP50_V = float(models["shots_p50"].predict(X_passes)[0])
                ShotsP90_V = float(models["shots_p90"].predict(X_passes)[0])
                ShotsMean_V = (ShotsP10_V + 4 * ShotsP50_V + ShotsP90_V) / 6.0

                ExpectedMinutes_V = MinP50_V * IntlMinutesFactor_V

                LamGoals_V = max(0.001, (GoalsRate_V * ExpectedMinutes_V / 90.0))
                LamSot_V = max(
                    0.001, (SotMean_V / 90.0) * ExpectedMinutes_V * IntlPpdaNorm_V
                )
                LamPasses_V = max(0.001, (PassMean_V / 90.0) * ExpectedMinutes_V)

                logger.info(
                    f"    [DEBUG] {player_name}: SotMean_V={SotMean_V:.3f}, ExpectedMinutes_V={ExpectedMinutes_V:.1f} => LamSot_V={LamSot_V:.3f}"
                )

                AnytimeGoal_V = 1.0 - math.exp(-LamGoals_V)

                player_proj = {
                    "player": player_name,
                    "is_fallback": bool(IsFallback_V),
                    "expected_minutes": round(ExpectedMinutes_V, 1),
                    "anytime_goal_prob": round(AnytimeGoal_V, 3),
                    "expected_shots": round(ShotsMean_V, 2),
                    "expected_sot": round(SotMean_V, 2),
                    "expected_passes": round(PassMean_V, 1),
                }

                # ISSUE 4 FIX: Evaluate ALL markets concurrently instead of short-circuiting
                candidate_markets = []

                # Market: Anytime Goalscorer
                candidate_markets.append(
                    {
                        "market": "player_goal_anytime",
                        "line": None,
                        "fair_prob": AnytimeGoal_V,
                    }
                )

                # Market: Shots on Target Over 0.5
                RawProb_V = poisson_prob_ge(LamSot_V, 1)

                # TASK 3: Platt Scaling
                import pickle

                scaler_path = os.path.join(
                    os.path.dirname(__file__), "..", "models", "platt_scaler_sot.pkl"
                )
                if os.path.exists(scaler_path):
                    with open(scaler_path, "rb") as f:
                        platt_scaler = pickle.load(f)
                    CalibratedProb_V = float(
                        platt_scaler.predict_proba([[RawProb_V]])[0][1]
                    )
                else:
                    CalibratedProb_V = RawProb_V

                if not (0.10 <= CalibratedProb_V <= 0.90):
                    SotStatus_V = "LOW_CONFIDENCE"
                else:
                    SotStatus_V = "OK"

                candidate_markets.append(
                    {
                        "market": "player_shots_on_target_over",
                        "line": 0.5,
                        "fair_prob": CalibratedProb_V,
                        "raw_prob": RawProb_V,
                        "status_flag": SotStatus_V,
                    }
                )

                # Market: Passes Over
                if PassMean_V > 20:
                    PassLine_V = math.floor(PassMean_V) + 0.5
                    PassFairProb_V = poisson_prob_ge(LamPasses_V, int(PassLine_V + 0.5))
                    candidate_markets.append(
                        {
                            "market": "player_passes_over",
                            "line": PassLine_V,
                            "fair_prob": PassFairProb_V,
                        }
                    )

                # Select the market with the highest true Fair Probability
                BestMarket_V = max(candidate_markets, key=lambda x: x["fair_prob"])

                # ISSUE 3 FIX: Remove simulated 10% odds multiplier. Output Target Odds Threshold.
                # Threshold = (1 / fair_prob) + 5% minimum edge margin
                TargetOdds_V = (
                    round((1.0 / BestMarket_V["fair_prob"]) * 1.05, 2)
                    if BestMarket_V["fair_prob"] > 0.05
                    else None
                )

                if (
                    TargetOdds_V
                    and BestMarket_V.get("status_flag", "OK") != "LOW_CONFIDENCE"
                ):
                    player_proj["top_ev_play"] = {
                        "market": BestMarket_V["market"],
                        "line": BestMarket_V["line"],
                        "fair_prob": round(BestMarket_V["fair_prob"], 3),
                        "raw_prob": round(
                            BestMarket_V.get("raw_prob", BestMarket_V["fair_prob"]), 3
                        ),
                        "target_odds_threshold": TargetOdds_V,
                        "status": "WAITING_FOR_LIVE_ODDS",
                    }
                    logger.info(
                        f"  [PROJECTION] {player_name}: {BestMarket_V['market']} (Target Odds > {TargetOdds_V})"
                    )
                else:
                    status = (
                        "LOW_CONFIDENCE"
                        if BestMarket_V.get("status_flag") == "LOW_CONFIDENCE"
                        else "NO_VIABLE_MARKETS"
                    )
                    player_proj["top_ev_play"] = {
                        "market": BestMarket_V["market"],
                        "line": BestMarket_V["line"],
                        "fair_prob": round(BestMarket_V["fair_prob"], 3),
                        "raw_prob": round(
                            BestMarket_V.get("raw_prob", BestMarket_V["fair_prob"]), 3
                        ),
                        "status": status,
                    }
                    logger.info(
                        f"  [PROJECTION] {player_name}: {BestMarket_V['market']} ({status})"
                    )

                game_preds["player_projections"].append(player_proj)
            except Exception as e:
                logger.error(f"  [ERROR] Predicting for {player_name}: {e}")

        predictions.append(game_preds)

    out_path = os.path.join(
        os.path.dirname(__file__), "..", "data", "tomorrow_predictions_real.json"
    )
    with open(out_path, "w") as f:
        json.dump(predictions, f, indent=2)

    logger.info(f"\nReal system predictions written to {out_path}")


if __name__ == "__main__":
    generate_predictions()
