"""
live_matches.py — currently IN-PLAY matches for the dashboard (no odds needed).
=============================================================================
The "Matches" tab is built from the Betarabia odds feed, which is PRE-MATCH only — once
a game kicks off Betarabia drops it, so live games (e.g. a World Cup match in play) vanish.
This pulls live games straight from Flashscore's keyless daily feed (plain requests, no
browser, no key) and shapes them as DISPLAY-ONLY dashboard cards: real score + live status,
no odds and no prediction (you can see them, the AI doesn't bet them).

Flashscore daily feed fields: AA=eventId, AB=status (1 scheduled / 2 in-play / 3 finished),
AD=start timestamp, AE/AF=home/away, AG/AH=score, ZA="Country: League" header.
"""

import time
import datetime
import requests

_H = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/125.0 Safari/537.36",
    "x-fsign": "SW9D1eZo",
    "Referer": "https://www.flashscore.com/",
}
_DAY = "https://local-global.flashscore.ninja/2/x/feed/f_1_0_3_en_1"
_REC = chr(0x00AC)
_KV = chr(0x00F7)
_LIVE = "2"  # in-play

_cache = {"ts": 0.0, "data": []}
_TTL = 45  # seconds — live scores move; keep it fresh but don't hammer


def _parse(txt):
    league = ""
    out = []
    cur = {}

    def flush():
        if not (cur.get("AE") and cur.get("AF") and cur.get("AB") == _LIVE):
            return
        try:
            hs = int(cur.get("AG"))
            as_ = int(cur.get("AH"))
        except (TypeError, ValueError):
            hs, as_ = None, None
        ts = cur.get("AD")
        try:
            kickoff = (
                datetime.datetime.fromtimestamp(
                    int(ts), datetime.timezone.utc
                ).isoformat()
                if ts
                else None
            )
        except (TypeError, ValueError):
            kickoff = None
        eid = cur.get("AA")
        out.append(
            {
                "fixture_id": f"FS_{eid}",
                "match": f"{cur['AE']} vs {cur['AF']}",
                "league": cur.get("_league", "Live"),
                "kickoff": kickoff
                or datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "status_code": "LIVE",
                "has_lineup": False,
                "prediction": None,
                "prematch_markets": None,
                "live_only": True,  # marks a display-only card (no odds, no betting)
                "fixture": {
                    "id": f"FS_{eid}",
                    "home_score": hs,
                    "away_score": as_,
                    "status": {"short": "LIVE"},
                    "date": kickoff,
                },
            }
        )

    for blk in txt.split("~"):
        f = {}
        for part in blk.split(_REC):
            if _KV in part:
                k, v = part.split(_KV, 1)
                f[k] = v
        if "ZA" in f:
            league = f["ZA"]
        if "AA" in f:
            flush()
            cur = dict(f)
            cur["_league"] = league
        elif cur:
            cur.update(f)
    flush()
    return out


def get_live_matches(limit=80):
    """Return display-only dashboard cards for matches currently in play. Cached (45s)."""
    if (time.time() - _cache["ts"]) < _TTL and _cache["data"]:
        return _cache["data"][:limit]
    data = []
    try:
        r = requests.get(_DAY, headers=_H, timeout=12)
        if r.status_code == 200 and len(r.text) > 5:
            data = _parse(r.text)
    except Exception as e:
        print(f"[LIVE] feed error: {e}")
    _cache["ts"] = time.time()
    _cache["data"] = data
    return data[:limit]


if __name__ == "__main__":
    m = get_live_matches()
    print(f"live now: {len(m)}")
    for x in m[:25]:
        fx = x["fixture"]
        print(f"  {x['match']}  {fx['home_score']}-{fx['away_score']}  | {x['league']}")
