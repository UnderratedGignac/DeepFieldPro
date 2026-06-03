import os
import sqlite3
from datetime import datetime, timezone
from model_runner import run_for_match

# Paths
BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(BASE_DIR, '..', 'data')
DB_LINEUPS = os.path.join(DATA_DIR, 'parsed_lineups.db')
DB_ODDS = os.path.join(DATA_DIR, 'odds_stream.db')

MATCH_FIXTURES = {
    # 1. Croatia vs. Belgium
    '1001': {
        'opponent': 'Belgium',
        'players': [
            # Croatia
            ('1', 'Luka Modric', 'central_mid'),
            ('2', 'Mateo Kovacic', 'central_mid'),
            ('3', 'Josko Gvardiol', 'center_back'),
            ('4', 'Lovro Majer', 'attacking_mid'),
            ('5', 'Mario Pasalic', 'attacking_mid'),
            ('6', 'Andrej Kramaric', 'striker'),
            ('7', 'Josip Stanisic', 'fullback'),
            ('8', 'Borna Sosa', 'fullback'),
            # Belgium
            ('9', 'Kevin De Bruyne', 'attacking_mid'),
            ('10', 'Leandro Trossard', 'winger'),
            ('11', 'Jeremy Doku', 'winger'),
            ('12', 'Romelu Lukaku', 'striker'),
            ('13', 'Amadou Onana', 'defensive_mid'),
            ('14', 'Orel Mangala', 'central_mid'),
            ('15', 'Timothy Castagne', 'fullback'),
            ('16', 'Wout Faes', 'center_back'),
            ('17', 'Arthur Theate', 'center_back')
        ]
    },
    # 2. Georgia vs. Romania
    '1002': {
        'opponent': 'Romania',
        'players': [
            # Georgia
            ('18', 'Guram Kashia', 'center_back'),
            ('19', 'Otar Kakabadze', 'fullback'),
            # Romania
            ('20', 'Radu Dragusin', 'center_back'),
            ('21', 'Nicolae Stanciu', 'attacking_mid'),
            ('22', 'Marius Marin', 'defensive_mid')
        ]
    },
    # 3. Morocco vs. Madagascar
    '1003': {
        'opponent': 'Madagascar',
        'players': [
            # Morocco
            ('23', 'Achraf Hakimi', 'fullback'),
            ('24', 'Brahim Diaz', 'attacking_mid'),
            ('25', 'Nayef Aguerd', 'center_back'),
            ('26', 'Sofyan Amrabat', 'defensive_mid'),
            ('27', 'Azzedine Ounahi', 'central_mid')
        ]
    },
    # 4. Wales vs. Ghana
    '1004': {
        'opponent': 'Ghana',
        'players': [
            # Wales
            ('28', 'Brennan Johnson', 'winger'),
            ('29', 'Harry Wilson', 'attacking_mid'),
            ('30', 'Daniel James', 'winger'),
            ('31', 'Ben Davies', 'fullback'),
            ('32', 'Ethan Ampadu', 'defensive_mid'),
            ('33', 'Joe Rodon', 'center_back'),
            # Ghana
            ('34', 'Mohammed Kudus', 'attacking_mid'),
            ('35', 'Thomas Partey', 'defensive_mid'),
            ('36', 'Inaki Williams', 'striker'),
            ('37', 'Antoine Semenyo', 'winger'),
            ('38', 'Tariq Lamptey', 'fullback'),
            ('39', 'Gideon Mensah', 'fullback')
        ]
    },
    # 5. Haiti vs. New Zealand
    '1005': {
        'opponent': 'Haiti',
        'players': [
            # New Zealand
            ('40', 'Chris Wood', 'striker')
        ]
    }
}

print("==================================================")
print("RUNNING LIVE PREDICTIONS ON EXPECTED SQUADS (ALL 14 BETARABIA MARKETS)")
print("==================================================")

# 1. Setup Lineups Table
conn_lineups = sqlite3.connect(DB_LINEUPS)
cursor_lineups = conn_lineups.cursor()
cursor_lineups.execute('''CREATE TABLE IF NOT EXISTS parsed_lineups
                  (match_id TEXT, team_id TEXT, player_id TEXT, player_name TEXT, 
                   position_raw TEXT, expected_role TEXT, grid TEXT, is_starter INTEGER, timestamp DATETIME)''')

# Clear prior test lineups
for match_id in MATCH_FIXTURES.keys():
    cursor_lineups.execute("DELETE FROM parsed_lineups WHERE match_id = ?", (match_id,))

# Insert starters
now_iso = datetime.now(timezone.utc).isoformat()
for match_id, info in MATCH_FIXTURES.items():
    for p_id, p_name, role in info['players']:
        cursor_lineups.execute("""
            INSERT INTO parsed_lineups (match_id, team_id, player_id, player_name, position_raw, expected_role, grid, is_starter, timestamp)
            VALUES (?, '1', ?, ?, 'M', ?, '3:1', 1, ?)
        """, (match_id, p_id, p_name, role, now_iso))

conn_lineups.commit()
conn_lineups.close()
print("[OK] Starting lineups populated.")

# 2. Setup Odds Table
conn_odds = sqlite3.connect(DB_ODDS)
cursor_odds = conn_odds.cursor()
cursor_odds.execute('''CREATE TABLE IF NOT EXISTS odds_feed (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id        TEXT,
    market_type     TEXT,
    player_id       TEXT,
    selection_name  TEXT,
    price           REAL,
    volume          REAL,
    bookmaker       TEXT,
    timestamp       DATETIME
)''')

# Clear prior test odds
for match_id in MATCH_FIXTURES.keys():
    cursor_odds.execute("DELETE FROM odds_feed WHERE match_id = ?", (match_id,))

# Define all 14 markets with their lines
PROPS_CONFIG = [
    ('goals_anytime', [None]),
    ('goals_first', [None]),
    ('goals_brace', [None]),
    ('goals_hattrick', [None]),
    ('goals_both_halves', [None]),
    ('goals_first_10', [None]),
    ('cards_yellow', [None]),
    ('cards_any', [None]),
    ('cards_first', [None]),
    ('goals_first_half', [None]),
    ('goals_second_half', [None]),
    ('shots_total', [0.5, 1.5, 2.5, 3.5]),
    ('sot_total', [0.5, 1.5, 2.5]),
    ('offsides_total', [0.5, 1.5])
]

# Insert standard 1.90 / 1.90 odds for each player/line combination
for match_id, info in MATCH_FIXTURES.items():
    for p_id, p_name, _ in info['players']:
        for market_type, lines in PROPS_CONFIG:
            for line in lines:
                if line is not None:
                    sel_over = f"Over {line} - {p_name}"
                    sel_under = f"Under {line} - {p_name}"
                else:
                    sel_over = f"Yes - {p_name}"
                    sel_under = f"No - {p_name}"

                cursor_odds.execute("""
                    INSERT INTO odds_feed (match_id, market_type, player_id, selection_name, price, volume, bookmaker, timestamp)
                    VALUES (?, ?, ?, ?, 1.90, 100.0, 'Betfair', ?)
                """, (match_id, market_type, p_id, sel_over, now_iso))
                cursor_odds.execute("""
                    INSERT INTO odds_feed (match_id, market_type, player_id, selection_name, price, volume, bookmaker, timestamp)
                    VALUES (?, ?, ?, ?, 1.90, 100.0, 'Betfair', ?)
                """, (match_id, market_type, p_id, sel_under, now_iso))

conn_odds.commit()
conn_odds.close()
print("[OK] Standard odds feed populated.")

# 3. Call the model runner for each match
total_bets_placed = 0
for match_id, info in MATCH_FIXTURES.items():
    print(f"\n--- EVALUATING MATCH {match_id} | Opponent: {info['opponent']} ---")
    bets = run_for_match(
        fixture_id=match_id,
        opponent_team=info['opponent'],
        lineup_drop_at=now_iso,
        latency_ms=100,
        role_shifts=[],
        regime='lineup_adjustment_window'
    )
    total_bets_placed += len(bets)

print("\n==================================================")
print(f"PIPELINE RUN COMPLETE | Total Bets Placed: {total_bets_placed}")
print("==================================================")
