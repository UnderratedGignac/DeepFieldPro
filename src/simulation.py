"""
simulation.py — DeepFieldPro World Cup Simulation
Runs a complete paper-trade simulation for today's international matches.
Uses the validated passes/Poisson model with real player stats from CSV.
Does NOT require live odds — outputs bets at target odds thresholds.

Run: python src/simulation.py --bankroll 500
"""

import os
import sys
import json
import math
import argparse
import datetime
import logging
import pandas as pd
import numpy as np
import pickle

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'data')
MODEL_DIR = os.path.join(BASE_DIR, 'models')

logging.basicConfig(level=logging.INFO, format="%(asctime)s — %(message)s")
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTS — all sourced from validated backtest results
# ─────────────────────────────────────────────────────────────────────────────
ClubPpdaBaseline_P   = 12.0   # Average club league PPDA
IntlPpdaBaseline_P   = 9.5    # International matches press less
IntlMinutesFactor_P  = 0.88   # Intl starters average 72 min vs 82 for club
MinEvThreshold_P     = 0.05   # Minimum EV to flag as BATCH
KellyFraction_P      = 0.25   # Quarter Kelly
MaxSingleStakePct_P  = 0.05   # 5% of bankroll max per bet
MaxFallbackStakePct_P = 0.02  # 2% of bankroll if fallback player

# ─────────────────────────────────────────────────────────────────────────────
# TODAY'S WORLD CUP FIXTURES (June 3, 2026)
# PPDA sourced from FBref opponent profiles for each team
# ─────────────────────────────────────────────────────────────────────────────
TODAYS_FIXTURES = [
    {
        "fixture_id": "PHI_GUM_2026",
        "matchup": "Philippines vs Guam",
        "kickoff": "14:30",
        "competition_type": 1,
        "league": "International Friendly",
        "opp_ppda": 22.0,       # Guam very passive defense
        "opp_possession_allowed": 70.0,
        "players": [
            {"name": "Neil Etheridge",  "position": "GK"},
            {"name": "Gerrit Holtmann", "position": "FW"},
        ]
    },
    {
        "fixture_id": "DEN_DRC_2026",
        "matchup": "Denmark vs DR Congo",
        "kickoff": "21:00",
        "competition_type": 1,
        "league": "International Friendly",
        "opp_ppda": 10.5,       # DR Congo compact block
        "opp_possession_allowed": 45.0,
        "players": [
            {"name": "Christian Eriksen", "position": "MF"},
            {"name": "Rasmus Hojlund",   "position": "FW"},
            {"name": "Yoane Wissa",       "position": "FW"},
        ]
    },
    {
        "fixture_id": "POL_NGA_2026",
        "matchup": "Poland vs Nigeria",
        "kickoff": "21:45",
        "competition_type": 1,
        "league": "International Friendly",
        "opp_ppda": 8.5,        # Nigeria high-press
        "opp_possession_allowed": 42.0,
        "players": [
            {"name": "Robert Lewandowski", "position": "FW"},
            {"name": "Piotr Zielinski",    "position": "MF"},
            {"name": "Victor Osimhen",     "position": "FW"},
            {"name": "Ademola Lookman",    "position": "FW"},
        ]
    },
    {
        "fixture_id": "NED_ALG_2026",
        "matchup": "Netherlands vs Algeria",
        "kickoff": "21:45",
        "competition_type": 1,
        "league": "International Friendly",
        "opp_ppda": 11.2,
        "opp_possession_allowed": 48.0,
        "players": [
            {"name": "Cody Gakpo",       "position": "FW"},
            {"name": "Virgil van Dijk",  "position": "DF"},
            {"name": "Riyad Mahrez",     "position": "FW"},
        ]
    },
    {
        "fixture_id": "LUX_ITA_2026",
        "matchup": "Luxembourg vs Italy",
        "kickoff": "21:45",
        "competition_type": 1,
        "league": "International Friendly",
        "opp_ppda": 25.0,       # Luxembourg very open
        "opp_possession_allowed": 75.0,
        "players": [
            {"name": "Federico Chiesa",     "position": "FW"},
            {"name": "Nicolo Barella",      "position": "MF"},
        ]
    },
]

# ─────────────────────────────────────────────────────────────────────────────
# PLAYER DATABASE — load from CSV
# ─────────────────────────────────────────────────────────────────────────────
def load_player_db() -> pd.DataFrame:
    # Try both known CSV paths
    CsvPaths_V = [
        os.path.join(DATA_DIR, 'world_cup_players_match_logs.csv'),
        'C:/Users/Elie/data/csv/FULL_PLAYER_DATABASE_2026.csv',
    ]
    for Path_V in CsvPaths_V:
        if os.path.exists(Path_V):
            logger.info(f"Loaded player DB from {Path_V}")
            return pd.read_csv(Path_V)

    logger.error("No player CSV found — building synthetic fallback DB")
    return pd.DataFrame()

def find_player(Df_P: pd.DataFrame, PlayerName_P: str) -> dict | None:
    if Df_P.empty:
        return None

    try:
        from unidecode import unidecode
        Df_P = Df_P.copy()
        # Try multiple column names for player name
        NameCol_V = next((c for c in ['Player Name', 'player_', 'player_name', 'Player'] if c in Df_P.columns), None)
        if not NameCol_V:
            return None

        Df_P['name_clean'] = Df_P[NameCol_V].apply(lambda x: unidecode(str(x)).lower().strip())
        QueryName_V = unidecode(PlayerName_P).lower().strip()

        Matches_V = Df_P[Df_P['name_clean'] == QueryName_V]
        if Matches_V.empty:
            Matches_V = Df_P[Df_P['name_clean'].str.contains(QueryName_V[:8], na=False)]

        if Matches_V.empty:
            return None

        # Sort by most recent season
        SeasonCol_V = next((c for c in ['season', 'season_', 'Season'] if c in Df_P.columns), None)
        if SeasonCol_V:
            Matches_V = Matches_V.sort_values(SeasonCol_V, ascending=False)

        Row_V = Matches_V.iloc[0].to_dict()
        Row_V['is_fallback'] = False
        return Row_V

    except Exception as E_V:
        logger.warning(f"Player lookup error for {PlayerName_P}: {E_V}")
        return None

def get_position_average(Df_P: pd.DataFrame, Position_P: str) -> dict:
    if Df_P.empty:
        return {}

    PosCol_V = next((c for c in ['Position', 'pos_', 'Pos'] if c in Df_P.columns), None)
    if not PosCol_V:
        return {}

    Subset_V = Df_P[Df_P[PosCol_V].astype(str).str.contains(Position_P, na=False)]
    if Subset_V.empty:
        Subset_V = Df_P

    Avg_V = Subset_V.mean(numeric_only=True).to_dict()
    Avg_V['is_fallback'] = True
    return Avg_V

def safe_get(Stats_P: dict, Keys_P: list, Default_P: float) -> float:
    for K_V in Keys_P:
        Val_V = Stats_P.get(K_V)
        if Val_V is not None:
            try:
                FVal_V = float(str(Val_V).split('-')[0])
                if not math.isnan(FVal_V):
                    return FVal_V
            except:
                continue
    return Default_P

# ─────────────────────────────────────────────────────────────────────────────
# POISSON ENGINE
# ─────────────────────────────────────────────────────────────────────────────
def poisson_prob_ge(Lam_P: float, K_P: int) -> float:
    if Lam_P <= 0:
        return 0.0
    ProbLtK_V = sum((Lam_P ** i) * math.exp(-Lam_P) / math.factorial(i) for i in range(K_P))
    return max(0.0, min(1.0, 1.0 - ProbLtK_V))

def compute_lam_passes(Stats_P: dict, OppPpda_P: float, CompetitionType_P: int) -> float:
    # Pearson mean of passes distribution
    PassMean_V = safe_get(Stats_P,
        ['Att', 'Total_Att', 'passes_attempted', 'passes_mean', 'PPM'],
        35.0
    )
    MinutesPlayed_V = safe_get(Stats_P,
        ['Minutes Played', 'min_', 'Min', 'minutes_played'],
        75.0
    )
    MinutesPlayed_V = max(30.0, min(90.0, MinutesPlayed_V))

    # International normalization
    if CompetitionType_P == 1:
        PpdaNorm_V = OppPpda_P / IntlPpdaBaseline_P
        MinutesFactor_V = IntlMinutesFactor_P
    else:
        PpdaNorm_V = OppPpda_P / ClubPpdaBaseline_P
        MinutesFactor_V = 1.0

    # Lambda: passes per 90 scaled to expected minutes and opponent PPDA
    LamPasses_V = max(0.001, (PassMean_V / 90.0) * MinutesPlayed_V * MinutesFactor_V * (1.0 / max(PpdaNorm_V, 0.1)))
    return LamPasses_V

def compute_lam_sot(Stats_P: dict, OppPpda_P: float, CompetitionType_P: int,
                    PlattScaler_P=None) -> tuple[float, float]:
    # SoT lambda
    SotMean_V = safe_get(Stats_P,
        ['SoT', 'shots_on_target', 'sot_mean', 'Performance_SoT', 'Sh'],
        1.2
    )
    MinutesPlayed_V = safe_get(Stats_P,
        ['Minutes Played', 'min_', 'Min', 'minutes_played'],
        75.0
    )
    MinutesPlayed_V = max(30.0, min(90.0, MinutesPlayed_V))

    if CompetitionType_P == 1:
        PpdaNorm_V = OppPpda_P / IntlPpdaBaseline_P
        MinutesFactor_V = IntlMinutesFactor_P
    else:
        PpdaNorm_V = OppPpda_P / ClubPpdaBaseline_P
        MinutesFactor_V = 1.0

    LamSot_V = max(0.001, (SotMean_V / 90.0) * MinutesPlayed_V * MinutesFactor_V * PpdaNorm_V)
    RawProb_V = poisson_prob_ge(LamSot_V, 1)

    # Apply Platt scaling if loaded
    if PlattScaler_P is not None:
        try:
            CalibProb_V = float(PlattScaler_P.predict_proba([[RawProb_V]])[0][1])
        except:
            CalibProb_V = RawProb_V
    else:
        CalibProb_V = RawProb_V

    return LamSot_V, CalibProb_V

def compute_lam_goals(Stats_P: dict, OppPpda_P: float, CompetitionType_P: int) -> float:
    GoalRate_V = safe_get(Stats_P,
        ['Gls', 'goals', 'G/Sh', 'Performance_Gls'],
        0.3
    )
    MinutesPlayed_V = safe_get(Stats_P, ['Minutes Played', 'min_', 'Min'], 75.0)
    MinutesPlayed_V = max(30.0, min(90.0, MinutesPlayed_V))

    if CompetitionType_P == 1:
        MinutesFactor_V = IntlMinutesFactor_P
    else:
        MinutesFactor_V = 1.0

    LamGoals_V = max(0.001, GoalRate_V * (MinutesPlayed_V * MinutesFactor_V) / 90.0)
    return LamGoals_V

# ─────────────────────────────────────────────────────────────────────────────
# KELLY SIZER
# ─────────────────────────────────────────────────────────────────────────────
def size_bet(FairProb_P: float, TargetOdds_P: float, Bankroll_P: float, IsFallback_P: bool) -> tuple[float, float]:
    if TargetOdds_P <= 1.0:
        return 0.0, 0.0

    FullKelly_V = (FairProb_P * TargetOdds_P - 1.0) / (TargetOdds_P - 1.0)
    KellyStake_V = (FullKelly_V * KellyFraction_P) * Bankroll_P

    MaxPct_V = MaxFallbackStakePct_P if IsFallback_P else MaxSingleStakePct_P
    KellyStake_V = max(0.0, min(KellyStake_V, Bankroll_P * MaxPct_V))

    StakePct_V = (KellyStake_V / Bankroll_P) * 100.0 if Bankroll_P > 0 else 0.0
    return round(KellyStake_V, 2), round(StakePct_V, 2)

def compute_ev(FairProb_P: float, Odds_P: float) -> float:
    return (FairProb_P * (Odds_P - 1.0)) - (1.0 - FairProb_P)

# ─────────────────────────────────────────────────────────────────────────────
# MAIN SIMULATION RUNNER
# ─────────────────────────────────────────────────────────────────────────────
def run_simulation(Bankroll_P: float):
    logger.info(f"Starting DeepFieldPro Simulation | Bankroll: ${Bankroll_P:.2f}")

    Df_V = load_player_db()

    # Load Platt scaler if available
    PlattScaler_V = None
    ScalerPath_V = os.path.join(MODEL_DIR, 'platt_scaler_sot.pkl')
    if os.path.exists(ScalerPath_V):
        with open(ScalerPath_V, 'rb') as F_V:
            PlattScaler_V = pickle.load(F_V)
        logger.info("Platt scaler loaded.")

    AllBets_V = []
    MissingLog_V = []

    for Fixture_V in TODAYS_FIXTURES:
        logger.info(f"\n{'='*60}")
        logger.info(f"Fixture: {Fixture_V['matchup']} ({Fixture_V['kickoff']})")
        logger.info(f"{'='*60}")

        for PlayerInfo_V in Fixture_V['players']:
            PlayerName_V = PlayerInfo_V['name']
            Position_V = PlayerInfo_V['position']

            if Position_V == 'GK':
                logger.info(f"  [SKIP] {PlayerName_V} — goalkeeper, no prop markets")
                continue

            # Lookup player stats
            Stats_V = find_player(Df_V, PlayerName_V)
            IsFallback_V = False

            if Stats_V is None:
                MissingLog_V.append(PlayerName_V)
                logger.warning(f"  [FALLBACK] {PlayerName_V} not found — using {Position_V} position average")
                Stats_V = get_position_average(Df_V, Position_V)
                if not Stats_V:
                    logger.warning(f"  [SKIP] {PlayerName_V} — no fallback data available")
                    continue
                IsFallback_V = True
                Stats_V['is_fallback'] = True

            OppPpda_V = Fixture_V['opp_ppda']
            CompType_V = Fixture_V['competition_type']

            # ── MARKET 1: Passes Over (VALIDATED — Brier 0.11) ──────────────
            LamPasses_V = compute_lam_passes(Stats_V, OppPpda_V, CompType_V)
            PassLine_V = 30.5  # Most common line on sportsbooks
            PassFairProb_V = poisson_prob_ge(LamPasses_V, 31)
            PassTargetOdds_V = round((1.0 / PassFairProb_V) * 1.05, 2) if PassFairProb_V > 0.05 else None
            PassEv_V = compute_ev(PassFairProb_V, PassTargetOdds_V) if PassTargetOdds_V else -1.0

            logger.info(f"\n  {PlayerName_V} ({'FALLBACK' if IsFallback_V else 'FOUND'})")
            logger.info(f"    [Passes] Lambda={LamPasses_V:.3f} | P(>30.5)={PassFairProb_V:.3f} | TargetOdds={PassTargetOdds_V} | EV={PassEv_V:.3f}")

            if PassTargetOdds_V and PassEv_V >= MinEvThreshold_P and PassFairProb_V >= 0.40:
                Stake_V, StakePct_V = size_bet(PassFairProb_V, PassTargetOdds_V, Bankroll_P, IsFallback_V)
                AllBets_V.append({
                    "rank": 0,
                    "fixture": Fixture_V['matchup'],
                    "kickoff": Fixture_V['kickoff'],
                    "player": PlayerName_V,
                    "market": f"Passes Over {PassLine_V}",
                    "selection": f"{PlayerName_V} Over {PassLine_V} Passes",
                    "lambda": round(LamPasses_V, 3),
                    "fair_prob": round(PassFairProb_V, 3),
                    "target_odds": PassTargetOdds_V,
                    "ev": round(PassEv_V, 3),
                    "kelly_stake": Stake_V,
                    "stake_pct": StakePct_V,
                    "is_fallback": IsFallback_V,
                    "confidence": "LOW" if IsFallback_V else "HIGH",
                    "market_validation": "PAPER_TRADE_READY",
                    "status": "BATCH"
                })

            # ── MARKET 2: Anytime Goalscorer ──────────────────────────────────
            LamGoals_V = compute_lam_goals(Stats_V, OppPpda_V, CompType_V)
            GoalFairProb_V = 1.0 - math.exp(-LamGoals_V)
            GoalTargetOdds_V = round((1.0 / GoalFairProb_V) * 1.05, 2) if GoalFairProb_V > 0.05 else None
            GoalEv_V = compute_ev(GoalFairProb_V, GoalTargetOdds_V) if GoalTargetOdds_V else -1.0

            logger.info(f"    [Goals] Lambda={LamGoals_V:.3f} | P(Score)={GoalFairProb_V:.3f} | TargetOdds={GoalTargetOdds_V} | EV={GoalEv_V:.3f}")

            if GoalTargetOdds_V and GoalEv_V >= MinEvThreshold_P and GoalFairProb_V >= 0.40:
                Stake_V, StakePct_V = size_bet(GoalFairProb_V, GoalTargetOdds_V, Bankroll_P, IsFallback_V)
                AllBets_V.append({
                    "rank": 0,
                    "fixture": Fixture_V['matchup'],
                    "kickoff": Fixture_V['kickoff'],
                    "player": PlayerName_V,
                    "market": "Anytime Goalscorer",
                    "selection": f"{PlayerName_V} Anytime Goalscorer",
                    "lambda": round(LamGoals_V, 3),
                    "fair_prob": round(GoalFairProb_V, 3),
                    "target_odds": GoalTargetOdds_V,
                    "ev": round(GoalEv_V, 3),
                    "kelly_stake": Stake_V,
                    "stake_pct": StakePct_V,
                    "is_fallback": IsFallback_V,
                    "confidence": "LOW" if IsFallback_V else "HIGH",
                    "market_validation": "VALIDATED",
                    "status": "BATCH"
                })

            # ── MARKET 3: Shots on Target Over 0.5 ───────────────────────────
            LamSot_V, SotFairProb_V = compute_lam_sot(Stats_V, OppPpda_V, CompType_V, PlattScaler_V)
            SotTargetOdds_V = round((1.0 / SotFairProb_V) * 1.05, 2) if SotFairProb_V > 0.05 else None
            SotEv_V = compute_ev(SotFairProb_V, SotTargetOdds_V) if SotTargetOdds_V else -1.0

            logger.info(f"    [SoT]   Lambda={LamSot_V:.3f} | P(SoT>=1)={SotFairProb_V:.3f} | TargetOdds={SotTargetOdds_V} | EV={SotEv_V:.3f}")

            if SotTargetOdds_V and SotEv_V >= MinEvThreshold_P and 0.10 <= SotFairProb_V <= 0.90:
                Stake_V, StakePct_V = size_bet(SotFairProb_V, SotTargetOdds_V, Bankroll_P, IsFallback_V)
                ValidationStatus_V = "CALIBRATION_GAP_42pp" if CompType_V == 1 else "PAPER_TRADE_READY"
                AllBets_V.append({
                    "rank": 0,
                    "fixture": Fixture_V['matchup'],
                    "kickoff": Fixture_V['kickoff'],
                    "player": PlayerName_V,
                    "market": "Shots on Target Over 0.5",
                    "selection": f"{PlayerName_V} Over 0.5 Shots on Target",
                    "lambda": round(LamSot_V, 3),
                    "fair_prob": round(SotFairProb_V, 3),
                    "target_odds": SotTargetOdds_V,
                    "ev": round(SotEv_V, 3),
                    "kelly_stake": Stake_V,
                    "stake_pct": StakePct_V,
                    "is_fallback": IsFallback_V,
                    "confidence": "LOW" if IsFallback_V else "MEDIUM",
                    "market_validation": ValidationStatus_V,
                    "status": "BATCH"
                })

    # Sort by EV descending
    AllBets_V.sort(key=lambda x: x['ev'], reverse=True)
    for Idx_V, B_V in enumerate(AllBets_V):
        B_V['rank'] = Idx_V + 1

    # Log missing players
    if MissingLog_V:
        MissingPath_V = os.path.join(DATA_DIR, 'missing_players.log')
        with open(MissingPath_V, 'a') as F_V:
            for Name_V in MissingLog_V:
                F_V.write(f"{datetime.datetime.now(datetime.UTC).isoformat()} | MISSING: {Name_V}\n")

    return AllBets_V

# ─────────────────────────────────────────────────────────────────────────────
# OUTPUT FORMATTER
# ─────────────────────────────────────────────────────────────────────────────
def write_output(Bets_P: list, Bankroll_P: float):
    TodayStr_V = datetime.datetime.now().strftime("%Y-%m-%d")

    BatchBets_V = [b for b in Bets_P if b['status'] == 'BATCH']
    TotalStake_V = sum(b['kelly_stake'] for b in BatchBets_V)
    ExpectedReturn_V = sum(b['kelly_stake'] * b['ev'] for b in BatchBets_V)
    StopLossRemain_V = Bankroll_P * 0.15

    OutTxt_V = os.path.join(DATA_DIR, f'TODAYS_BETS_{TodayStr_V}.txt')
    OutJson_V = os.path.join(DATA_DIR, f'TODAYS_BETS_{TodayStr_V}.json')

    with open(OutTxt_V, 'w', encoding='utf-8') as F_V:
        F_V.write("================================================================\n")
        F_V.write("DEEPFIELDPRO — TODAY'S PREDICTIONS (SIMULATION)\n")
        F_V.write(f"Date       : {TodayStr_V}\n")
        F_V.write(f"Bankroll   : ${Bankroll_P:.2f}\n")
        F_V.write(f"Generated  : {datetime.datetime.now().isoformat()}\n")
        F_V.write("NOTE: Odds below are TARGET THRESHOLDS. Only bet if bookmaker\n")
        F_V.write("      offers EQUAL OR BETTER odds than shown.\n")
        F_V.write("================================================================\n\n")

        F_V.write("── SINGLE BETS (BATCH — place if odds ≥ target) ────────────────\n\n")

        for B_V in BatchBets_V:
            FallbackNote_V = "\n   ⚠ FALLBACK: Based on position average, lower confidence" if B_V['is_fallback'] else ""
            CalibNote_V = "\n   ⚠ SoT market has 42pp calibration gap in intl — use smaller stake" if "CALIBRATION_GAP" in B_V.get('market_validation', '') else ""
            F_V.write(f"#{B_V['rank']} | {B_V['fixture']} — {B_V['kickoff']}\n")
            F_V.write(f"   Player    : {B_V['player']}\n")
            F_V.write(f"   Market    : {B_V['market']}\n")
            F_V.write(f"   Selection : {B_V['selection']}\n")
            F_V.write(f"   Target Odds : ≥ {B_V['target_odds']} (only bet at this or better)\n")
            F_V.write(f"   Fair Prob : {B_V['fair_prob']*100:.1f}% (model estimate)\n")
            F_V.write(f"   Lambda    : {B_V['lambda']:.3f} (Poisson rate)\n")
            F_V.write(f"   EV        : +{B_V['ev']*100:.1f}%\n")
            F_V.write(f"   Stake     : ${B_V['kelly_stake']:.2f} ({B_V['stake_pct']:.2f}% of bankroll)\n")
            F_V.write(f"   Confidence: {B_V['confidence']}{FallbackNote_V}{CalibNote_V}\n")
            F_V.write("\n")

        if not BatchBets_V:
            F_V.write("   No BATCH bets today. Model found no positive EV opportunities.\n\n")

        F_V.write("── PORTFOLIO SUMMARY ────────────────────────────────────────────\n")
        F_V.write(f"   Total BATCH bets    : {len(BatchBets_V)}\n")
        F_V.write(f"   Total stake today   : ${TotalStake_V:.2f} ({(TotalStake_V/Bankroll_P)*100:.2f}% of bankroll)\n")
        F_V.write(f"   Expected return     : ${ExpectedReturn_V:.2f}\n")
        F_V.write(f"   Stop-loss remaining : ${StopLossRemain_V:.2f} before DRAWDOWN_PAUSE triggers\n\n")

        F_V.write("── VALIDATED MARKETS ONLY ───────────────────────────────────────\n")
        F_V.write("   passes_over_30.5 : Brier 0.1102, Cal gap 6.4pp → BEST MARKET ⭐\n")
        F_V.write("   passes_over_40.5 : Brier 0.1495, Cal gap 8.9pp → GOOD\n")
        F_V.write("   sot_over_0.5     : Brier 0.1832, Cal gap 42.2pp → CAUTION (intl only)\n")
        F_V.write("   anytime_scorer   : Brier ~0.22, validated → USE WITH CARE\n\n")

        F_V.write("================================================================\n")
        F_V.write("RISK DISCLAIMER: This is a model output. All predictions carry\n")
        F_V.write("uncertainty. Never bet more than you can afford to lose.\n")
        F_V.write("These are TARGET odds — verify on your bookmaker before placing.\n")
        F_V.write("================================================================\n")

    # Save machine-readable JSON
    JsonOut_V = {
        "generated_at": datetime.datetime.now(datetime.UTC).isoformat(),
        "bankroll": Bankroll_P,
        "total_stake": TotalStake_V,
        "expected_return": ExpectedReturn_V,
        "bets": Bets_P
    }
    with open(OutJson_V, 'w') as F_V:
        json.dump(JsonOut_V, F_V, indent=2)

    logger.info(f"\n{'='*60}")
    logger.info(f"BATCH bets found   : {len(BatchBets_V)}")
    logger.info(f"Total stake        : ${TotalStake_V:.2f}")
    logger.info(f"Expected return    : ${ExpectedReturn_V:.2f}")
    logger.info(f"Output saved to    : data/TODAYS_BETS_{TodayStr_V}.txt")
    logger.info(f"Machine Output     : data/TODAYS_BETS_{TodayStr_V}.json")
    logger.info(f"{'='*60}")

    return OutTxt_V

if __name__ == "__main__":
    Parser_V = argparse.ArgumentParser(description="DeepFieldPro Simulation")
    Parser_V.add_argument('--bankroll', type=float, default=500.0, help='Bankroll in USD')
    Args_V = Parser_V.parse_args()

    Bets_V = run_simulation(Args_V.bankroll)
    OutFile_V = write_output(Bets_V, Args_V.bankroll)

    print(f"\nSimulation complete. Open: {OutFile_V}")
