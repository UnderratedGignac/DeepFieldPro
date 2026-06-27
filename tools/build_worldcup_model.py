"""
build_worldcup_model.py — Build squad quality metrics for WC 2026 model.
Run:  .venv\Scripts\python.exe tools\build_worldcup_model.py
"""

import csv
import json
import os
from collections import defaultdict

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
MODEL_DIR = os.path.join(BASE_DIR, "models")
MATCH_LOGS = os.path.join(DATA_DIR, "world_cup_players_match_logs_global.csv")
OUTPUT = os.path.join(MODEL_DIR, "worldcup_model.json")

NATION_MAP = {
    "ARG": "Argentina",
    "AUS": "Australia",
    "AUT": "Austria",
    "BEL": "Belgium",
    "BOL": "Bolivia",
    "BRA": "Brazil",
    "BUR": "Burkina Faso",
    "CMR": "Cameroon",
    "CAN": "Canada",
    "CPV": "Cabo Verde",
    "CHI": "Chile",
    "COL": "Colombia",
    "COD": "Congo DR",
    "CRC": "Costa Rica",
    "CRO": "Croatia",
    "CUR": "Curacao",
    "CZE": "Czech Republic",
    "DEN": "Denmark",
    "ECU": "Ecuador",
    "EGY": "Egypt",
    "ENG": "England",
    "ESP": "Spain",
    "FRA": "France",
    "GER": "Germany",
    "GHA": "Ghana",
    "HON": "Honduras",
    "HUN": "Hungary",
    "IRN": "Iran",
    "ITA": "Italy",
    "JAM": "Jamaica",
    "JPN": "Japan",
    "JOR": "Jordan",
    "KOR": "South Korea",
    "MAR": "Morocco",
    "MEX": "Mexico",
    "MLI": "Mali",
    "NED": "Netherlands",
    "NGA": "Nigeria",
    "NOR": "Norway",
    "NZL": "New Zealand",
    "PAN": "Panama",
    "PAR": "Paraguay",
    "POL": "Poland",
    "POR": "Portugal",
    "QAT": "Qatar",
    "SCO": "Scotland",
    "SEN": "Senegal",
    "SRB": "Serbia",
    "SUI": "Switzerland",
    "SWE": "Sweden",
    "TUN": "Tunisia",
    "TUR": "Turkey",
    "UAE": "United Arab Emirates",
    "UKR": "Ukraine",
    "URU": "Uruguay",
    "USA": "USA",
    "UZB": "Uzbekistan",
    "WAL": "Wales",
    "RSA": "South Africa",
    "KSA": "Saudi Arabia",
    "CIV": "Ivory Coast",
}


def aggregate_squad_quality():
    nation_stats = defaultdict(
        lambda: {
            "goals": 0,
            "assists": 0,
            "shots": 0,
            "sot": 0,
            "tackles": 0,
            "interceptions": 0,
            "minutes": 0,
            "players": set(),
        }
    )
    if not os.path.exists(MATCH_LOGS):
        print(
            f"[!] {MATCH_LOGS} not found — squad quality will be empty (Elo-only model)"
        )
        return {}
    with open(MATCH_LOGS, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            game = row.get("game_", "")
            if "SeasonAggregate" in game or not game:
                continue
            try:
                mins = float(row.get("min_", 0) or 0)
            except (ValueError, TypeError):
                continue
            if mins <= 0:
                continue
            nation_code = row.get("Nation", "").strip()
            if not nation_code or nation_code not in NATION_MAP:
                continue
            canonical = NATION_MAP[nation_code]
            s = nation_stats[canonical]
            player = row.get("player_", "")
            if player:
                s["players"].add(player)
            s["minutes"] += mins
            try:
                s["goals"] += float(row.get("Performance_Gls", 0) or 0)
                s["assists"] += float(row.get("Performance_Ast", 0) or 0)
                s["shots"] += float(row.get("Performance_Sh", 0) or 0)
                s["sot"] += float(row.get("Performance_SoT", 0) or 0)
                s["tackles"] += float(row.get("Performance_TklW", 0) or 0)
                s["interceptions"] += float(row.get("Performance_Int", 0) or 0)
            except (ValueError, TypeError):
                pass
    result = {}
    for nation, s in nation_stats.items():
        total_mins = s["minutes"]
        if total_mins < 900:
            continue
        n90 = total_mins / 90.0
        result[nation] = {
            "n_players": len(s["players"]),
            "total_minutes": int(total_mins),
            "g_p90": round(s["goals"] / n90, 3),
            "a_p90": round(s["assists"] / n90, 3),
            "xg_p90": round(s["goals"] / n90 * 0.85, 3),
            "xa_p90": round(s["assists"] / n90 * 0.85, 3),
            "sh_p90": round(s["shots"] / n90, 2),
            "sot_p90": round(s["sot"] / n90, 2),
            "tkl_p90": round(s["tackles"] / n90, 2),
            "int_p90": round(s["interceptions"] / n90, 2),
        }
    return result


def main():
    print("Building World Cup 2026 model...\n")
    sq = aggregate_squad_quality()
    print(f"Squad quality computed for {len(sq)} nations:")
    ranked = sorted(sq.items(), key=lambda x: x[1].get("g_p90", 0), reverse=True)
    for nation, stats in ranked[:15]:
        print(
            f"  {nation:20s}  g_p90={stats['g_p90']:.2f}  "
            f"players={stats['n_players']}  mins={stats['total_minutes']}"
        )
    if len(ranked) > 15:
        print(f"  ... and {len(ranked) - 15} more nations")
    os.makedirs(MODEL_DIR, exist_ok=True)
    model_data = {"squad_quality": sq, "fifa_ratings": {}, "n_nations": len(sq)}
    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(model_data, f, indent=2)
    print(f"\nSaved World Cup model -> {os.path.relpath(OUTPUT)}")
    print(f"  {len(sq)} nations with squad quality data")


if __name__ == "__main__":
    main()
