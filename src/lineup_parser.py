"""
lineup_parser.py
----------------
Parses the API-Football v3 lineup payload into structured player roles.
Handles the REAL API response format:
  startXI[n]['player'] = {'id': 1234, 'name': 'Rodri', 'pos': 'M', 'grid': '4:1'}

Grid format: 'row:column' where row 1 = goalkeeper.
Storing the grid enables formation detection in the future.
"""

import os
import sqlite3

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "parsed_lineups.db")

# Mapping from API-Football position code → tactical role
# API-Football uses single letters: G, D, M, F — and sometimes specific codes
POSITION_TO_ROLE = {
    # Goalkeepers
    "G": "goalkeeper",
    # Defenders
    "D": "defender",  # generic — resolved further by grid position
    "CB": "center_back",
    "LB": "fullback",
    "RB": "fullback",
    "LWB": "wingback",
    "RWB": "wingback",
    # Midfielders
    "M": "midfield",  # generic — resolved further by grid position
    "CDM": "defensive_mid",
    "CM": "central_mid",
    "CAM": "attacking_mid",
    "LM": "winger",
    "RM": "winger",
    # Forwards
    "F": "forward",  # generic — resolved further by grid position
    "LW": "winger",
    "RW": "winger",
    "ST": "striker",
    "CF": "striker",
    "SS": "striker",  # Second striker / shadow striker
}


def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS parsed_lineups (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        match_id     TEXT,
        team_id      TEXT,
        player_id    TEXT,
        player_name  TEXT,
        position_raw TEXT,
        expected_role TEXT,
        grid         TEXT,
        is_starter   BOOLEAN,
        timestamp    DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(match_id, player_id)
    )
    """)
    conn.commit()
    conn.close()


def parse_and_store_lineup(match_id, team_id, api_team_data):
    """
    Parses and stores lineup from the real API-Football v3 response for ONE team.

    api_team_data: The dict for one team from the API response, which looks like:
    {
      "team": {"id": 50, "name": "Manchester City"},
      "startXI": [
        {"player": {"id": 617, "name": "Ederson", "pos": "G", "grid": "1:1"}},
        ...
      ],
      "substitutes": [
        {"player": {"id": 999, "name": "Some Player", "pos": "M", "grid": null}},
        ...
      ]
    }
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    def _insert_players(player_list, is_starter):
        for entry in player_list:
            p = entry.get("player", {})
            pid = str(p.get("id", ""))
            name = p.get("name", "Unknown")
            pos_raw = str(p.get("pos", "")).upper().strip()
            grid = p.get("grid") or ""

            # Map position → role. Use grid to refine generic positions.
            role = POSITION_TO_ROLE.get(pos_raw, "unknown")

            # Refine generic 'defender' using grid column (edge cols = fullback)
            if role == "defender" and grid:
                try:
                    col = int(grid.split(":")[1])
                    row = int(grid.split(":")[0])
                    # In a 4-man defence: cols 1 and 4 are fullbacks, 2 and 3 are CBs
                    if col in (1, 4):
                        role = "fullback"
                    else:
                        role = "center_back"
                except (IndexError, ValueError):
                    pass  # Keep generic 'defender' if grid is malformed

            # Refine generic 'midfield' using row (higher row = more attacking)
            if role == "midfield" and grid:
                try:
                    row = int(grid.split(":")[0])
                    if row >= 4:
                        role = "attacking_mid"
                    elif row == 2:
                        role = "defensive_mid"
                    else:
                        role = "central_mid"
                except (IndexError, ValueError):
                    pass

            if not pid:
                continue

            try:
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO parsed_lineups
                    (match_id, team_id, player_id, player_name, position_raw, expected_role, grid, is_starter)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        match_id,
                        str(team_id),
                        pid,
                        name,
                        pos_raw,
                        role,
                        grid,
                        is_starter,
                    ),
                )
            except Exception as e:
                print(f"DB Error inserting {name}: {e}")

    _insert_players(api_team_data.get("startXI", []), is_starter=True)
    _insert_players(api_team_data.get("substitutes", []), is_starter=False)

    conn.commit()
    conn.close()
    team_name = api_team_data.get("team", {}).get("name", team_id)
    print(f"Parsed lineup for match {match_id} | Team: {team_name}")


if __name__ == "__main__":
    init_db()

    # Realistic mock of API-Football v3 response structure
    mock_api_team = {
        "team": {"id": 50, "name": "Manchester City"},
        "startXI": [
            {"player": {"id": 617, "name": "Ederson", "pos": "G", "grid": "1:1"}},
            {"player": {"id": 883, "name": "Kyle Walker", "pos": "D", "grid": "2:4"}},
            {"player": {"id": 627, "name": "Ruben Dias", "pos": "D", "grid": "2:3"}},
            {"player": {"id": 626, "name": "Manuel Akanji", "pos": "D", "grid": "2:2"}},
            {
                "player": {
                    "id": 745,
                    "name": "Josko Gvardiol",
                    "pos": "D",
                    "grid": "2:1",
                }
            },
            {"player": {"id": 284, "name": "Rodri", "pos": "M", "grid": "3:1"}},
            {
                "player": {
                    "id": 622,
                    "name": "Kevin De Bruyne",
                    "pos": "M",
                    "grid": "4:3",
                }
            },
            {
                "player": {
                    "id": 898,
                    "name": "Bernardo Silva",
                    "pos": "M",
                    "grid": "4:2",
                }
            },
            {"player": {"id": 742, "name": "Phil Foden", "pos": "F", "grid": "5:1"}},
            {
                "player": {
                    "id": 1100,
                    "name": "Erling Haaland",
                    "pos": "F",
                    "grid": "5:2",
                }
            },
            {"player": {"id": 654, "name": "Jeremy Doku", "pos": "F", "grid": "5:3"}},
        ],
        "substitutes": [
            {"player": {"id": 999, "name": "Stefan Ortega", "pos": "G", "grid": None}},
        ],
    }

    parse_and_store_lineup("fixture_test_001", "50", mock_api_team)
    print("Mock lineup stored.")
