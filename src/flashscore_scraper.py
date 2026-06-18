"""
flashscore_scraper.py — free, keyless, DEEP-coverage finished results.
======================================================================
Flashscore (a.k.a. Livescore.in) exposes a hidden data feed that its own frontend uses.
It is NOT a paid API and needs no account — only a static signature header
(`x-fsign: SW9D1eZo`) that the site ships publicly. Plain `requests` works (no browser),
and coverage is enormous: every tier down to Brazilian Serie D, Argentine Torneo Federal,
Australian state NPLs, etc. — exactly the obscure matches ESPN/TheSportsDB miss and that
were leaving bets stuck on OPEN.

Feed URL:  https://local-global.flashscore.ninja/{proj}/x/feed/f_1_{dayOffset}_3_en_1
  - f_1_...   football
  - dayOffset relative to today (0 today, -1 yesterday, ...)
  - data is a `~`-separated list of blocks; each block is `KEY÷VALUE` fields joined by ¬
  - ZA = "COUNTRY: League" header; AE/AF = home/away name; AG/AH = score; AB = status
    (1 scheduled, 2/… live, 3 finished)

Public API (mirrors free_results_scraper for drop-in use):
    get_finished_results(dates=None) -> { "Home vs Away": (home_score, away_score) }
Cached per day-offset (TTL) so the settlement loop can call it every sweep cheaply.
"""

import time
import datetime
import requests

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0 Safari/537.36",
    "x-fsign": "SW9D1eZo",
    "Referer": "https://www.flashscore.com/",
}
_BASE = "https://local-global.flashscore.ninja/2/x/feed/f_1_{off}_3_en_1"
_REC = chr(0x00AC)  # ¬  field separator
_KV = chr(0x00F7)  # ÷  key/value separator
_FINISHED = "3"

# offset -> (epoch_fetched, {match: (hs, as)})
_cache = {}
_CACHE_TTL = 600  # 10 min


def _parse_feed(txt):
    """Parse one feed payload into {'Home vs Away': (hs, as)} for FINISHED matches."""
    out = {}
    cur = {}

    def flush():
        if cur.get("AE") and cur.get("AF") and cur.get("AB") == _FINISHED:
            try:
                hs = int(cur.get("AG"))
                as_ = int(cur.get("AH"))
            except (TypeError, ValueError):
                return
            out[f"{cur['AE']} vs {cur['AF']}"] = (hs, as_)

    for blk in txt.split("~"):
        f = {}
        for part in blk.split(_REC):
            if _KV in part:
                k, v = part.split(_KV, 1)
                f[k] = v
        if "AA" in f:  # a new match block begins
            flush()
            cur = dict(f)
        elif cur:  # continuation fields for the current match
            cur.update(f)
    flush()
    return out


def _results_for_offset(off):
    cached = _cache.get(off)
    if cached and (time.time() - cached[0]) < _CACHE_TTL:
        return cached[1]
    res = {}
    try:
        r = requests.get(_BASE.format(off=off), headers=_HEADERS, timeout=15)
        if r.status_code == 200 and len(r.text) > 5:
            res = _parse_feed(r.text)
    except Exception as e:
        print(f"[FLASHSCORE] feed error for offset {off}: {e}")
    _cache[off] = (time.time(), res)
    return res


def _date_to_offset(date_str):
    try:
        d = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
        return (d - datetime.date.today()).days
    except Exception:
        return None


def get_finished_results(dates=None):
    """Finished results for the given dates (default: today + yesterday). Keyless."""
    if dates is None:
        offsets = [0, -1]
    else:
        offsets = [o for o in (_date_to_offset(d) for d in dates) if o is not None]
    out = {}
    for off in offsets:
        out.update(_results_for_offset(off))
    return out


if __name__ == "__main__":
    res = get_finished_results()
    print(f"flashscore finished results: {len(res)}")
    for k, v in list(res.items())[:20]:
        print("  ", k, v)
