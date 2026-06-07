"""
data_pipeline.py — DeepFieldPro World Cup 2026 Player Data Pipeline
=====================================================================
Fetches real player data for all World Cup 2026 participants from:
  1. StatsBomb Open Data  (via statsbombpy - no key needed, WC 2022 historical)
  2. API-Football         (live squads & stats, 100 req/day free tier, key in .env)
  3. TheSportsDB          (player position/age enrichment, no key needed)

All data saved to:
  - data/odds_stream.db  (team_stats + player_stats tables)
  - data/worldcup_players.csv  (flat CSV cache)

Usage:
  python src/data_pipeline.py

Set API_FOOTBALL_KEY in .env to enable API-Football source.
"""

import os
import json
import time
import sqlite3
import logging
import datetime
import requests
import pandas as pd

# Load .env
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
except ImportError:
    pass

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# ── Paths ───────────────────────────────────────────────────────────────────
BASE_DIR   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR   = os.path.join(BASE_DIR, "data")
DB_PATH    = os.path.join(DATA_DIR, "odds_stream.db")
CSV_PATH   = os.path.join(DATA_DIR, "worldcup_players.csv")
CACHE_APIF = os.path.join(DATA_DIR, "api_football_cache")
CACHE_TSDB = os.path.join(DATA_DIR, "thesportsdb_cache")

os.makedirs(CACHE_APIF, exist_ok=True)
os.makedirs(CACHE_TSDB, exist_ok=True)

# ── API-Football config ─────────────────────────────────────────────────────
API_FOOTBALL_KEY = os.environ.get("API_FOOTBALL_KEY", "")
API_FOOTBALL_BASE = "https://v3.football.api-sports.io"
API_FOOTBALL_HEADERS = {"x-apisports-key": API_FOOTBALL_KEY}

# WC 2026 in API-Football: league_id=1, season=2026
WC_LEAGUE_ID = 1
WC_SEASON    = 2026

# ── StatsBomb WC 2022: competition_id=43, season_id=106 ────────────────────
SB_COMPETITION_ID = 43
SB_SEASON_ID      = 106  # FIFA World Cup 2022


# ===========================================================================
# DB SCHEMA
# ===========================================================================

def init_db(conn: sqlite3.Connection):
    """Create team_stats and player_stats tables if they don't exist."""
    c = conn.cursor()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS team_stats (
        team_id TEXT PRIMARY KEY,
        team_name TEXT,
        nation_code TEXT,
        league TEXT,
        form_last_5 REAL DEFAULT 0,
        xg_for_p90 REAL DEFAULT 0,
        xg_against_p90 REAL DEFAULT 0,
        possession_pct REAL DEFAULT 50,
        corners_for_p90 REAL DEFAULT 4.5,
        yellow_cards_p90 REAL DEFAULT 1.5,
        red_cards_p90 REAL DEFAULT 0.1,
        updated_at TEXT
    );

    CREATE TABLE IF NOT EXISTS player_stats (
        player_id TEXT PRIMARY KEY,
        player_name TEXT,
        team_id TEXT,
        nation_code TEXT,
        position TEXT,
        age INTEGER DEFAULT 0,
        minutes_played INTEGER DEFAULT 0,
        goals_p90 REAL DEFAULT 0,
        assists_p90 REAL DEFAULT 0,
        xg_p90 REAL DEFAULT 0,
        xa_p90 REAL DEFAULT 0,
        shots_p90 REAL DEFAULT 0,
        sot_p90 REAL DEFAULT 0,
        passes_p90 REAL DEFAULT 0,
        tackles_p90 REAL DEFAULT 0,
        fouls_committed_p90 REAL DEFAULT 0,
        yellow_cards_p90 REAL DEFAULT 0,
        red_cards_p90 REAL DEFAULT 0,
        data_source TEXT,
        updated_at TEXT
    );
    """)
    conn.commit()
    logger.info("[DB] Schema initialised.")


def upsert_player(conn: sqlite3.Connection, p: dict):
    conn.execute("""
        INSERT OR REPLACE INTO player_stats (
            player_id, player_name, team_id, nation_code, position, age,
            minutes_played, goals_p90, assists_p90, xg_p90, xa_p90,
            shots_p90, sot_p90, passes_p90, tackles_p90,
            fouls_committed_p90, yellow_cards_p90, red_cards_p90,
            data_source, updated_at
        ) VALUES (
            :player_id, :player_name, :team_id, :nation_code, :position, :age,
            :minutes_played, :goals_p90, :assists_p90, :xg_p90, :xa_p90,
            :shots_p90, :sot_p90, :passes_p90, :tackles_p90,
            :fouls_committed_p90, :yellow_cards_p90, :red_cards_p90,
            :data_source, :updated_at
        )
    """, p)


def upsert_team(conn: sqlite3.Connection, t: dict):
    conn.execute("""
        INSERT OR REPLACE INTO team_stats (
            team_id, team_name, nation_code, league, updated_at
        ) VALUES (:team_id, :team_name, :nation_code, :league, :updated_at)
    """, t)


def safe_p90(value, total_minutes, default=0.0) -> float:
    """Convert raw count to per-90 rate. Never divides by zero."""
    mins = max(float(total_minutes), 1.0)
    try:
        return round(float(value or 0) / (mins / 90), 4)
    except Exception:
        return default


def now_str() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


# ===========================================================================
# SOURCE 1: StatsBomb Open Data (WC 2022)
# ===========================================================================

def fetch_statsbomb(conn: sqlite3.Connection) -> int:
    """
    Pull World Cup 2022 player event data using statsbombpy.
    Aggregates per-match stats for each player across all WC 2022 matches.
    Returns number of players inserted.
    """
    logger.info("[StatsBomb] Starting WC 2022 data fetch...")
    try:
        from statsbombpy import sb
    except ImportError:
        logger.warning("[StatsBomb] statsbombpy not installed. Skipping.")
        return 0

    try:
        matches = sb.matches(competition_id=SB_COMPETITION_ID, season_id=SB_SEASON_ID)
        logger.info(f"[StatsBomb] Found {len(matches)} WC 2022 matches.")
    except Exception as e:
        logger.error(f"[StatsBomb] Failed to fetch matches: {e}")
        return 0

    # Accumulate player stats across all matches
    player_rows: dict = {}  # player_id -> aggregated stats dict

    for _, match_row in matches.iterrows():
        match_id = match_row["match_id"]
        try:
            lineups = sb.lineups(match_id=match_id)
            events  = sb.events(match_id=match_id, split=False, flatten_attrs=True)
        except Exception as e:
            logger.debug(f"[StatsBomb] match {match_id} failed: {e}")
            continue

        # Process each team's lineup
        for team_name, lineup_df in lineups.items():
            if not isinstance(lineup_df, pd.DataFrame):
                continue
            for _, player_row in lineup_df.iterrows():
                pid   = str(player_row.get("player_id", ""))
                pname = str(player_row.get("player_name", "")).strip()
                pos   = str(player_row.get("positions", [{}])[0].get("position", "MID") if player_row.get("positions") else "MID")

                # Map StatsBomb positions to simple 3-letter codes
                pos = _map_sb_position(pos)

                if not pid or not pname:
                    continue

                # Filter player's events
                try:
                    p_events = events[events["player_id"] == int(pid)] if "player_id" in events.columns else pd.DataFrame()
                except Exception:
                    p_events = pd.DataFrame()

                # Calculate minutes (from substitution data or default)
                mins = _calc_minutes(player_row, events if "player_id" in events.columns else pd.DataFrame(), match_id)

                if pid not in player_rows:
                    player_rows[pid] = {
                        "player_id":    f"sb_{pid}",
                        "player_name":  pname,
                        "team_id":      f"team_{team_name.lower().replace(' ', '_')}",
                        "nation_code":  str(player_row.get("country", {}).get("name", "UNK"))[:3].upper() if isinstance(player_row.get("country"), dict) else "UNK",
                        "position":     pos,
                        "age":          int(player_row.get("birth_date", "2000-01-01") and
                                           (2022 - int(str(player_row.get("birth_date", "2000-01-01"))[:4])))
                                        if player_row.get("birth_date") else 0,
                        "total_minutes": 0,
                        "goals":   0, "assists": 0,
                        "shots":   0, "shots_on_target": 0,
                        "xg_sum":  0.0, "xa_sum": 0.0,
                        "passes":  0, "tackles": 0,
                        "fouls":   0, "yellow_cards": 0, "red_cards": 0,
                    }

                row = player_rows[pid]
                row["total_minutes"] += mins

                if not p_events.empty:
                    # Goals
                    row["goals"]   += int(len(p_events[
                        (p_events.get("type_name", pd.Series(dtype=str)) == "Shot") &
                        (p_events.get("shot_outcome_name", pd.Series(dtype=str)) == "Goal")
                    ])) if "shot_outcome_name" in p_events.columns else 0

                    # Shots
                    row["shots"]   += int(len(p_events[p_events.get("type_name", pd.Series(dtype=str)) == "Shot"])) if "type_name" in p_events.columns else 0

                    # xG
                    if "shot_statsbomb_xg" in p_events.columns:
                        row["xg_sum"] += float(p_events["shot_statsbomb_xg"].fillna(0).sum())

                    # Assists (key_pass leading to goal)
                    if "pass_goal_assist" in p_events.columns:
                        row["assists"] += int(p_events["pass_goal_assist"].fillna(False).sum())

                    # Passes
                    row["passes"] += int(len(p_events[p_events.get("type_name", pd.Series(dtype=str)) == "Pass"])) if "type_name" in p_events.columns else 0

                    # Yellow/Red cards
                    if "foul_committed_card_name" in p_events.columns:
                        cards = p_events["foul_committed_card_name"].fillna("")
                        row["yellow_cards"] += int((cards == "Yellow Card").sum())
                        row["red_cards"]    += int((cards.isin(["Red Card", "Second Yellow"])).sum())

        # Small delay to be polite
        time.sleep(0.2)

    # Insert into DB
    count = 0
    for pid, row in player_rows.items():
        mins = max(row["total_minutes"], 1)
        p = {
            "player_id":    row["player_id"],
            "player_name":  row["player_name"],
            "team_id":      row["team_id"],
            "nation_code":  row["nation_code"],
            "position":     row["position"],
            "age":          row["age"],
            "minutes_played": int(mins),
            "goals_p90":    safe_p90(row["goals"],         mins),
            "assists_p90":  safe_p90(row["assists"],       mins),
            "xg_p90":       safe_p90(row["xg_sum"],        mins),
            "xa_p90":       0.0,
            "shots_p90":    safe_p90(row["shots"],         mins),
            "sot_p90":      safe_p90(row["shots_on_target"], mins),
            "passes_p90":   safe_p90(row["passes"],        mins),
            "tackles_p90":  safe_p90(row["tackles"],       mins),
            "fouls_committed_p90": safe_p90(row["fouls"], mins),
            "yellow_cards_p90":    safe_p90(row["yellow_cards"], mins),
            "red_cards_p90":       safe_p90(row["red_cards"],    mins),
            "data_source":  "statsbomb_wc2022",
            "updated_at":   now_str(),
        }
        try:
            upsert_player(conn, p)
            # Also upsert team record
            upsert_team(conn, {
                "team_id":    row["team_id"],
                "team_name":  row["team_id"].replace("team_", "").replace("_", " ").title(),
                "nation_code": row["nation_code"],
                "league":     "FIFA World Cup 2022",
                "updated_at": now_str(),
            })
            count += 1
        except Exception as e:
            logger.debug(f"[StatsBomb] Insert failed for {row['player_name']}: {e}")

    conn.commit()
    logger.info(f"[StatsBomb] ✅ Inserted {count} players from WC 2022.")
    return count


def _map_sb_position(pos: str) -> str:
    """Map StatsBomb position names to 3-letter codes."""
    pos_lower = pos.lower()
    if "keeper" in pos_lower or "goalkeeper" in pos_lower:
        return "GK"
    if any(x in pos_lower for x in ["back", "defender", "centre-back", "wing-back"]):
        return "DEF"
    if any(x in pos_lower for x in ["midfield", "central mid", "mid"]):
        return "MID"
    if any(x in pos_lower for x in ["forward", "winger", "striker", "attack"]):
        return "FWD"
    return "MID"


def _calc_minutes(player_row, events_df, match_id, default=90) -> int:
    """Estimate minutes played from substitution events."""
    try:
        pid = int(player_row.get("player_id", 0))
        if events_df.empty or "player_id" not in events_df.columns:
            return default

        # Check if player was subbed off
        sub_off = events_df[
            (events_df.get("substitution_replacement_id", pd.Series(dtype=object)) == pid) |
            (events_df.get("type_name", pd.Series(dtype=str)) == "Substitution") &
            (events_df.get("player_id", pd.Series(dtype=object)) == pid)
        ]
        if not sub_off.empty and "minute" in sub_off.columns:
            return int(sub_off["minute"].min())
        return default
    except Exception:
        return default


# ===========================================================================
# SOURCE 2: API-Football (WC 2026 live squads)
# ===========================================================================

def _apif_cached_get(endpoint: str, params: dict, cache_key: str) -> dict:
    """
    Fetch from API-Football with disk caching.
    Returns {} on error or if key is missing.
    """
    if not API_FOOTBALL_KEY or API_FOOTBALL_KEY in ("your_api_key_here", ""):
        return {}

    cache_file = os.path.join(CACHE_APIF, f"{cache_key}.json")
    if os.path.exists(cache_file):
        with open(cache_file) as f:
            logger.debug(f"[API-Football] Cache hit: {cache_key}")
            return json.load(f)

    url = f"{API_FOOTBALL_BASE}/{endpoint}"
    try:
        resp = requests.get(url, headers=API_FOOTBALL_HEADERS, params=params, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            with open(cache_file, "w") as f:
                json.dump(data, f)
            logger.info(f"[API-Football] Fetched {endpoint} → {cache_key}")
            time.sleep(0.5)  # polite rate limiting
            return data
        else:
            logger.warning(f"[API-Football] {resp.status_code} for {endpoint}: {resp.text[:200]}")
            return {}
    except Exception as e:
        logger.error(f"[API-Football] Request error for {endpoint}: {e}")
        return {}


def fetch_api_football(conn: sqlite3.Connection) -> int:
    """
    Fetch WC 2026 team squads from API-Football.
    Step 1: Get all WC 2026 teams
    Step 2: For each team, get squad (1 request per team)
    Returns number of players inserted.
    """
    if not API_FOOTBALL_KEY or API_FOOTBALL_KEY in ("your_api_key_here", ""):
        logger.warning("[API-Football] No valid API key found. Skipping. Add API_FOOTBALL_KEY to .env")
        return 0

    logger.info("[API-Football] Fetching WC 2026 teams...")

    # Step 1: Get all teams in WC 2026
    teams_data = _apif_cached_get(
        "teams",
        {"league": WC_LEAGUE_ID, "season": WC_SEASON},
        "wc2026_teams"
    )

    teams = teams_data.get("response", [])
    if not teams:
        logger.warning("[API-Football] No teams found for WC 2026. Check league ID or season.")
        return 0

    logger.info(f"[API-Football] Found {len(teams)} teams in WC 2026.")
    count = 0

    for team_entry in teams:
        team_info = team_entry.get("team", {})
        team_id   = str(team_info.get("id", ""))
        team_name = team_info.get("name", "Unknown")

        # Upsert team
        upsert_team(conn, {
            "team_id":    f"apif_{team_id}",
            "team_name":  team_name,
            "nation_code": team_name[:3].upper(),
            "league":     "FIFA World Cup 2026",
            "updated_at": now_str(),
        })

        # Step 2: Get squad for this team
        squad_data = _apif_cached_get(
            "players/squads",
            {"team": team_id},
            f"squad_{team_id}"
        )

        players = squad_data.get("response", [{}])
        for squad_entry in players:
            for player in squad_entry.get("players", []):
                pid      = str(player.get("id", ""))
                pname    = player.get("name", "").strip()
                pos      = _map_apif_position(player.get("position", "Midfielder"))
                age      = int(player.get("age", 0))

                if not pid or not pname:
                    continue

                # For WC 2026 squads we might not have per-90 stats directly,
                # so we default to 0 and enrich later with statsbomb historical data
                p = {
                    "player_id":    f"apif_{pid}",
                    "player_name":  pname,
                    "team_id":      f"apif_{team_id}",
                    "nation_code":  team_name[:3].upper(),
                    "position":     pos,
                    "age":          age,
                    "minutes_played": 0,
                    "goals_p90":   0.0, "assists_p90":  0.0,
                    "xg_p90":      0.0, "xa_p90":       0.0,
                    "shots_p90":   0.0, "sot_p90":      0.0,
                    "passes_p90":  0.0, "tackles_p90":  0.0,
                    "fouls_committed_p90": 0.0,
                    "yellow_cards_p90": 0.0,
                    "red_cards_p90":    0.0,
                    "data_source":  "api_football_wc2026",
                    "updated_at":   now_str(),
                }
                try:
                    upsert_player(conn, p)
                    count += 1
                except Exception as e:
                    logger.debug(f"[API-Football] Insert failed for {pname}: {e}")

    conn.commit()
    logger.info(f"[API-Football] ✅ Inserted {count} players from WC 2026 squads.")
    return count


def _map_apif_position(pos: str) -> str:
    pos_lower = pos.lower()
    if "goalkeeper" in pos_lower: return "GK"
    if "defender"   in pos_lower: return "DEF"
    if "midfielder" in pos_lower: return "MID"
    if "attacker"   in pos_lower or "forward" in pos_lower: return "FWD"
    return "MID"


# ===========================================================================
# SOURCE 3: TheSportsDB (player age/position enrichment)
# ===========================================================================

def enrich_from_thesportsdb(conn: sqlite3.Connection, max_players: int = 100) -> int:
    """
    Enrich player profiles with age and position data from TheSportsDB.
    Only updates players where age=0 (i.e., unknown).
    Limits to max_players to respect rate limits.
    """
    logger.info("[TheSportsDB] Starting player enrichment...")
    c = conn.cursor()
    c.execute("SELECT player_id, player_name FROM player_stats WHERE age = 0 LIMIT ?", (max_players,))
    players_to_enrich = c.fetchall()

    if not players_to_enrich:
        logger.info("[TheSportsDB] No players need enrichment.")
        return 0

    enriched = 0
    for player_id, player_name in players_to_enrich:
        cache_key = player_name.lower().replace(" ", "_")[:30]
        cache_file = os.path.join(CACHE_TSDB, f"{cache_key}.json")

        if os.path.exists(cache_file):
            with open(cache_file) as f:
                data = json.load(f)
        else:
            try:
                url = "https://www.thesportsdb.com/api/v1/json/3/searchplayers.php"
                resp = requests.get(url, params={"p": player_name}, timeout=10)
                data = resp.json() if resp.status_code == 200 else {}
                with open(cache_file, "w") as f:
                    json.dump(data, f)
                time.sleep(0.3)  # polite rate limiting
            except Exception as e:
                logger.debug(f"[TheSportsDB] Failed for {player_name}: {e}")
                continue

        players_list = data.get("player", [])
        if not players_list:
            continue

        player_info = players_list[0]
        str(player_info.get("strBirthLocation", "") or "")
        dob = player_info.get("dateBorn", "")
        try:
            age = 2026 - int(str(dob)[:4]) if dob else 0
        except Exception:
            age = 0

        # Map TheSportsDB position
        tsdb_pos = player_info.get("strPosition", "")
        pos = _map_tsdb_position(tsdb_pos)

        if age > 0 or pos:
            updates = []
            vals = []
            if age > 0:
                updates.append("age = ?")
                vals.append(age)
            if pos:
                updates.append("position = ?")
                vals.append(pos)
            if updates:
                vals.append(player_id)
                conn.execute(f"UPDATE player_stats SET {', '.join(updates)} WHERE player_id = ?", vals)
                enriched += 1

    conn.commit()
    logger.info(f"[TheSportsDB] ✅ Enriched {enriched} player profiles.")
    return enriched


def _map_tsdb_position(pos: str) -> str:
    pos_lower = str(pos).lower()
    if "goalkeeper" in pos_lower or "keeper" in pos_lower: return "GK"
    if "defender" in pos_lower or "back" in pos_lower:     return "DEF"
    if "midfielder" in pos_lower or "midfield" in pos_lower: return "MID"
    if "forward" in pos_lower or "striker" in pos_lower or "winger" in pos_lower: return "FWD"
    return ""


# ===========================================================================
# SOURCE 4: StatsBomb GitHub Direct (fallback if statsbombpy fails)
# ===========================================================================

def fetch_statsbomb_github_fallback(conn: sqlite3.Connection) -> int:
    """
    Fallback: Fetch WC 2022 match list directly from StatsBomb's GitHub.
    Only used if statsbombpy import fails or returns empty.
    """
    logger.info("[StatsBomb-GitHub] Attempting direct GitHub fallback...")
    url = "https://raw.githubusercontent.com/statsbomb/open-data/master/data/matches/43/106.json"
    cache_file = os.path.join(DATA_DIR, "statsbomb_wc2022_matches.json")

    if os.path.exists(cache_file):
        with open(cache_file) as f:
            matches = json.load(f)
    else:
        try:
            resp = requests.get(url, timeout=30)
            matches = resp.json()
            with open(cache_file, "w") as f:
                json.dump(matches, f)
        except Exception as e:
            logger.error(f"[StatsBomb-GitHub] Failed: {e}")
            return 0

    logger.info(f"[StatsBomb-GitHub] Found {len(matches)} matches in cache.")
    # For brevity, we insert team records from match data without full player details
    count = 0
    teams_seen = set()
    for m in matches:
        for side in ("home_team", "away_team"):
            team = m.get(side, {})
            tid  = str(team.get("home_team_id") or team.get("away_team_id", ""))
            tname = team.get("home_team_name") or team.get("away_team_name", "")
            if tid and tid not in teams_seen:
                try:
                    upsert_team(conn, {
                        "team_id":    f"sb_{tid}",
                        "team_name":  tname,
                        "nation_code": tname[:3].upper(),
                        "league":     "FIFA World Cup 2022",
                        "updated_at": now_str(),
                    })
                    teams_seen.add(tid)
                    count += 1
                except Exception:
                    pass

    conn.commit()
    logger.info(f"[StatsBomb-GitHub] ✅ Inserted {count} team records from GitHub fallback.")
    return count


# ===========================================================================
# EXPORT TO CSV
# ===========================================================================

def export_to_csv(conn: sqlite3.Connection) -> str:
    """Export full player_stats table to CSV."""
    df = pd.read_sql("SELECT * FROM player_stats ORDER BY xg_p90 DESC", conn)
    df.to_csv(CSV_PATH, index=False)
    logger.info(f"[CSV] ✅ Exported {len(df)} players to {CSV_PATH}")
    return CSV_PATH


# ===========================================================================
# MAIN
# ===========================================================================

def run_pipeline():
    """Run all data sources in order, report final counts."""
    print("\n" + "="*60)
    print("  DeepFieldPro World Cup Data Pipeline")
    print("="*60 + "\n")

    conn = sqlite3.connect(DB_PATH)
    init_db(conn)

    counts = {}

    # ── Source 1: StatsBomb (WC 2022 historical, no key needed) ─────────────
    try:
        counts["statsbomb_wc2022"] = fetch_statsbomb(conn)
    except Exception as e:
        logger.error(f"[StatsBomb] Fatal error: {e}")
        counts["statsbomb_wc2022"] = 0
        # Try GitHub fallback
        try:
            counts["statsbomb_github"] = fetch_statsbomb_github_fallback(conn)
        except Exception as e2:
            logger.error(f"[StatsBomb-GitHub] Fatal error: {e2}")
            counts["statsbomb_github"] = 0

    # ── Source 2: API-Football (WC 2026 squads) ─────────────────────────────
    try:
        counts["api_football_wc2026"] = fetch_api_football(conn)
    except Exception as e:
        logger.error(f"[API-Football] Fatal error: {e}")
        counts["api_football_wc2026"] = 0

    # ── Source 3: TheSportsDB (enrichment) ──────────────────────────────────
    try:
        counts["thesportsdb_enriched"] = enrich_from_thesportsdb(conn, max_players=150)
    except Exception as e:
        logger.error(f"[TheSportsDB] Fatal error: {e}")
        counts["thesportsdb_enriched"] = 0

    # ── Export CSV ───────────────────────────────────────────────────────────
    export_to_csv(conn)

    # ── Summary ──────────────────────────────────────────────────────────────
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM player_stats")
    total_players = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM team_stats")
    total_teams = c.fetchone()[0]
    c.execute("SELECT data_source, COUNT(*) FROM player_stats GROUP BY data_source")
    by_source = c.fetchall()
    conn.close()

    print("\n" + "="*60)
    print("  PIPELINE COMPLETE")
    print("="*60)
    print(f"  Total players in DB : {total_players}")
    print(f"  Total teams in DB   : {total_teams}")
    print("\n  Breakdown by source:")
    for src, cnt in by_source:
        print(f"    {src:<30} {cnt} players")
    print(f"\n  CSV saved to: {CSV_PATH}")
    print("="*60 + "\n")


if __name__ == "__main__":
    run_pipeline()
