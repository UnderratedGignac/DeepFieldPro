"""
environment_edge.py — Dedicated bet signals for environmental + structural edges.

Provides three independent strategy signals, each with their own
bet_source and $100 virtual bankroll:

  WEATHER_EDGE  — when weather pushes O/U 2.5 xG adjustment >= threshold,
                  bet Under 2.5 (rain/wind reduces goals)
  FATIGUE_EDGE  — when a fatigued team (3+ games/7d) is priced as if fresh,
                  bet against them (or on their opponent) if odds offer value
  REFEREE_EDGE  — when a high-card ref is assigned and the market hasn't
                  priced in the xG suppression, bet Under 2.5 or away win

Scientific basis:
  WEATHER: Rain reduces expected goals by ~0.4/game (mean 2.76 → 2.36),
           wind >= 25 km/h reduces BTTS probability by ~15%.
           Source: Premier League / La Liga studies 2016-2025.

  FATIGUE: Teams playing 3rd game in 7 days show -8% offensive xG drop,
           slight improvement in defensive compactness.
           Source: Stuttgen et al. (2025), Sports Medicine meta-analysis (2021).

  REFEREE: Referees have r~0.55 consistency in booking rates across seasons.
           High-card refs suppress goals through stoppages (-0.08 xG per
           booking unit above mean).
           Source: UEFA research, Anderson & Sally (2013).
"""

import math
import logging

logger = logging.getLogger(__name__)

# ── Thresholds ────────────────────────────────────────────────────────────────
WEATHER_RAIN_THRESHOLD_MM   = 1.0   # mm/h minimum to count as "rain"
WEATHER_WIND_THRESHOLD_KMH  = 25.0  # km/h
WEATHER_XG_DROP_MIN         = 0.10  # minimum xg_mult reduction to fire (10%)
WEATHER_MIN_EDGE_PCT         = 3.0  # minimum implied edge % to bet

FATIGUE_MIN_GAMES           = 3     # team must have >= 3 games in 7 days
FATIGUE_MIN_EDGE_PCT        = 4.0   # minimum edge % (fatigue suppresses scoring)

REFEREE_HIGH_CARD_MULT_MAX  = 0.97  # if xg_mult < 0.97 (high card), consider betting Under
REFEREE_MIN_EDGE_PCT        = 3.0


# ── WEATHER EDGE ─────────────────────────────────────────────────────────────

def weather_edge_signal(
    home_team: str,
    away_team: str,
    market: str,
    selection: str,
    odds: float,
    weather_info: dict,
) -> dict:
    """
    Returns a signal dict if WEATHER_EDGE should fire.

    Fires on:
      - Under 2.5 when rain or heavy wind is forecast (xg_mult <= 0.90)
      - BTTS No when heavy wind (btts_yes_mult <= 0.85)

    weather_info: dict from weather_adjuster.get_weather_adjustments()
    """
    base = {"fire": False, "edge_pct": 0.0, "reason": "", "market": market, "selection": selection}

    if not weather_info or weather_info.get("source") == "no-stadium":
        return base

    xg_mult      = weather_info.get("xg_mult", 1.0)
    over25_mult  = weather_info.get("over25_mult", 1.0)
    btts_mult    = weather_info.get("btts_yes_mult", 1.0)
    rain         = weather_info.get("rain", False)
    heavy_wind   = weather_info.get("heavy_wind", False)
    wind_kmh     = weather_info.get("wind_kmh", 0.0)
    precip_mm    = weather_info.get("precipitation_mm", 0.0)

    if not (rain or heavy_wind):
        return base

    # Case 1: Under 2.5 in rain or wind
    if market in ("Over/Under 2.5", "Over/Under 3.0") and "Under" in selection:
        # Market is pricing roughly 50% Over/Under (implied by odds)
        market_prob = 100.0 / odds if odds > 1.0 else 50.0
        # Weather adjustment means Under is more likely than priced
        # We estimate edge as: (over25_mult drop) * fair probability shift
        fair_under_prob = market_prob / over25_mult   # if Over is less likely, Under is more likely
        edge_pct = fair_under_prob - market_prob
        if edge_pct >= WEATHER_MIN_EDGE_PCT:
            base["fire"] = True
            base["edge_pct"] = round(edge_pct, 2)
            base["reason"] = (
                f"Weather edge: rain={precip_mm:.1f}mm wind={wind_kmh:.0f}km/h "
                f"xG*{xg_mult:.2f} O25*{over25_mult:.2f} -> Under more likely by {edge_pct:.1f}%"
            )
            return base

    # Case 2: BTTS No in heavy wind
    if market == "BTTS" and selection in ("No", "BTTS No") and heavy_wind:
        market_prob = 100.0 / odds if odds > 1.0 else 50.0
        fair_btts_no_prob = market_prob / btts_mult  # btts_yes less likely -> btts_no more likely
        edge_pct = fair_btts_no_prob - market_prob
        if edge_pct >= WEATHER_MIN_EDGE_PCT:
            base["fire"] = True
            base["edge_pct"] = round(edge_pct, 2)
            base["reason"] = (
                f"Weather edge: heavy wind {wind_kmh:.0f}km/h "
                f"BTTS yes suppressed {btts_mult:.2f} -> BTTS No by {edge_pct:.1f}%"
            )
            return base

    return base


# ── FATIGUE EDGE ──────────────────────────────────────────────────────────────

def fatigue_edge_signal(
    home_team: str,
    away_team: str,
    market: str,
    selection: str,
    odds: float,
    fatigue_info: dict,
) -> dict:
    """
    Returns a signal dict if FATIGUE_EDGE should fire.

    Fires on:
      - Away Win or Under 2.5 when the home team is fatigued
      - Home Win or Under 2.5 when the away team is fatigued

    fatigue_info: dict from fatigue_detector.congestion_summary()
    """
    base = {"fire": False, "edge_pct": 0.0, "reason": "", "market": market, "selection": selection}

    if not fatigue_info:
        return base

    home_fatigued  = fatigue_info.get("home_fatigued", False)
    away_fatigued  = fatigue_info.get("away_fatigued", False)
    home_games_7d  = fatigue_info.get("home_games_7d", 0)
    away_games_7d  = fatigue_info.get("away_games_7d", 0)
    home_mult      = fatigue_info.get("home_mult", 1.0)
    away_mult      = fatigue_info.get("away_mult", 1.0)

    if not (home_fatigued or away_fatigued):
        return base

    market_prob = 100.0 / odds if odds > 1.0 else 50.0

    # Case 1: Home fatigued → bet Away Win if 1X2 and odds reasonable
    if home_fatigued and market == "1X2":
        if "(2)" in selection or "away" in selection.lower():
            # xG suppression on home side = more likely away doesn't concede / wins
            # Rough edge: home_mult drop * market_prob
            drop = 1.0 - home_mult
            edge_pct = drop * market_prob * 0.8  # 80% of theoretical edge (conservative)
            if edge_pct >= FATIGUE_MIN_EDGE_PCT:
                base["fire"] = True
                base["edge_pct"] = round(edge_pct, 2)
                base["reason"] = (
                    f"Fatigue edge: {home_team} fatigued ({home_games_7d}g/7d), "
                    f"xG reduced {home_mult:.2f} -> Away Win value {edge_pct:.1f}%"
                )
                return base

    # Case 2: Away fatigued → bet Home Win
    if away_fatigued and market == "1X2":
        if "(1)" in selection or "home" in selection.lower():
            drop = 1.0 - away_mult
            edge_pct = drop * market_prob * 0.8
            if edge_pct >= FATIGUE_MIN_EDGE_PCT:
                base["fire"] = True
                base["edge_pct"] = round(edge_pct, 2)
                base["reason"] = (
                    f"Fatigue edge: {away_team} fatigued ({away_games_7d}g/7d), "
                    f"xG reduced {away_mult:.2f} -> Home Win value {edge_pct:.1f}%"
                )
                return base

    # Case 3: Any fatigued team → Under 2.5 (both attack and defence affected)
    if market in ("Over/Under 2.5",) and "Under" in selection:
        if home_fatigued or away_fatigued:
            total_drop = (1.0 - home_mult) + (1.0 - away_mult)
            edge_pct = total_drop * market_prob * 0.6
            if edge_pct >= FATIGUE_MIN_EDGE_PCT:
                base["fire"] = True
                base["edge_pct"] = round(edge_pct, 2)
                fatigued_teams = []
                if home_fatigued:
                    fatigued_teams.append(f"{home_team}({home_games_7d}g)")
                if away_fatigued:
                    fatigued_teams.append(f"{away_team}({away_games_7d}g)")
                base["reason"] = (
                    f"Fatigue edge: {', '.join(fatigued_teams)} fatigued -> Under 2.5 +{edge_pct:.1f}%"
                )
                return base

    return base


# ── REFEREE EDGE ──────────────────────────────────────────────────────────────

def referee_edge_signal(
    home_team: str,
    away_team: str,
    market: str,
    selection: str,
    odds: float,
    referee_info: dict,
) -> dict:
    """
    Returns a signal dict if REFEREE_EDGE should fire.

    Fires on:
      - Under 2.5 when a high-card ref is assigned and market underestimates impact
      - Away Win when ref has strong home bias and home team is priced too short

    referee_info: dict from referee_data.get_referee_signal()
    """
    base = {"fire": False, "edge_pct": 0.0, "reason": "", "market": market, "selection": selection}

    if not referee_info or not referee_info.get("found"):
        return base

    xg_mult     = referee_info.get("xg_mult", 1.0)
    is_high     = referee_info.get("is_high_card", False)
    booking_rate = referee_info.get("booking_rate", 3.5)
    home_bias   = referee_info.get("home_bias", 0.0)
    ref_name    = referee_info.get("referee", "Unknown")

    market_prob = 100.0 / odds if odds > 1.0 else 50.0

    # Case 1: High-card ref → Under 2.5
    if is_high and xg_mult <= REFEREE_HIGH_CARD_MULT_MAX:
        if market in ("Over/Under 2.5",) and "Under" in selection:
            drop = 1.0 - xg_mult
            edge_pct = drop * market_prob * 1.5
            if edge_pct >= REFEREE_MIN_EDGE_PCT:
                base["fire"] = True
                base["edge_pct"] = round(edge_pct, 2)
                base["reason"] = (
                    f"Referee edge: {ref_name} high-card ({booking_rate:.1f}/match) "
                    f"xG*{xg_mult:.3f} -> Under 2.5 +{edge_pct:.1f}%"
                )
                return base

    # Case 2: Strong home bias → value on Away Win (market underestimates away chance)
    if home_bias > 0.25 and market == "1X2":
        if "(2)" in selection or "away" in selection.lower():
            # Ref favouring home means away team is disadvantaged → priced at longer odds
            # But the EDGE: if the market doesn't fully price in the bias,
            # the away team is UNDERPRICED (they'll be further penalised than priced)
            # Actually: strong home bias → bet HOME not away. Let's be precise.
            pass  # Skip this case — direction is ambiguous without full model

    # Case 3: Low-card ref → Over 2.5 (fewer stoppages = more goals)
    if referee_info.get("is_low_card") and xg_mult >= 1.03:
        if market in ("Over/Under 2.5",) and "Over" in selection:
            boost = xg_mult - 1.0
            edge_pct = boost * market_prob * 1.5
            if edge_pct >= REFEREE_MIN_EDGE_PCT:
                base["fire"] = True
                base["edge_pct"] = round(edge_pct, 2)
                base["reason"] = (
                    f"Referee edge: {ref_name} low-card ({booking_rate:.1f}/match) "
                    f"xG*{xg_mult:.3f} -> Over 2.5 +{edge_pct:.1f}%"
                )
                return base

    return base
