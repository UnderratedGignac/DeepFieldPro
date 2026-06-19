import json
import hashlib
import datetime
import time
import requests

from seleniumbase import SB  # still used by lineup / stats helpers below

_UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "application/json",
}

_ESPN_BASE = "https://site.api.espn.com/apis/site/v2/sports/soccer"

# Same league coverage as free_results_scraper — over-listing is harmless (unknown slugs
# return 0 events). Remove usa.nwsl (women's) since we only want men's fixtures.
_ESPN_LEAGUES = [
    "eng.1",
    "eng.2",
    "eng.3",
    "eng.4",
    "eng.fa",
    "eng.league_cup",
    "esp.1",
    "esp.2",
    "esp.copa_del_rey",
    "ita.1",
    "ita.2",
    "ita.coppa_italia",
    "ger.1",
    "ger.2",
    "ger.dfb_pokal",
    "fra.1",
    "fra.2",
    "fra.coupe_de_france",
    "ned.1",
    "ned.2",
    "por.1",
    "por.2",
    "sco.1",
    "sco.2",
    "sui.1",
    "aut.1",
    "bel.1",
    "gre.1",
    "tur.1",
    "rus.1",
    "ukr.1",
    "den.1",
    "nor.1",
    "swe.1",
    "pol.1",
    "cze.1",
    "cro.1",
    "rou.1",
    "srb.1",
    "hun.1",
    "bul.1",
    "svk.1",
    "slv.1",
    "isr.1",
    "cyp.1",
    "fin.1",
    "usa.1",
    "usa.usl.1",
    "mex.1",
    "mex.2",
    "bra.1",
    "bra.2",
    "arg.1",
    "arg.2",
    "chi.1",
    "col.1",
    "uru.1",
    "per.1",
    "ecu.1",
    "par.1",
    "ven.1",
    "bol.1",
    "crc.1",
    "gua.1",
    "hon.1",
    "jpn.1",
    "kor.1",
    "chn.1",
    "aus.1",
    "ksa.1",
    "qat.1",
    "are.1",
    "ind.1",
    "idn.1",
    "tha.1",
    "mys.1",
    "rsa.1",
    "egy.1",
    "mar.1",
    "nga.1",
    "tun.1",
    "fifa.world",
    "fifa.friendly",
    "fifa.cwc",
    "uefa.champions",
    "uefa.europa",
    "uefa.europa.conf",
    "uefa.nations",
    "conmebol.libertadores",
    "conmebol.sudamericana",
    "concacaf.champions",
    "concacaf.league",
    "afc.champions",
    "caf.champions_league",
    "fifa.worldq.conmebol",
    "fifa.worldq.uefa",
    "fifa.worldq.concacaf",
    "fifa.worldq.afc",
    "fifa.worldq.caf",
]

# Cache ESPN results for 5 minutes — the daemon loops every ~30s but fixtures
# don't change that fast; this avoids 80+ HTTP calls every cycle.
_fixture_cache = {}
_FIXTURE_CACHE_TTL = 300  # seconds


def _espn_fixtures_today():
    """
    Fetch today's football fixtures from ESPN (upcoming + live + finished).
    Returns a list of fixture dicts in the same format the daemon expects.
    No Playwright, no Cloudflare — plain JSON over requests.
    """
    today_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    cached = _fixture_cache.get(today_str)
    if cached and (time.time() - cached[0]) < _FIXTURE_CACHE_TTL:
        return list(cached[1])

    compact = today_str.replace("-", "")
    seen = set()
    fixtures = []

    for lg in _ESPN_LEAGUES:
        try:
            r = requests.get(
                f"{_ESPN_BASE}/{lg}/scoreboard",
                headers=_UA,
                params={"dates": compact},
                timeout=5,
            )
            if r.status_code != 200:
                continue
            data = r.json()
            league_name = (data.get("leagues") or [{}])[0].get("name") or lg

            # Skip women's leagues that sneak through
            if any(
                kw in league_name.lower()
                for kw in ("women", "female", "feminin", "nwsl")
            ):
                continue

            for e in data.get("events") or []:
                comp = (e.get("competitions") or [{}])[0]
                cs = comp.get("competitors") or []
                if len(cs) != 2:
                    continue
                home = next((c for c in cs if c.get("homeAway") == "home"), None)
                away = next((c for c in cs if c.get("homeAway") == "away"), None)
                if not home or not away:
                    continue
                hn = (home.get("team") or {}).get("displayName")
                an = (away.get("team") or {}).get("displayName")
                if not hn or not an:
                    continue

                key = f"{hn} vs {an}"
                if key in seen:
                    continue
                seen.add(key)

                # Map ESPN status to our codes
                st = comp.get("status") or {}
                st_type = st.get("type") or {}
                period = st.get("period", 0)
                if st_type.get("completed"):
                    status_short = "FT"
                elif st_type.get("name") == "STATUS_HALFTIME":
                    status_short = "HT"
                elif st_type.get("name") == "STATUS_IN_PROGRESS":
                    status_short = "2H" if period >= 2 else "1H"
                else:
                    status_short = "NS"

                # Only read scores for live/finished matches — ESPN returns "0" for
                # upcoming fixtures, which would incorrectly show as 0-0 on the dashboard.
                if status_short == "NS":
                    hs, as_ = None, None
                else:
                    try:
                        hs = (
                            int(home["score"])
                            if home.get("score") not in (None, "")
                            else None
                        )
                    except (TypeError, ValueError):
                        hs = None
                    try:
                        as_ = (
                            int(away["score"])
                            if away.get("score") not in (None, "")
                            else None
                        )
                    except (TypeError, ValueError):
                        as_ = None

                kickoff_iso = (
                    comp.get("date") or e.get("date") or today_str + "T00:00:00+00:00"
                )

                try:
                    fid = int(e.get("id", 0))
                except (TypeError, ValueError):
                    fid = int(hashlib.md5(key.encode()).hexdigest(), 16) % 100000000

                fixtures.append(
                    {
                        "fixture": {
                            "id": fid,
                            "date": kickoff_iso,
                            "status": {"short": status_short},
                            "home_score": hs,
                            "away_score": as_,
                        },
                        "league": {"name": league_name},
                        "teams": {
                            "home": {"name": hn},
                            "away": {"name": an},
                        },
                    }
                )
        except Exception:
            continue

    _fixture_cache[today_str] = (time.time(), list(fixtures))
    return fixtures


def _betarabia_fixture_fallback():
    """
    Build fixture list from Betarabia odds_stream.db when all real sources fail.
    Has real kickoff times and league names from the scraper, but no live scores.
    """
    from src.live_predictions_daemon import fetch_betarabia_odds

    fixtures = []
    try:
        b_odds, _ = fetch_betarabia_odds()
        for b_name, b_info in b_odds.items():
            if " vs " in b_name:
                h, a = b_name.split(" vs ", 1)
                fid = int(hashlib.md5(b_name.encode()).hexdigest(), 16) % 100000000
                info = b_info or {}
                fixtures.append(
                    {
                        "fixture": {
                            "id": fid,
                            "date": info.get("kickoff")
                            or datetime.datetime.now(datetime.timezone.utc).isoformat(),
                            "status": {"short": info.get("status") or "NS"},
                            "home_score": None,
                            "away_score": None,
                        },
                        "league": {"name": info.get("league") or "Betarabia"},
                        "teams": {
                            "home": {"name": h},
                            "away": {"name": a},
                        },
                    }
                )
    except Exception as ex:
        print(f"[!] Betarabia fallback failed: {ex}")
    return fixtures


def get_todays_fixtures_free():
    """
    Merge ESPN + Betarabia fixtures for maximum coverage:
    - ESPN provides real live scores and granular status (1H/HT/2H/FT) for the leagues
      it covers (top European, World Cup, major Americas, Asia/Africa).
    - Betarabia's odds_stream.db is used to top up with any match ESPN missed (minor
      leagues, niche competitions). Those extra fixtures have accurate kickoff times and
      league names from the scraper but no live scores.
    This replaces the old Sofascore→dummy-fallback chain which was permanently Cloudflare-
    blocked and could never return live scores.
    """
    espn_fixtures = []
    try:
        espn_fixtures = _espn_fixtures_today()
        print(f"[*] ESPN fixtures: {len(espn_fixtures)} matches")
    except Exception as ex:
        print(f"[!] ESPN fixture fetch error: {ex}")

    # Build a normalised lookup so we can dedup against Betarabia
    espn_pairs = set()
    for f in espn_fixtures:
        h = f["teams"]["home"]["name"].lower().strip()
        a = f["teams"]["away"]["name"].lower().strip()
        espn_pairs.add((h, a))

    # Add Betarabia fixtures that ESPN doesn't have
    betarabia_additions = []
    try:
        for f in _betarabia_fixture_fallback():
            h = f["teams"]["home"]["name"].lower().strip()
            a = f["teams"]["away"]["name"].lower().strip()
            if (h, a) not in espn_pairs:
                betarabia_additions.append(f)
        if betarabia_additions:
            print(f"[*] Betarabia additions (not in ESPN): {len(betarabia_additions)}")
    except Exception as ex:
        print(f"[!] Betarabia top-up error: {ex}")

    combined = espn_fixtures + betarabia_additions
    if combined:
        return combined

    print("[!] No fixtures from any source.")
    return []


# ---------------------------------------------------------------------------
# Lineup / stats helpers — still use Sofascore via SeleniumBase (lineups are
# fetched on-demand before kickoff, not in the hot loop, so occasional failures
# are acceptable). These are unchanged.
# ---------------------------------------------------------------------------


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
