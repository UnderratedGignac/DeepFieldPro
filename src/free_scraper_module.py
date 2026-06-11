from seleniumbase import SB
import json
import datetime
import time


def get_todays_fixtures_free():
    today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    url = f"https://api.sofascore.com/api/v1/sport/football/scheduled-events/{today}"

    for attempt in range(3):
        try:
            with SB(uc=True, headless=True) as sb:
                sb.open(url)
                time.sleep(1)  # Let Cloudflare bypass
                content = sb.execute_script("return document.body.innerText;")
                data = json.loads(content)
                events = data.get("events", [])

                # Format to match the old API structure for seamless integration
                formatted_fixtures = []
                for e in events:
                    # Filter out women's matches
                    tournament_name = e.get("tournament", {}).get("name", "").lower()
                    category_name = (
                        e.get("tournament", {}).get("category", {}).get("name", "").lower()
                    )
                    home_name = e.get("homeTeam", {}).get("name", "").lower()
                    away_name = e.get("awayTeam", {}).get("name", "").lower()

                    is_women = False
                    for kw in [
                        "women",
                        "female",
                        "feminin",
                        "femenil",
                        "femenino",
                        "femminile",
                        "women's",
                    ]:
                        if (
                            kw in tournament_name
                            or kw in category_name
                            or kw in home_name
                            or kw in away_name
                        ):
                            is_women = True
                            break
                    if (
                        home_name.endswith(" (w)")
                        or home_name.endswith(" w")
                        or away_name.endswith(" (w)")
                        or away_name.endswith(" w")
                    ):
                        is_women = True

                    if is_women:
                        continue

                    # Sofascore uses Unix timestamps
                    kickoff_ts = e["startTimestamp"]
                    now_ts = time.time()
                    
                    # HARD FILTER: Skip matches that started more than 4 hours ago
                    if (now_ts - kickoff_ts) > (4 * 3600):
                        continue

                    kickoff_iso = datetime.datetime.fromtimestamp(
                        kickoff_ts, datetime.timezone.utc
                    ).isoformat()

                    status_code = "NS"
                    if e["status"]["type"] == "inprogress":
                        status_code = "1H"
                    elif e["status"]["type"] == "finished":
                        status_code = "FT"

                    home_score = e.get("homeScore", {}).get("current", None)
                    away_score = e.get("awayScore", {}).get("current", None)

                    formatted_fixtures.append(
                        {
                            "fixture": {
                                "id": e["id"],
                                "date": kickoff_iso,
                                "status": {"short": status_code},
                                "home_score": home_score,
                                "away_score": away_score,
                            },
                            "league": {"name": e["tournament"]["name"]},
                            "teams": {
                                "home": {"name": e["homeTeam"]["name"]},
                                "away": {"name": e["awayTeam"]["name"]},
                            },
                        }
                    )
                return formatted_fixtures
        except Exception as e:
            if "used by another process" in str(e) and attempt < 2:
                print(f"[*] Driver locked, retrying in 3s... (Attempt {attempt+1})")
                time.sleep(3)
                continue
            print(f"[!] Scraper Error (Fixtures): {e}")
            return []
    return []


def get_fixture_lineups_free(fixture_id):
    url = f"https://api.sofascore.com/api/v1/event/{fixture_id}/lineups"

    with SB(uc=True, headless=True) as sb:
        sb.open(url)
        time.sleep(1)
        try:
            content = sb.execute_script("return document.body.innerText;")
            data = json.loads(content)

            if "home" not in data or "away" not in data:
                return []

            # Map Sofascore lineups back to API-Football format
            home_xi = []
            for p in data["home"].get("players", []):
                if not p.get("substitute"):
                    home_xi.append({"player": {"name": p["player"]["name"]}})

            away_xi = []
            for p in data["away"].get("players", []):
                if not p.get("substitute"):
                    away_xi.append({"player": {"name": p["player"]["name"]}})

            return [{"startXI": home_xi}, {"startXI": away_xi}]
        except Exception:
            # Most likely 404 meaning lineups not released yet
            return []


def get_fixture_stats_free(fixture_id):
    url = f"https://api.sofascore.com/api/v1/event/{fixture_id}/statistics"

    with SB(uc=True, headless=True) as sb:
        sb.open(url)
        time.sleep(1)
        try:
            content = sb.execute_script("return document.body.innerText;")
            data = json.loads(content)
            return data
        except Exception:
            return None


def get_fixture_lineups_batch(fixture_ids):
    if not fixture_ids:
        return {}
    results = {}
    with SB(uc=True, headless=True) as sb:
        for fid in fixture_ids:
            url = f"https://api.sofascore.com/api/v1/event/{fid}/lineups"
            try:
                sb.open(url)
                time.sleep(1)
                content = sb.execute_script("return document.body.innerText;")
                data = json.loads(content)
                if "home" in data and "away" in data:
                    home_xi = [
                        {"player": {"name": p["player"]["name"]}}
                        for p in data["home"].get("players", [])
                        if not p.get("substitute")
                    ]
                    away_xi = [
                        {"player": {"name": p["player"]["name"]}}
                        for p in data["away"].get("players", [])
                        if not p.get("substitute")
                    ]
                    results[fid] = [{"startXI": home_xi}, {"startXI": away_xi}]
            except Exception:
                pass
    return results
