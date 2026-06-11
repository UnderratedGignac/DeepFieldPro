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
                    kickoff_iso = datetime.datetime.fromtimestamp(
                        e["startTimestamp"], datetime.timezone.utc
                    ).isoformat()

                    status_code = "NS"
                    if e["status"]["type"] == "inprogress":
                        status_code = "1H"
                    elif e["status"]["type"] == "finished":
                        status_code = "FT"

                    home_score = e.get("homeScore", {}).get("normaltime", e.get("homeScore", {}).get("current", None))
                    away_score = e.get("awayScore", {}).get("normaltime", e.get("awayScore", {}).get("current", None))

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
                if not formatted_fixtures:
                    print("[!] Sofascore fixtures empty! Falling back to Betarabia dummy fixtures...")
                    import hashlib
                    from src.live_predictions_daemon import fetch_betarabia_odds
                    b_odds, _ = fetch_betarabia_odds()
                    for b_name in b_odds.keys():
                        if ' vs ' in b_name:
                            h, a = b_name.split(' vs ', 1)
                            fid = int(hashlib.md5(b_name.encode()).hexdigest(), 16) % 100000000
                            formatted_fixtures.append({
                                "fixture": {
                                    "id": fid,
                                    "date": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                                    "status": {"short": "NS"},
                                    "home_score": None,
                                    "away_score": None
                                },
                                "league": {"name": "Betarabia"},
                                "teams": {
                                    "home": {"name": h},
                                    "away": {"name": a}
                                }
                            })
                    print(f"[!] Rebuilt {len(formatted_fixtures)} dummy fixtures from Betarabia.")

                return formatted_fixtures
        except Exception as e:
            if "used by another process" in str(e) and attempt < 2:
                print(f"[*] Driver locked, retrying in 3s... (Attempt {attempt+1})")
                time.sleep(3)
                continue
            print(f"[!] Scraper Error (Fixtures): {e}")

    # Fallback to Betarabia if all attempts fail
    formatted_fixtures = []
    print("[!] Sofascore completely failed. Falling back to Betarabia dummy fixtures...")
    try:
        import hashlib
        from src.live_predictions_daemon import fetch_betarabia_odds
        b_odds, _ = fetch_betarabia_odds()
        for b_name in b_odds.keys():
            if ' vs ' in b_name:
                h, a = b_name.split(' vs ', 1)
                fid = int(hashlib.md5(b_name.encode()).hexdigest(), 16) % 100000000
                formatted_fixtures.append({
                    "fixture": {
                        "id": fid,
                        "date": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                        "status": {"short": "NS"},
                        "home_score": None,
                        "away_score": None
                    },
                    "league": {"name": "Betarabia"},
                    "teams": {
                        "home": {"name": h},
                        "away": {"name": a}
                    }
                })
        print(f"[!] Rebuilt {len(formatted_fixtures)} dummy fixtures from Betarabia.")
    except Exception as e:
        print(f"[!] Fallback to Betarabia failed: {e}")
        
    return formatted_fixtures


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
