"""Debug why open bets can't settle — run from project root."""
import sys, os, io, sqlite3, datetime, re, unicodedata
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.flashscore_scraper import get_finished_results as flashscore_results
from src.free_results_scraper import get_finished_results as espn_results

# Fetch results for last 3 days
now_utc = datetime.datetime.now(datetime.timezone.utc)
dates = [(now_utc - datetime.timedelta(days=d)).strftime("%Y-%m-%d") for d in range(3)]
print(f"Fetching results for dates: {dates}")

flash = flashscore_results(dates=dates)
espn = espn_results(dates=dates)
print(f"Flashscore: {len(flash)} matches")
print(f"ESPN: {len(espn)} matches")
all_results = {**flash, **espn}
print(f"Combined: {len(all_results)} matches")

# Name matching
_TEAM_ALIASES = {
    "st patricks": "st patricks", "st pat": "st patricks",
    "utsiktens bk": "utsiktens", "atvidabergs ff": "atvidabergs",
}
def get_tokens(name):
    n = name.lower()
    n = "".join(c for c in unicodedata.normalize("NFD", n) if unicodedata.category(c) != "Mn")
    n = re.sub(r"[^a-z0-9\s]", " ", n)
    n = re.sub(r"\s+", " ", n).strip()
    noise = {"fc", "cf", "sc", "u23", "pr", "ii", "u20", "united", "city", "town",
             "athletic", "club", "de", "fk", "afc", "sv", "sp",
             "bk", "ik", "if", "sk", "aik", "bois", "if", "ff"}
    return [w for w in n.split() if w and w not in noise]

def match_score(n1, n2):
    if not n1 or not n2: return 0.0
    t1, t2 = get_tokens(n1), get_tokens(n2)
    if not t1 or not t2: return 0.0
    if t1 == t2: return 1.0
    s1, s2 = set(t1), set(t2)
    if s1 == s2: return 0.95
    if s1.issubset(s2) or s2.issubset(s1):
        return 0.8 + 0.1 * (min(len(s1), len(s2)) / max(len(s1), len(s2)))
    inter = s1 & s2
    if inter:
        return 0.5 + 0.3 * (len(inter) / len(s1 | s2))
    return 0.0

# Load open bets
conn = sqlite3.connect(os.path.join(os.path.dirname(__file__), "..", "data", "bet_log.db"))
conn.row_factory = sqlite3.Row
cur = conn.cursor()
cur.execute("SELECT match_id, market_type, side, placed_at FROM bet_log WHERE result='OPEN' ORDER BY placed_at")
open_bets = cur.fetchall()
conn.close()

print(f"\n=== Checking {len(open_bets)} OPEN bets ===\n")

for bet in open_bets:
    mid = (bet["match_id"] or "").encode("ascii","replace").decode()
    try:
        parts = mid.split(" vs ", 1)
        bh, ba = parts[0].strip(), parts[1].strip()
    except Exception:
        print(f"  SKIP (can't parse): {mid}")
        continue

    # Find best match
    best_score = 0.0
    best_match = None
    best_result = None
    for fname, score in all_results.items():
        try:
            fp = fname.split(" vs ", 1)
            fh, fa = fp[0].strip(), fp[1].strip()
        except Exception:
            continue
        hs = match_score(bh, fh)
        as_ = match_score(ba, fa)
        total = hs + as_
        if total > best_score:
            best_score = total
            best_match = fname.encode("ascii","replace").decode()
            best_result = score

    status = "NOT FOUND" if best_score < 1.0 else f"MATCH ({best_score:.2f})"
    bh_a = bh.encode("ascii","replace").decode()
    ba_a = ba.encode("ascii","replace").decode()
    print(f"{bet['placed_at'][:10]} {bh_a} vs {ba_a}")
    print(f"  -> {status} | best: {best_match} = {best_result} (score={best_score:.2f})")

    # Show closest flashscore matches
    if best_score < 1.0:
        candidates = []
        for fname, score in all_results.items():
            try:
                fp = fname.split(" vs ", 1)
                fh, fa = fp[0].strip(), fp[1].strip()
                hs = match_score(bh, fh)
                as_ = match_score(ba, fa)
                total = hs + as_
                if total > 0.3:
                    candidates.append((total, fname.encode("ascii","replace").decode()))
            except Exception:
                continue
        candidates.sort(reverse=True)
        for s, n in candidates[:3]:
            print(f"    near-miss: {n} ({s:.2f})")
    print()
