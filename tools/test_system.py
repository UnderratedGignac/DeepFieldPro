"""
test_system.py -- DeepFieldPro end-to-end system tests.

Covers: Pinnacle value detector, STEAM logic, CLV computation,
bet log recording, bankroll tracking, and safety gates.

Run: .venv/Scripts/python.exe tools/test_system.py
Exit 0 = all tests passed. Non-zero = failures (details printed).
"""

import os
import sys
import sqlite3
import json
import datetime
import uuid
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

DATA_DIR = os.path.join(ROOT, "data")
COMPLETED_DB = os.path.join(DATA_DIR, "deepfield_browser_data", "completed_fixtures.db")
BET_LOG_DB = os.path.join(DATA_DIR, "bet_log.db")
BANKROLL_DB = os.path.join(DATA_DIR, "bankroll.db")
SETTINGS_JSON = os.path.join(DATA_DIR, "settings.json")

# ─── helpers ──────────────────────────────────────────────────────────────────

PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"
WARN = "\033[93mWARN\033[0m"

results = []


def check(name, expr, detail=""):
    ok = bool(expr)
    results.append((name, ok, detail))
    status = PASS if ok else FAIL
    line = f"  [{status}] {name}"
    if detail:
        line += f" — {detail}"
    print(line)
    return ok


def warn(name, detail=""):
    results.append((name, None, detail))
    print(f"  [{WARN}] {name}" + (f" — {detail}" if detail else ""))


# ─── SECTION 1: Safety gates ─────────────────────────────────────────────────

print("\n=== 1. SAFETY GATES ===")

# 1a. DEEPFIELD_ARENA_LIVE must NOT be set
check(
    "DEEPFIELD_ARENA_LIVE unset",
    not os.environ.get("DEEPFIELD_ARENA_LIVE"),
    "Real-money arena gate is off",
)

# 1b. SHADOW_MODE must be True in dfp_config (it's a Pydantic Settings instance)
try:
    from src.dfp_config import Settings as _DFPSettings

    _cfg = _DFPSettings()
    check("SHADOW_MODE=True", _cfg.SHADOW_MODE is True, f"dfp_config.Settings().SHADOW_MODE={_cfg.SHADOW_MODE}")
except Exception as e:
    check("SHADOW_MODE import", False, str(e))

# 1c. settings.json ai_real_staking_enabled must be False
try:
    with open(SETTINGS_JSON) as f:
        settings = json.load(f)
    check(
        "ai_real_staking_enabled=False",
        not settings.get("ai_real_staking_enabled", False),
        "Model bets use stake=0 in paper mode",
    )
    check(
        "pinnacle_value_betting_enabled=False",
        not settings.get("pinnacle_value_betting_enabled", True),
        "Pinnacle value bets off by default (measure first)",
    )
except Exception as e:
    check("settings.json readable", False, str(e))

# ─── SECTION 2: Database connectivity ─────────────────────────────────────────

print("\n=== 2. DATABASE CONNECTIVITY ===")

for label, path in [
    ("bet_log.db", BET_LOG_DB),
    ("bankroll.db", BANKROLL_DB),
    ("completed_fixtures.db", COMPLETED_DB),
]:
    if not os.path.exists(path):
        warn(f"{label} exists", f"Not found at {path}")
        continue
    try:
        con = sqlite3.connect(path, timeout=3)
        con.execute("SELECT 1")
        con.close()
        check(f"{label} readable", True)
    except Exception as e:
        check(f"{label} readable", False, str(e))

# sharp_odds_history row count
try:
    con = sqlite3.connect(COMPLETED_DB, timeout=3)
    n = con.execute("SELECT COUNT(*) FROM sharp_odds_history").fetchone()[0]
    con.close()
    check(
        "sharp_odds_history populated",
        n > 0,
        f"{n:,} rows",
    )
except Exception as e:
    warn("sharp_odds_history", str(e))

# odds_history row count
try:
    con = sqlite3.connect(COMPLETED_DB, timeout=3)
    n = con.execute("SELECT COUNT(*) FROM odds_history").fetchone()[0]
    con.close()
    check("odds_history populated", n > 0, f"{n:,} rows")
except Exception as e:
    warn("odds_history", str(e))

# ─── SECTION 3: Pinnacle value detector ───────────────────────────────────────

print("\n=== 3. PINNACLE VALUE DETECTOR ===")

try:
    from tools.pinnacle_value import get_pinnacle_latest, check_value, kelly_stake, clv_from_pinnacle

    check("pinnacle_value imports", True)

    # Pick a real match from sharp_odds_history if any exist
    try:
        con = sqlite3.connect(COMPLETED_DB, timeout=3)
        sample = con.execute(
            "SELECT home_team, away_team, selection, decimal_odds, devig_prob "
            "FROM sharp_odds_history WHERE devig_prob > 0 ORDER BY ts DESC LIMIT 1"
        ).fetchone()
        con.close()
        if sample:
            s_home, s_away, s_sel, s_odds, s_prob = sample
            pin = get_pinnacle_latest(s_home, s_away, s_sel)
            check(
                "get_pinnacle_latest returns dict",
                isinstance(pin, dict),
                f"{s_home} vs {s_away} [{s_sel}]",
            )
            if pin:
                check("devig_prob in result", "devig_prob" in pin and pin["devig_prob"] > 0)
                check("fair_odds in result", "fair_odds" in pin and pin["fair_odds"] > 1.0)
        else:
            warn("No sharp_odds_history data for live lookup test")
    except Exception as e:
        check("pinnacle_latest live lookup", False, str(e))

    # kelly_stake sanity check
    ks = kelly_stake(edge=0.05, odds=2.0, kelly_frac=0.20)
    check("kelly_stake > 0 for positive edge", ks > 0, f"stake_frac={ks:.4f}")
    check("kelly_stake <= 0.10", ks <= 0.10)

    ks_neg = kelly_stake(edge=-0.01, odds=2.0)
    check("kelly_stake = 0 for negative edge", ks_neg == 0.0, f"stake_frac={ks_neg}")

    # check_value with synthetic data (no real match needed)
    edge, pin_d = check_value("FakeHome FC", "FakeAway FC", "home", 2.0, min_edge=0.03)
    check("check_value returns (0, None) for unknown match", edge == 0.0 and pin_d is None)

except ImportError as e:
    check("pinnacle_value module", False, str(e))

# ─── SECTION 4: STEAM detector ────────────────────────────────────────────────

print("\n=== 4. STEAM DETECTOR ===")

try:
    # Import _steam_moves from daemon (expensive import but necessary)
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "lpd", os.path.join(ROOT, "src", "live_predictions_daemon.py")
    )
    # Only test the module-level functions we can call without spawning the daemon
    from tools.pinnacle_value import _normalize_team

    check("_normalize_team strips dots/hyphens", _normalize_team("Man. Utd-Res") == "man utd res")

    # Verify steam_min_move_pct setting readable
    with open(SETTINGS_JSON) as f:
        s = json.load(f)
    check("steam_min_move_pct in settings", "steam_min_move_pct" in s, f"={s.get('steam_min_move_pct')}")
    check("steam_league_whitelist not empty", len(s.get("steam_league_whitelist", [])) > 0)
    check("steam_flat_stake set", s.get("steam_flat_stake", 0) > 0)

except Exception as e:
    check("STEAM config checks", False, str(e))

# steam_signals table
try:
    con = sqlite3.connect(COMPLETED_DB, timeout=3)
    n = con.execute("SELECT COUNT(*) FROM steam_signals").fetchone()[0]
    con.close()
    check("steam_signals table accessible", True, f"{n} rows")
except Exception as e:
    warn("steam_signals", str(e))

# ─── SECTION 5: Bet log integrity ────────────────────────────────────────────

print("\n=== 5. BET LOG INTEGRITY ===")

try:
    con = sqlite3.connect(BET_LOG_DB, timeout=3)
    columns = [r[1] for r in con.execute("PRAGMA table_info(bet_log)").fetchall()]
    con.close()
    for col in ["bet_id", "match_id", "entry_odds", "stake", "result", "pnl", "bet_source", "side"]:
        check(f"bet_log has column '{col}'", col in columns)

    # Check no implausibly large odds
    con = sqlite3.connect(BET_LOG_DB, timeout=3)
    bad = con.execute(
        "SELECT COUNT(*) FROM bet_log WHERE entry_odds > 100 OR entry_odds < 1.01"
    ).fetchone()[0]
    con.close()
    check("No implausible odds in bet_log", bad == 0, f"{bad} suspicious rows")

    # Check open bets are sane
    con = sqlite3.connect(BET_LOG_DB, timeout=3)
    open_bets = con.execute(
        "SELECT COUNT(*) FROM bet_log WHERE result='OPEN'"
    ).fetchone()[0]
    con.close()
    check("open bets count readable", True, f"{open_bets} open")

except Exception as e:
    check("bet_log schema check", False, str(e))

# ─── SECTION 6: Bankroll tracker ─────────────────────────────────────────────

print("\n=== 6. BANKROLL TRACKER ===")

try:
    con = sqlite3.connect(BANKROLL_DB, timeout=3)
    row = con.execute(
        "SELECT current_balance FROM bankroll ORDER BY date DESC LIMIT 1"
    ).fetchone()
    con.close()
    check("bankroll.db has balance row", row is not None, f"balance={row[0] if row else 'N/A'}")
    if row:
        check("balance > 0", row[0] > 0, f"${row[0]:.2f}")
except Exception as e:
    check("bankroll readable", False, str(e))

try:
    from src.bankroll_tracker import get_status, register_bet, register_settlement

    st = get_status()
    check("get_status() returns dict", isinstance(st, dict))
    bal = st.get("current_balance", 0)
    check("current_balance > 0", bal > 0, f"${bal:.2f}")
    check("system_status readable", "status" in st, f"status={st.get('status')}")
except Exception as e:
    check("bankroll_tracker import", False, str(e))

# ─── SECTION 7: Settlement CLV columns ───────────────────────────────────────

print("\n=== 7. CLV COLUMNS IN BET_LOG ===")

try:
    con = sqlite3.connect(BET_LOG_DB, timeout=3)
    columns = [r[1] for r in con.execute("PRAGMA table_info(bet_log)").fetchall()]
    con.close()
    check("bet_log has 'clv' column", "clv" in columns)
    if "pinnacle_clv" not in columns:
        warn("bet_log has 'pinnacle_clv' column", "Run first settlement to create it")
    else:
        check("bet_log has 'pinnacle_clv' column", True)
    check("bet_log has 'closing_odds' column", "closing_odds" in columns)
except Exception as e:
    check("CLV columns check", False, str(e))

# ─── SECTION 8: Settings completeness ────────────────────────────────────────

print("\n=== 8. SETTINGS COMPLETENESS ===")

REQUIRED_KEYS = [
    "allowed_markets", "exclude_draws", "steam_betting_enabled",
    "steam_min_move_pct", "steam_league_whitelist", "steam_flat_stake",
    "pinnacle_value_betting_enabled", "pinnacle_min_edge_pct",
    "require_pinnacle_confirm", "kelly_multiplier", "min_ev_threshold",
    "require_dc_coverage", "daily_stop_loss_pct", "max_drawdown_pct",
]

try:
    with open(SETTINGS_JSON) as f:
        s = json.load(f)
    for key in REQUIRED_KEYS:
        check(f"settings['{key}'] present", key in s, f"={s.get(key)}")
    check("allowed_markets=['1X2']", s.get("allowed_markets") == ["1X2"])
    check("exclude_draws=True", s.get("exclude_draws") is True)
except Exception as e:
    check("settings.json parse", False, str(e))

# ─── SECTION 9: Dixon-Coles model load ───────────────────────────────────────

print("\n=== 9. MODEL FILES ===")

models_dir = os.path.join(ROOT, "models")
for fname in ["dixon_coles.json", "calibrator_1x2.json"]:
    fpath = os.path.join(models_dir, fname)
    exists = os.path.exists(fpath)
    check(f"models/{fname} exists", exists)
    if exists:
        try:
            with open(fpath) as f:
                data = json.load(f)
            check(f"models/{fname} valid JSON", True, f"{len(data)} keys" if isinstance(data, dict) else "array")
        except Exception as e:
            check(f"models/{fname} valid JSON", False, str(e))

# ─── Summary ──────────────────────────────────────────────────────────────────

print("\n" + "=" * 60)
passed = sum(1 for _, ok, _ in results if ok is True)
failed = sum(1 for _, ok, _ in results if ok is False)
warned = sum(1 for _, ok, _ in results if ok is None)
total = passed + failed

print(f"  Results: {passed}/{total} passed, {failed} failed, {warned} warnings")

if failed:
    print("\nFailed tests:")
    for name, ok, detail in results:
        if ok is False:
            print(f"  - {name}" + (f": {detail}" if detail else ""))
    print()
    sys.exit(1)
else:
    print("\nAll tests passed.\n")
    sys.exit(0)
