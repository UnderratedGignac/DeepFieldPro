"""Quick pre-flight check run by START_ALL.bat."""
import os, sys
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

ok = True
if os.getenv("STAIR_AI_API_KEY"):
    print("  [ok] STAIR_AI_API_KEY present")
else:
    print("  [warn] STAIR_AI_API_KEY missing in .env")
    ok = False

if all(os.getenv(k) for k in ["BETFAIR_USERNAME", "BETFAIR_PASSWORD", "BETFAIR_APP_KEY"]):
    print("  [ok] Betfair credentials present (activate at betfair.com)")
else:
    print("  [info] Betfair not configured -- line-shopping limited to Pinnacle only")

if os.path.exists("data/history.db"):
    import sqlite3
    cols = [r[1] for r in sqlite3.connect("data/history.db").execute("PRAGMA table_info(matches)")]
    if "referee" in cols:
        print("  [ok] history.db has referee data")
    else:
        print("  [warn] history.db missing referee column -- run ingest_history.py")
else:
    print("  [warn] history.db not found -- run ingest_history.py")

print("  [ok] Pre-flight done" if ok else "  [warn] Pre-flight done with warnings")
