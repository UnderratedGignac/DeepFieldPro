"""
flashscore_stats.py — REAL match statistics (corners, cards, shots) for settlement.
==================================================================================
Settling prop markets (corners, cards) requires actual match stats, not just the score.
The old code fabricated these with hash(bet_id) (the mirage). This pulls REAL stats from
Flashscore's match-detail feed — keyless (static x-fsign header), plain requests, no browser:

  df_st_1_<eventId>  -> the Statistics tab: "Corner kicks", "Yellow cards", "Red cards",
                        "Total shots", etc. as home/away values.

Discovery: the daily feed (f_1_<offset>_3_en_1) maps "Home vs Away" -> eventId (the AA field).

We ONLY fetch stats for the specific matches that have an open prop bet (settlement passes
the list), so this stays cheap — not a fetch-everything sweep.

Public API:
    stats_for_matches(match_names, offsets=(0,-1,-2))
        -> { "<your match name>": {"corners_total": int|None,
                                    "cards_total": int|None,
                                    "shots_home": int|None, "shots_away": int|None} }
    Only matches we could confidently map AND that had real stats are included.

What this does NOT do: individual goalscorers or per-player shots — Flashscore's free feed
doesn't expose reliable per-player data, so those markets are intentionally not settleable
here (better an honest gap than a fabricated/wrong settlement).
"""

import re
import requests

_H = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/125.0 Safari/537.36",
    "x-fsign": "SW9D1eZo",
    "Referer": "https://www.flashscore.com/",
}
_DAY = "https://local-global.flashscore.ninja/2/x/feed/f_1_{off}_3_en_1"
_STAT = "https://local-global.flashscore.ninja/2/x/feed/df_st_1_{mid}"
_REC = chr(0x00AC)
_KV = chr(0x00F7)

# Same native<->English aliases used elsewhere so e.g. "Cabo Verde" maps to "Cape Verde".
_ALIASES = {
    "cabo verde": "cape verde",
    "cote d ivoire": "ivory coast",
    "korea republic": "south korea",
    "ir iran": "iran",
    "china pr": "china",
}


def _norm(s):
    n = "".join(c for c in (s or "").lower() if c.isalnum() or c == " ")
    n = re.sub(r"\s+", " ", n).strip()
    for a, b in _ALIASES.items():
        n = n.replace(a, b)
    return n


def _parse_blocks(txt):
    for blk in txt.split("~"):
        f = {}
        for part in blk.split(_REC):
            if _KV in part:
                k, v = part.split(_KV, 1)
                f[k] = v
        yield f


def _event_id_map(offsets):
    """{ normalized 'home vs away' : eventId } for finished matches across the offsets."""
    out = {}
    for off in offsets:
        try:
            txt = requests.get(_DAY.format(off=off), headers=_H, timeout=15).text
        except Exception:
            continue
        cur = {}

        def stash(c):
            if c.get("AE") and c.get("AF") and c.get("AA"):
                out[_norm(f"{c['AE']} vs {c['AF']}")] = c["AA"]

        for f in _parse_blocks(txt):
            if "AA" in f:
                stash(cur)
                cur = dict(f)
            elif cur:
                cur.update(f)
        stash(cur)
    return out


def _to_int(s):
    m = re.match(r"\s*(\d+)", s or "")
    return int(m.group(1)) if m else None


def _to_float(s):
    m = re.match(r"\s*([\d.]+)", s or "")
    try:
        return float(m.group(1)) if m else None
    except ValueError:
        return None


def _match_stats(event_id):
    """Parse the Statistics feed -> {corners_total, cards_total, shots_home, shots_away}."""
    try:
        txt = requests.get(_STAT.format(mid=event_id), headers=_H, timeout=12).text
    except Exception:
        return None
    if not txt or len(txt) < 5:
        return None
    vals = {}
    for f in _parse_blocks(txt):
        name = f.get("SG")
        if name and name not in vals:
            vals[name] = (f.get("SH"), f.get("SI"))
    res = {
        "corners_total": None,
        "cards_total": None,
        "shots_home": None,
        "shots_away": None,
        "xg_home": None,
        "xg_away": None,
    }
    if "Expected goals (xG)" in vals:
        res["xg_home"] = _to_float(vals["Expected goals (xG)"][0])
        res["xg_away"] = _to_float(vals["Expected goals (xG)"][1])
    if "Corner kicks" in vals:
        h, a = _to_int(vals["Corner kicks"][0]), _to_int(vals["Corner kicks"][1])
        if h is not None and a is not None:
            res["corners_total"] = h + a
    yc = vals.get("Yellow cards", (None, None))
    rc = vals.get("Red cards", (None, None))
    cards = [
        x
        for x in (_to_int(yc[0]), _to_int(yc[1]), _to_int(rc[0]), _to_int(rc[1]))
        if x is not None
    ]
    if "Yellow cards" in vals:  # at least yellow data present
        res["cards_total"] = sum(cards)
    if "Total shots" in vals:
        res["shots_home"], res["shots_away"] = (
            _to_int(vals["Total shots"][0]),
            _to_int(vals["Total shots"][1]),
        )
    has_any = any(v is not None for v in res.values())
    return res if has_any else None


def _best_event(name, idmap):
    """Fuzzy-map a 'Home vs Away' bet name to a Flashscore eventId."""
    target = _norm(name)
    if target in idmap:
        return idmap[target]
    t = set(target.split())
    best, best_ov = None, 0.0
    for k, eid in idmap.items():
        ks = set(k.split())
        if not ks:
            continue
        ov = len(t & ks) / len(t | ks)
        if ov > best_ov:
            best, best_ov = eid, ov
    return best if best_ov >= 0.5 else None


def stats_for_matches(match_names, offsets=(0, -1, -2)):
    names = {n for n in match_names if n}
    if not names:
        return {}
    idmap = _event_id_map(offsets)
    if not idmap:
        return {}
    out = {}
    seen = {}  # event_id -> stats (cache so two bets on the same match fetch once)
    for name in names:
        eid = _best_event(name, idmap)
        if not eid:
            continue
        if eid not in seen:
            seen[eid] = _match_stats(eid)
        if seen[eid]:
            out[name] = seen[eid]
    return out


if __name__ == "__main__":
    import sys

    print(stats_for_matches(sys.argv[1:] or ["Spain vs Cape Verde"]))
