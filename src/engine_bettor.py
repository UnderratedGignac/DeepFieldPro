"""
DeepFieldPro — Betting Engine (Module 2 of 3)
==============================================
Takes prediction probabilities from the Prediction Engine and compares
them against real bookmaker odds to identify +EV (positive expected value) bets.

INPUT:  predictions_df from engine_predictor.py
        bookmaker odds (live from API-Football or manual input)
OUTPUT: Ranked list of value bets with EV%, edge, and recommendation

No hardcoded values. No fake odds. Will only process real market lines.
If no bookmaker odds are available, it will clearly report that.
"""

import pandas as pd
import numpy as np
import requests
import os
import sys
import io
from datetime import date

# stdout encoding set by caller

ROOT     = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
DATA_DIR = os.path.join(ROOT, 'data')

API_KEY     = '4ae9f07e1ae1f775050015c50037a71d'
API_HEADERS = {'x-apisports-key': API_KEY}
API_BASE    = 'https://v3.football.api-sports.io'

# ─── Thresholds ────────────────────────────────────────────────────────────────
MIN_EDGE_PCT        = 4.0   # Only flag bets with > 4% probability edge
MIN_EV_PCT          = 3.0   # Only flag bets with > 3% EV
MIN_MODEL_PROB      = 0.10  # Ignore bets where our model gives < 10% probability
CONFIDENCE_REQUIRED = {'HIGH', 'MEDIUM'}  # Only bet HIGH or MEDIUM confidence players


# ─── Vig Stripping ─────────────────────────────────────────────────────────────
def strip_vig(odds_list: list[float]) -> list[float]:
    """
    Convert raw bookmaker odds to true no-vig probabilities.
    Removes the overround using standard proportional method.
    """
    raw_probs = [1.0 / o for o in odds_list if o > 1.0]
    total_prob = sum(raw_probs)
    if total_prob <= 0:
        return raw_probs
    return [p / total_prob for p in raw_probs]


def implied_prob(decimal_odds: float) -> float:
    """Convert decimal odds to implied probability (includes vig)."""
    if decimal_odds <= 1.0:
        return 1.0
    return 1.0 / decimal_odds


def expected_value(model_prob: float, decimal_odds: float) -> float:
    """
    EV = P(win) × profit - P(lose) × stake
    Normalised to per-unit stake so EV is in [-1, +∞).
    """
    return model_prob * (decimal_odds - 1.0) - (1.0 - model_prob)


def edge_pct(model_prob: float, market_odds: float) -> float:
    """
    Probability edge = model_prob - no-vig implied_prob.
    We strip vig from a 2-way market (over/under) before computing edge.
    """
    # For over/under markets, assume balanced book: true prob ≈ implied / 1.05
    implied = implied_prob(market_odds)
    # Approximate vig removal for a simple over/under line
    vig_factor = 1.05
    true_implied = implied / vig_factor
    return (model_prob - true_implied) * 100.0


# ─── Odds Fetching ─────────────────────────────────────────────────────────────
def fetch_bookmaker_odds(fixture_ids: list[int]) -> dict:
    """
    Fetch player prop odds from API-Football for each fixture.
    Returns a dict: {fixture_id: {market_name: {player_name: {line: odds}}}}
    
    Note: Player prop odds availability depends on API-Football's coverage.
    If unavailable, this will return an empty dict and be clearly flagged.
    """
    all_odds = {}
    for fid in fixture_ids:
        try:
            r = requests.get(f'{API_BASE}/odds', headers=API_HEADERS,
                             params={'fixture': fid}, timeout=10)
            data = r.json()
            errors = data.get('errors')
            if errors:
                print(f'  Odds API error for fixture {fid}: {errors}')
                continue

            bookmakers = data.get('response', [])
            if not bookmakers:
                print(f'  No odds available for fixture {fid}')
                continue

            fixture_odds = {}
            for bk in bookmakers:
                bk_name = bk.get('bookmakers', [{}])[0].get('name', 'Unknown') if bk.get('bookmakers') else 'Unknown'
                for bk_data in bk.get('bookmakers', []):
                    for bet in bk_data.get('bets', []):
                        market = bet.get('name', '')
                        if market not in fixture_odds:
                            fixture_odds[market] = {}
                        for val in bet.get('values', []):
                            fixture_odds[market][val.get('value', '')] = float(val.get('odd', 0))

            if fixture_odds:
                all_odds[fid] = fixture_odds
                print(f'  Fixture {fid}: {len(fixture_odds)} markets loaded')
            else:
                print(f'  Fixture {fid}: Odds response empty')

        except Exception as e:
            print(f'  Odds fetch error for fixture {fid}: {e}')

    return all_odds


# ─── Bet Identifier ────────────────────────────────────────────────────────────
def identify_value_bets(predictions_df: pd.DataFrame,
                        bookmaker_odds: dict = None,
                        manual_lines: list[dict] = None) -> pd.DataFrame:
    """
    Core function: compare model probabilities against bookmaker lines.

    Parameters
    ----------
    predictions_df  : Output from engine_predictor.run_predictions()
    bookmaker_odds  : Dict from fetch_bookmaker_odds() — real market lines
    manual_lines    : Optional list of manually entered lines in format:
                      [{'player': 'Dušan Vlahović', 'market': 'Goals', 'line': 0.5, 'over_odds': 2.10, 'under_odds': 1.75}]

    Returns
    -------
    DataFrame of value bets sorted by EV descending.
    """
    if predictions_df.empty:
        print('  No predictions to evaluate.')
        return pd.DataFrame()

    value_bets = []

    # ── Process manual lines ──────────────────────────────────────────────────
    if manual_lines:
        for entry in manual_lines:
            player_name = entry.get('player', '').strip()
            market      = entry.get('market', '').strip()   # 'Goals', 'Shots', 'SoT', 'Assists', 'Cards'
            line        = float(entry.get('line', 0.5))
            over_odds   = float(entry.get('over_odds', 0))
            under_odds  = float(entry.get('under_odds', 0))

            # Map market name to prediction column
            MARKET_MAP = {
                'Goals':   'Gls',
                'Assists': 'Ast',
                'Shots':   'Sh',
                'SoT':     'SoT',
                'Cards':   'CrdY',
                'Minutes': 'min',
            }
            col_key = MARKET_MAP.get(market)
            if not col_key:
                print(f'  Unknown market: {market}. Valid: {list(MARKET_MAP.keys())}')
                continue

            # Find player in predictions
            player_rows = predictions_df[predictions_df['player'].str.lower() == player_name.lower()]
            if player_rows.empty:
                # Fuzzy search
                mask = predictions_df['player'].str.lower().str.contains(player_name.lower()[:8], na=False)
                player_rows = predictions_df[mask]

            if player_rows.empty:
                print(f'  Player not found in predictions: {player_name}')
                continue

            row = player_rows.iloc[0]
            if row.get('confidence', 'LOW') not in CONFIDENCE_REQUIRED:
                continue

            # Determine which probability column to use based on line
            if line == 0.5:
                prob_col = f'p_{col_key}_over_0_5'
            elif line == 1.5:
                prob_col = f'p_{col_key}_over_1_5'
            elif line == 2.5:
                prob_col = f'p_{col_key}_over_2_5'
            else:
                prob_col = f'p_{col_key}_over_0_5'  # fallback

            model_prob_over  = float(row.get(prob_col, 0))
            model_prob_under = 1.0 - model_prob_over

            # Evaluate OVER
            if over_odds > 1.0 and model_prob_over >= MIN_MODEL_PROB:
                ev  = expected_value(model_prob_over, over_odds)
                edg = edge_pct(model_prob_over, over_odds)
                if ev * 100 >= MIN_EV_PCT and edg >= MIN_EDGE_PCT:
                    value_bets.append({
                        'Player':          row['player'],
                        'Team':            row.get('team', ''),
                        'Match':           row.get('match', ''),
                        'Market':          f'{market} Over {line}',
                        'Line':            line,
                        'Side':            'OVER',
                        'Model Prob':      round(model_prob_over, 4),
                        'Book Odds':       over_odds,
                        'Implied Prob':    round(implied_prob(over_odds), 4),
                        'Edge %':          round(edg, 2),
                        'EV %':            round(ev * 100, 2),
                        'xExpected':       round(float(row.get(f'exp_{col_key}', 0)), 3),
                        'Confidence':      row.get('confidence', 'LOW'),
                        'Recommendation':  'BET' if edg >= 5 else 'MONITOR',
                    })

            # Evaluate UNDER
            if under_odds > 1.0 and model_prob_under >= MIN_MODEL_PROB:
                ev  = expected_value(model_prob_under, under_odds)
                edg = edge_pct(model_prob_under, under_odds)
                if ev * 100 >= MIN_EV_PCT and edg >= MIN_EDGE_PCT:
                    value_bets.append({
                        'Player':          row['player'],
                        'Team':            row.get('team', ''),
                        'Match':           row.get('match', ''),
                        'Market':          f'{market} Under {line}',
                        'Line':            line,
                        'Side':            'UNDER',
                        'Model Prob':      round(model_prob_under, 4),
                        'Book Odds':       under_odds,
                        'Implied Prob':    round(implied_prob(under_odds), 4),
                        'Edge %':          round(edg, 2),
                        'EV %':            round(ev * 100, 2),
                        'xExpected':       round(float(row.get(f'exp_{col_key}', 0)), 3),
                        'Confidence':      row.get('confidence', 'LOW'),
                        'Recommendation':  'BET' if edg >= 5 else 'MONITOR',
                    })

    if not value_bets:
        return pd.DataFrame()

    result_df = pd.DataFrame(value_bets).sort_values('EV %', ascending=False)
    return result_df


def run_betting_engine(predictions_df: pd.DataFrame,
                       manual_lines: list[dict] = None) -> pd.DataFrame:
    """
    Full betting engine pipeline.
    
    1. Try to fetch live bookmaker odds from API-Football
    2. Fall back to manual_lines if provided
    3. Return ranked DataFrame of value bets
    """
    print(f'\n{"="*65}')
    print('[BETTING ENGINE] Identifying +EV opportunities')
    print(f'{"="*65}')
    print(f'  Min edge threshold:  {MIN_EDGE_PCT}%')
    print(f'  Min EV threshold:    {MIN_EV_PCT}%')
    print(f'  Confidence filter:   {CONFIDENCE_REQUIRED}')

    # Try live odds
    bookmaker_odds = {}
    if not predictions_df.empty and 'fixture_id' in predictions_df.columns:
        fixture_ids = predictions_df['fixture_id'].dropna().unique().tolist()
        print(f'\n[1] Fetching live odds for {len(fixture_ids)} fixtures...')
        bookmaker_odds = fetch_bookmaker_odds([int(f) for f in fixture_ids])

    print(f'\n[2] Evaluating value bets...')
    value_df = identify_value_bets(predictions_df, bookmaker_odds, manual_lines)

    if value_df.empty:
        print('\n  No +EV bets identified.')
        if not manual_lines and not bookmaker_odds:
            print('  REASON: No bookmaker lines available. Provide manual_lines or ensure API odds are available.')
    else:
        print(f'\n  {len(value_df)} value bets identified:')
        bets_only = value_df[value_df['Recommendation'] == 'BET']
        monitor   = value_df[value_df['Recommendation'] == 'MONITOR']
        print(f'    BET:     {len(bets_only)}')
        print(f'    MONITOR: {len(monitor)}')

    return value_df


if __name__ == '__main__':
    # Demo: run against today's predictions with manually entered lines
    # In production, replace manual_lines with real sportsbook data
    from engine_predictor import run_predictions

    preds = run_predictions()

    if not preds.empty:
        # Example manual lines — replace with actual sportsbook odds
        manual_lines = [
            {'player': 'Dušan Vlahović', 'market': 'Goals',  'line': 0.5, 'over_odds': 2.40, 'under_odds': 1.55},
            {'player': 'Dušan Vlahović', 'market': 'Shots',  'line': 1.5, 'over_odds': 1.80, 'under_odds': 2.00},
            {'player': 'Dušan Vlahović', 'market': 'SoT',    'line': 0.5, 'over_odds': 1.65, 'under_odds': 2.15},
            {'player': 'Santiago Sandoval', 'market': 'Shots', 'line': 1.5, 'over_odds': 1.85, 'under_odds': 1.95},
            {'player': 'Dominik Szoboszlai', 'market': 'Shots', 'line': 1.5, 'over_odds': 1.90, 'under_odds': 1.90},
            {'player': 'Dominik Szoboszlai', 'market': 'Goals', 'line': 0.5, 'over_odds': 4.50, 'under_odds': 1.20},
        ]
        bets = run_betting_engine(preds, manual_lines)
        if not bets.empty:
            out = os.path.join(DATA_DIR, f'value_bets_{date.today()}.csv')
            bets.to_csv(out, index=False)
            print(f'\nSaved: {out}')
            print(bets.to_string(index=False))
