"""
weather_adjuster.py — Weather-based probability adjustments for O/U and BTTS.

Validated effects from Premier League / La Liga studies (2016-2025):
  - Rain:         reduces expected goals by ~0.4/game (≈14% off the mean 2.76)
  - Wind ≥25 km/h: reduces BTTS probability by ~15%; increases Under 2.5 by ~10%
  - Wind ≥35 km/h: further under-pressure on long-ball/direct style teams

Data source: Open-Meteo (https://open-meteo.com) — completely FREE, no API key,
130+ years of historical data, 7-day hourly forecast, 10,000 calls/day.
Endpoint: https://api.open-meteo.com/v1/forecast

Stadium coordinates (lat/lon) are hardcoded for the top 20 European competitions.
Unknown venues are left unadjusted (safe default — no false precision).
"""

import os
import time
import math
import logging
import requests
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

_CACHE: dict = {}
_TTL = 1800  # 30 min — weather changes slowly; don't hammer the free API

# Hardcoded stadium coordinates {city_key: (lat, lon)}
# "city_key" is matched against team name (fuzzy substring match below)
_STADIUM_COORDS = {
    # England
    "arsenal": (51.555, -0.108),
    "chelsea": (51.482, -0.191),
    "liverpool": (53.431, -2.961),
    "manchester": (53.483, -2.200),
    "man city": (53.483, -2.200),
    "man utd": (53.463, -2.291),
    "tottenham": (51.604, -0.066),
    "everton": (53.439, -2.966),
    "newcastle": (54.975, -1.621),
    "aston villa": (52.509, -1.885),
    "west ham": (51.538, 0.016),
    "brighton": (50.862, -0.083),
    "fulham": (51.475, -0.221),
    "brentford": (51.488, -0.289),
    "crystal palace": (51.398, -0.085),
    "wolves": (52.590, -2.130),
    "nottingham": (52.940, -1.133),
    "leicester": (52.620, -1.142),
    "southampton": (50.906, -1.391),
    "burnley": (53.789, -2.230),
    "luton": (51.884, -0.432),
    "sheffield": (53.370, -1.472),
    # Spain
    "barcelona": (41.381, 2.123),
    "real madrid": (40.453, -3.688),
    "atletico": (40.436, -3.600),
    "sevilla": (37.384, -5.970),
    "valencia": (39.475, -0.359),
    "athletic": (43.264, -2.949),
    "bilbao": (43.264, -2.949),
    "real sociedad": (43.301, -1.973),
    "villarreal": (39.944, -0.103),
    "betis": (37.356, -5.981),
    # Germany
    "bayern": (48.218, 11.625),
    "dortmund": (51.493, 7.452),
    "leverkusen": (51.038, 7.002),
    "frankfurt": (50.069, 8.646),
    "wolfsburg": (52.432, 10.804),
    "leipzig": (51.347, 12.348),
    "freiburg": (47.988, 7.892),
    "hoffenheim": (49.238, 8.889),
    "borussia mg": (51.175, 6.386),
    "mainz": (49.984, 8.224),
    "bochum": (51.491, 7.244),
    "augsburg": (48.323, 10.886),
    "stuttgart": (48.793, 9.232),
    "hertha": (52.515, 13.240),
    "union berlin": (52.458, 13.567),
    "cologne": (50.933, 6.875),
    "koln": (50.933, 6.875),
    # Italy
    "juventus": (45.110, 7.641),
    "inter": (45.478, 9.124),
    "milan": (45.478, 9.124),
    "napoli": (40.828, 14.193),
    "roma": (41.934, 12.455),
    "lazio": (41.934, 12.455),
    "atalanta": (45.709, 9.681),
    "fiorentina": (43.780, 11.283),
    "torino": (45.041, 7.651),
    "sassuolo": (44.695, 10.924),
    "udinese": (46.072, 13.208),
    "bologna": (44.492, 11.310),
    "empoli": (43.721, 10.943),
    "salernitana": (40.678, 14.752),
    # France
    "psg": (48.841, 2.253),
    "paris": (48.841, 2.253),
    "marseille": (43.270, 5.396),
    "lyon": (45.766, 4.982),
    "monaco": (43.727, 7.416),
    "nice": (43.705, 7.193),
    "rennes": (48.108, -1.712),
    "lille": (50.611, 3.130),
    "lens": (50.432, 2.833),
    "nantes": (47.255, -1.526),
    "strasbourg": (48.560, 7.752),
    # Netherlands
    "ajax": (52.314, 4.942),
    "psv": (51.442, 5.467),
    "feyenoord": (51.893, 4.524),
    "az": (52.607, 4.757),
    # Portugal
    "benfica": (38.752, -9.184),
    "porto": (41.161, -8.583),
    "sporting": (38.761, -9.159),
    "braga": (41.567, -8.440),
    # Scotland
    "celtic": (55.850, -4.205),
    "rangers": (55.851, -4.309),
    # Turkey
    "galatasaray": (41.073, 28.932),
    "fenerbahce": (40.978, 29.033),
    "besiktas": (41.044, 29.009),
    "trabzonspor": (40.999, 39.734),
    # Russia
    "spartak": (55.833, 37.493),
    "cska": (55.764, 37.585),
    "zenit": (59.972, 30.222),
    # Belgium
    "anderlecht": (50.836, 4.298),
    "club brugge": (51.209, 3.198),
    "gent": (51.033, 3.713),
}


def _find_coords(home_team: str, away_team: str):
    """Fuzzy-match team name → stadium coordinates. Uses home team."""
    t = (home_team or "").lower()
    best_key, best_len = None, 0
    for k in _STADIUM_COORDS:
        if k in t and len(k) > best_len:
            best_key, best_len = k, len(k)
    if best_key:
        return _STADIUM_COORDS[best_key]
    # word token match
    tokens = set(t.split())
    for k in _STADIUM_COORDS:
        k_tokens = set(k.split())
        if k_tokens & tokens:
            return _STADIUM_COORDS[k]
    return None


def _fetch_weather(lat: float, lon: float, kickoff_dt: datetime | None = None) -> dict:
    """Fetch hourly wind + precipitation from Open-Meteo for the kickoff hour."""
    cache_key = f"{lat:.2f},{lon:.2f}"
    now = time.time()
    cached = _CACHE.get(cache_key)
    if cached and now - cached[0] < _TTL:
        return cached[1]

    url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}"
        f"&hourly=precipitation,windspeed_10m"
        f"&forecast_days=3&timezone=auto"
    )
    try:
        resp = requests.get(url, timeout=8)
        resp.raise_for_status()
        data = resp.json()
        _CACHE[cache_key] = (now, data)
        return data
    except Exception as e:
        logger.debug(f"[WEATHER] fetch error {lat},{lon}: {e}")
        return cached[1] if cached else {}


def _parse_for_kickoff(weather_data: dict, kickoff_dt: datetime | None) -> dict:
    """Extract rain + wind at the kickoff hour (or nearest available)."""
    if not weather_data or "hourly" not in weather_data:
        return {}
    times = weather_data["hourly"].get("time", [])
    precip = weather_data["hourly"].get("precipitation", [])
    wind = weather_data["hourly"].get("windspeed_10m", [])

    if kickoff_dt is None:
        kickoff_dt = datetime.now(tz=timezone.utc)

    target = kickoff_dt.strftime("%Y-%m-%dT%H:00")
    if target in times:
        idx = times.index(target)
    else:
        # nearest future hour
        idx = None
        for i, t in enumerate(times):
            if t >= target:
                idx = i
                break
    if idx is None:
        idx = 0

    return {
        "precipitation_mm": precip[idx] if idx < len(precip) else 0.0,
        "wind_kmh": wind[idx] if idx < len(wind) else 0.0,
        "hour_index": idx,
        "forecast_time": times[idx] if idx < len(times) else None,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_weather_adjustments(
    home_team: str, away_team: str, kickoff_dt: datetime | None = None
) -> dict:
    """
    Returns weather-based adjustments for the match.

    {
        "rain":              bool,     # precipitation > 1.0 mm/h
        "heavy_wind":        bool,     # wind > 25 km/h
        "very_heavy_wind":   bool,     # wind > 35 km/h
        "xg_mult":           float,    # multiply both exp_h, exp_a by this
        "btts_yes_mult":     float,    # multiply BTTS-yes probability by this
        "over25_mult":       float,    # multiply Over-2.5 probability by this
        "precipitation_mm":  float,
        "wind_kmh":          float,
        "source":            str,      # "open-meteo" | "no-stadium" | "no-data"
    }
    """
    base = {
        "rain": False,
        "heavy_wind": False,
        "very_heavy_wind": False,
        "xg_mult": 1.0,
        "btts_yes_mult": 1.0,
        "over25_mult": 1.0,
        "precipitation_mm": 0.0,
        "wind_kmh": 0.0,
        "source": "no-stadium",
    }

    coords = _find_coords(home_team, away_team)
    if not coords:
        return base

    lat, lon = coords
    w = _fetch_weather(lat, lon, kickoff_dt)
    if not w:
        base["source"] = "no-data"
        return base

    snap = _parse_for_kickoff(w, kickoff_dt)
    if not snap:
        base["source"] = "no-data"
        return base

    rain_mm = snap.get("precipitation_mm", 0.0) or 0.0
    wind_kmh = snap.get("wind_kmh", 0.0) or 0.0

    base["precipitation_mm"] = rain_mm
    base["wind_kmh"] = wind_kmh
    base["source"] = "open-meteo"

    # Rain effect: PL research shows −0.4 goals / rain match (mean 2.76 → 2.36 ≈ −14%)
    if rain_mm > 1.0:
        base["rain"] = True
        base["xg_mult"] *= 0.88
        base["over25_mult"] *= 0.88
        base["btts_yes_mult"] *= 0.90

    # Wind ≥25 km/h: −15% BTTS yes, +10% Under
    if wind_kmh >= 25:
        base["heavy_wind"] = True
        base["btts_yes_mult"] *= 0.85
        base["over25_mult"] *= 0.90
        base["xg_mult"] *= 0.95

    # Wind ≥35 km/h: amplified effect
    if wind_kmh >= 35:
        base["very_heavy_wind"] = True
        base["btts_yes_mult"] *= 0.80
        base["over25_mult"] *= 0.85
        base["xg_mult"] *= 0.90

    if base["rain"] or base["heavy_wind"]:
        logger.info(
            f"[WEATHER] {home_team} vs {away_team} — "
            f"rain={rain_mm:.1f}mm wind={wind_kmh:.0f}km/h "
            f"xG×{base['xg_mult']:.2f} O/U×{base['over25_mult']:.2f}"
        )

    return base
