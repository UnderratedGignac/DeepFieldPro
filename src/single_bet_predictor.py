import os
import sys
import sqlite3
import json
import math
import datetime
import logging
import pandas as pd
import pickle

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)
sys.path.insert(0, os.path.join(BASE_DIR, "src"))

from src.model_runner_v2 import (  # noqa: E402
    load_models_international,
    get_player_historical_stats,
    build_feature_vector,
    get_opponent_profile,
    detect_competition_type,
    compute_intl_ppda_norm,
    compute_intl_minutes_factor,
    poisson_prob_ge,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Feature column lists matching trained model input shapes
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
    "Age",
    "pos_encoded",
    "min_",
    "competition_type",
    "Performance_Sh",
    "Performance_Crs",
    "Performance_Int",
    "Performance_TklW",
    "sample_weight",
]


def compute_ev(FairProb_P: float, RawOdds_P: float) -> float:
    return (FairProb_P * (RawOdds_P - 1)) - (1 - FairProb_P)


def implied_fair_probs(DbPath_P, FixtureId_P, HomeTeam_P, AwayTeam_P):
    """
    Derive vig-free fair probabilities from scraped 1X2 odds for a given fixture.
    Returns (fair_home, fair_draw, fair_away, home_lam, away_lam).
    Falls back to league-average priors when no 1X2 odds are present.
    """
    conn = sqlite3.connect(DbPath_P)
    rows = conn.execute(
        "SELECT selection_name, raw_odds FROM market WHERE fixture_id = ? AND market_name = 'Match Result'",
        (FixtureId_P,)
    ).fetchall()
    conn.close()

    home_odds, draw_odds, away_odds = [], [], []
    for sel, odd in rows:
        s = sel.strip().lower()
        if s in ("x", "draw"):
            draw_odds.append(odd)
        elif s == HomeTeam_P.strip().lower():
            home_odds.append(odd)
        elif s == AwayTeam_P.strip().lower():
            away_odds.append(odd)

    if home_odds and draw_odds and away_odds:
        h_o = min(home_odds)
        d_o = min(draw_odds)
        a_o = min(away_odds)
        rh = 1.0 / h_o
        rd = 1.0 / d_o
        ra = 1.0 / a_o
        overround = rh + rd + ra
        fh = rh / overround
        fd = rd / overround
        fa = ra / overround
        total_lam = 2.55
        hl = total_lam * (fh + 0.5 * fd) / max(overround, 1.0)
        al = max(0.1, total_lam - hl)
        return fh, fd, fa, hl, al

    # League-average fallback
    return 0.44, 0.26, 0.30, 1.45, 1.10


def run_single_bet_predictor(BankrollSize_P: float):
    DbPath_V = os.path.join(BASE_DIR, "data", "odds_stream.db")
    if not os.path.exists(DbPath_V):
        logger.error("odds_stream.db not found. Did the scraper run?")
        return

    Conn_V = sqlite3.connect(DbPath_V)
    Cursor_V = Conn_V.cursor()
    Cursor_V.execute("""
        SELECT m.market_id, m.fixture_id, m.market_name, m.selection_name,
               m.raw_odds, m.prop_player, m.prop_type, m.prop_line,
               f.home_team, f.away_team, f.kickoff_time, f.league_id
        FROM market m
        JOIN fixture f ON m.fixture_id = f.fixture_id
    """)
    Rows_V = Cursor_V.fetchall()
    Conn_V.close()

    Models_V = load_models_international()

    # Load Platt scaler if available
    ScalerPath_V = os.path.join(BASE_DIR, "models", "platt_scaler_sot.pkl")
    PlattScaler_V = None
    if os.path.exists(ScalerPath_V):
        with open(ScalerPath_V, "rb") as F_V:
            PlattScaler_V = pickle.load(F_V)

    Bets_V = []

    for Row_V in Rows_V:
        (
            MarketId_V,
            FixtureId_V,
            MarketName_V,
            SelectionName_V,
            RawOdds_V,
            PlayerName_V,
            PropType_V,
            Line_V,
            HomeTeam_V,
            AwayTeam_V,
            KickoffTime_V,
            LeagueId_V,
        ) = Row_V

        # Skip junk odds range
        if RawOdds_V < 1.20 or RawOdds_V > 15.0:
            continue

        FairProb_V = None
        IsFallback_V = False
        Confidence_V = "HIGH"

        if PlayerName_V:
            # Detect competition type from league name
            CompetitionType_V = detect_competition_type(LeagueId_V)

            # Fetch real opponent profile from DB, not hardcoded
            OppProfile_V = get_opponent_profile(
                AwayTeam_V if HomeTeam_V else "", CompetitionType_V
            )

            Stats_V = get_player_historical_stats(
                PlayerName_V, competition_type=CompetitionType_V
            )
            if Stats_V is None:
                continue

            if isinstance(Stats_V, dict) and Stats_V.get("is_fallback"):
                IsFallback_V = True
                Confidence_V = "LOW"
            elif hasattr(Stats_V, "get") and Stats_V.get("is_fallback"):
                IsFallback_V = True
                Confidence_V = "LOW"

            Features_V = build_feature_vector(Stats_V, OppProfile_V, CompetitionType_V)

            # Build model input DataFrames with correct column names
            X_minutes = pd.DataFrame(  # noqa: F841
                [{k: Features_V[k] for k in MINUTES_FEATURES if k in Features_V}]
            )
            X_passes = pd.DataFrame(  # noqa: F841
                [{k: Features_V[k] for k in PASSES_FEATURES if k in Features_V}]
            )
            X_sot_new = pd.DataFrame(
                [{k: Features_V[k] for k in NEW_SOT_FEATURES if k in Features_V}]
            )

            # Route to correct SoT model based on competition type
            ModelKey_V = "sot_international" if CompetitionType_V == 1 else "sot_club"
            MinModel_V = Models_V.get(  # noqa: F841
                "sot_club"
            )  # use as proxy for minutes if no dedicated model

            if ModelKey_V not in Models_V:
                logger.warning(
                    f"Model {ModelKey_V} not loaded, skipping {PlayerName_V}"
                )
                continue

            SotMean_V = float(Models_V[ModelKey_V].predict(X_sot_new)[0])
            ExpectedMinutes_V = (
                float(
                    Models_V.get("sot_club", Models_V[ModelKey_V]).predict(X_sot_new)[0]
                )
                * 45.0
            )
            ExpectedMinutes_V = max(
                45.0, min(90.0, ExpectedMinutes_V)
            )  # clamp to sensible range

            # Compute normalized lambda
            IntlPpdaNorm_V = compute_intl_ppda_norm(
                OppProfile_V["ppda"], CompetitionType_V
            )
            IntlMinutesFactor_V = compute_intl_minutes_factor(CompetitionType_V)

            LamSot_V = max(
                0.001,
                (SotMean_V / 90.0)
                * ExpectedMinutes_V
                * IntlPpdaNorm_V
                * IntlMinutesFactor_V,
            )

            # Use prop line from scraped data, default to 0.5
            PropLine_V = float(Line_V) if Line_V is not None else 0.5
            Threshold_V = math.floor(PropLine_V)

            if "over" in SelectionName_V.lower():
                RawProb_V = poisson_prob_ge(LamSot_V, Threshold_V + 1)
            else:
                # Under: P(X <= threshold)
                RawProb_V = 1.0 - poisson_prob_ge(LamSot_V, Threshold_V + 1)

            # Apply Platt scaling if available
            if PlattScaler_V:
                FairProb_V = float(PlattScaler_V.predict_proba([[RawProb_V]])[0][1])
            else:
                FairProb_V = RawProb_V

        else:
            # Match result / BTTS / Over-Under
            # Use MARKET-IMPLIED probabilities (vig-free) from scraped odds
            FairHomeP_V, FairDrawP_V, FairAwayP_V, HomeGoalLam_V, AwayGoalLam_V = \
                implied_fair_probs(DbPath_V, FixtureId_V, HomeTeam_V, AwayTeam_V)

            SelectionLower_V = SelectionName_V.strip().lower()

            if SelectionLower_V == HomeTeam_V.strip().lower():
                FairProb_V = FairHomeP_V
            elif SelectionLower_V in ("x", "draw"):
                FairProb_V = FairDrawP_V
            elif SelectionLower_V == AwayTeam_V.strip().lower():
                FairProb_V = FairAwayP_V
            elif "both teams to score - yes" in SelectionLower_V:
                FairProb_V = (1 - math.exp(-HomeGoalLam_V)) * (1 - math.exp(-AwayGoalLam_V))
            elif "both teams to score - no" in SelectionLower_V:
                FairProb_V = 1.0 - (1 - math.exp(-HomeGoalLam_V)) * (1 - math.exp(-AwayGoalLam_V))
            elif "total over" in SelectionLower_V:
                FairProb_V = poisson_prob_ge(HomeGoalLam_V + AwayGoalLam_V, 3)
            elif "total under" in SelectionLower_V:
                FairProb_V = 1.0 - poisson_prob_ge(HomeGoalLam_V + AwayGoalLam_V, 3)
            else:
                FairProb_V = 0.50  # Unknown market, neutral prior

        if FairProb_V is None:
            continue

        Ev_V = compute_ev(FairProb_V, RawOdds_V)

        # EV filter
        if Ev_V >= 0.05 and FairProb_V >= 0.40:
            Status_V = "BATCH"
        elif 0.02 <= Ev_V < 0.05:
            Status_V = "MONITOR"
        else:
            Status_V = "SKIP"

        # Quarter Kelly sizing with hard caps
        FullKelly_V = (
            (FairProb_V * RawOdds_V - 1) / (RawOdds_V - 1) if RawOdds_V > 1 else 0
        )
        KellyStake_V = (FullKelly_V / 4.0) * BankrollSize_P

        MaxStake_V = BankrollSize_P * 0.02 if IsFallback_V else BankrollSize_P * 0.05
        KellyStake_V = max(0.0, min(KellyStake_V, MaxStake_V))

        # Only stake on BATCH
        if Status_V != "BATCH":
            KellyStake_V = 0.0

        StakePct_V = (KellyStake_V / BankrollSize_P) * 100 if BankrollSize_P > 0 else 0

        Bets_V.append(
            {
                "fixture": f"{HomeTeam_V} vs {AwayTeam_V}",
                "kickoff": KickoffTime_V,
                "market": MarketName_V,
                "selection": SelectionName_V,
                "fair_prob": round(FairProb_V, 3),
                "raw_odds": RawOdds_V,
                "ev": round(Ev_V, 3),
                "kelly_stake": round(KellyStake_V, 2),
                "stake_pct": round(StakePct_V, 2),
                "confidence": Confidence_V,
                "is_fallback": IsFallback_V,
                "status": Status_V,
            }
        )

    Bets_V.sort(key=lambda x: x["ev"], reverse=True)
    for Idx_V, B_V in enumerate(Bets_V):
        B_V["rank"] = Idx_V + 1

    OutputData_V = {
        "generated_at": datetime.datetime.now(datetime.UTC).isoformat(),
        "bankroll": BankrollSize_P,
        "bets": Bets_V,
    }

    OutPath_V = os.path.join(BASE_DIR, "data", "todays_single_bets.json")
    with open(OutPath_V, "w") as F_V:
        json.dump(OutputData_V, F_V, indent=4)

    logger.info(f"Generated single predictions for {len(Bets_V)} markets.")


if __name__ == "__main__":
    BankrollArg_V = float(sys.argv[1]) if len(sys.argv) > 1 else 100.0
    run_single_bet_predictor(BankrollArg_V)
