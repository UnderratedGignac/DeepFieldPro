"""
Nightly evidence collection — runs all analytics tools in sequence and writes
a summary cache used by the CLV dashboard.

Schedule via Windows Task Scheduler or run manually:
    .venv\Scripts\python.exe tools\nightly_jobs.py

Jobs (in order):
  1. signal_discovery  — re-rank signals by CLV; writes data/signal_discovery_results.json
                         and appends a row to signal_performance table
  2. steam_monitor     — print STEAM P&L report to logs/nightly_steam.txt
  3. clv_summary       — build data/nightly_cache.json (overall CLV + last-24h status)
  4. signal_validate   — walk-forward hold-out evaluation; writes signal_validation table

Output: logs/nightly_jobs.log  (appended each run)
"""
import os
import sys
import json
import sqlite3
import datetime
import subprocess

ROOT    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA    = os.path.join(ROOT, "data")
LOGS    = os.path.join(ROOT, "logs")
PYTHON  = os.path.join(ROOT, ".venv", "Scripts", "python.exe")

os.makedirs(LOGS, exist_ok=True)

LOG_FILE   = os.path.join(LOGS, "nightly_jobs.log")
CACHE_FILE = os.path.join(DATA, "nightly_cache.json")


def _log(msg):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def _run_script(script_path, *args, log_file=None):
    """Run a Python script via the project venv and return (returncode, stdout)."""
    cmd = [PYTHON, script_path] + list(args)
    _log(f"  Running: {' '.join(os.path.basename(c) for c in cmd)}")
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=ROOT,
            timeout=300,
        )
        if log_file:
            with open(log_file, "w", encoding="utf-8") as f:
                f.write(result.stdout)
                if result.stderr:
                    f.write("\n--- STDERR ---\n" + result.stderr)
        if result.returncode != 0:
            _log(f"  [WARN] exit {result.returncode} — check {log_file or 'stderr'}")
        return result.returncode, result.stdout
    except subprocess.TimeoutExpired:
        _log("  [ERROR] Script timed out after 300s")
        return 1, ""
    except Exception as e:
        _log(f"  [ERROR] {e}")
        return 1, ""


def job_signal_discovery():
    _log("=== JOB 1: Signal Discovery ===")
    rc, out = _run_script(
        os.path.join(ROOT, "tools", "signal_discovery.py"),
        "--min-bets", "20",
        log_file=os.path.join(LOGS, "nightly_signal_discovery.txt"),
    )
    sig_path = os.path.join(DATA, "signal_discovery_results.json")
    if os.path.exists(sig_path):
        try:
            disc = json.load(open(sig_path))
            sigs = disc.get("signals", {})
            top = sorted(sigs.items(), key=lambda x: x[1].get("avg_clv") or -999, reverse=True)
            _log(f"  Signals ranked: {len(sigs)}.  Top: " + ", ".join(
                f"{k} CLV={v.get('avg_clv', 0):.1f}%" for k, v in top[:3]
            ) if top else "  No signals.")
        except Exception as e:
            _log(f"  Could not parse results: {e}")
    else:
        _log("  [WARN] signal_discovery_results.json not written.")
    return rc == 0


def job_steam_monitor():
    _log("=== JOB 2: STEAM Monitor ===")
    rc, _ = _run_script(
        os.path.join(ROOT, "tools", "steam_monitor.py"),
        log_file=os.path.join(LOGS, "nightly_steam.txt"),
    )
    _log(f"  STEAM monitor {'OK' if rc == 0 else 'FAILED'}. Report at logs/nightly_steam.txt")
    return rc == 0


def job_signal_validate():
    _log("=== JOB 4: Walk-Forward Signal Validation ===")
    rc, _ = _run_script(
        os.path.join(ROOT, "tools", "signal_validate.py"),
        "--min-bets", "10",
        log_file=os.path.join(LOGS, "nightly_signal_validate.txt"),
    )
    val_path = os.path.join(DATA, "signal_validation_results.json")
    if os.path.exists(val_path):
        try:
            val = json.load(open(val_path))
            sigs = val.get("signals", {})
            top = sorted(sigs.items(), key=lambda x: x[1].get("avg_clv") or -999, reverse=True)
            _log(f"  Validation signals: {len(sigs)}.  Top: " + ", ".join(
                f"{k} CLV={v.get('avg_clv', 0):.1f}%" for k, v in top[:3]
            ) if top else "  No signals.")
        except Exception as e:
            _log(f"  Could not parse validation results: {e}")
    else:
        _log("  [WARN] signal_validation_results.json not written.")
    return rc == 0


def job_clv_summary():
    """Write a quick CLV summary cache so the dashboard can show stale-data warnings."""
    _log("=== JOB 3: CLV Summary Cache ===")
    BET_DB = os.path.join(DATA, "bet_log.db")
    if not os.path.exists(BET_DB):
        _log("  [SKIP] bet_log.db not found.")
        return True
    try:
        con = sqlite3.connect(BET_DB)
        # Overall STEAM CLV
        rows = con.execute(
            """SELECT clv, result, pnl, stake, placed_at
               FROM bet_log
               WHERE bet_source='STEAM' AND result IN ('W','L','WIN','LOSS')
               ORDER BY placed_at ASC"""
        ).fetchall()
        con.close()

        n = len(rows)
        clv_vals  = [r[0] * 100 for r in rows if r[0] is not None]
        pnl       = sum(r[2] or 0 for r in rows)
        staked    = sum(r[3] or 0 for r in rows)
        wins      = sum(1 for r in rows if r[1] in ("W", "WIN"))
        avg_clv   = round(sum(clv_vals) / len(clv_vals), 2) if clv_vals else None
        roi       = round(pnl / staked * 100, 1) if staked else 0
        last_50   = rows[-50:]
        lc        = [r[0] * 100 for r in last_50 if r[0] is not None]
        last_50_clv = round(sum(lc) / len(lc), 2) if lc else None

        # Auto-promotion status
        sig_path = os.path.join(DATA, "signal_discovery_results.json")
        signals_status = {}
        if os.path.exists(sig_path):
            disc = json.load(open(sig_path))
            for sig, r in disc.get("signals", {}).items():
                sn, sc = r.get("n", 0), r.get("avg_clv")
                if sn >= 100 and sc is not None:
                    signals_status[sig] = "PROMOTE" if sc >= 3.0 else ("DISABLE" if sc < 0.0 else "WATCH")
                else:
                    signals_status[sig] = "WATCH"

        cache = {
            "generated_at": datetime.datetime.now().isoformat(),
            "steam": {
                "n": n, "wins": wins,
                "hit_rate": round(wins / n * 100, 1) if n else 0,
                "roi": roi, "pnl": round(pnl, 2), "staked": round(staked, 2),
                "avg_clv": avg_clv, "clv_n": len(clv_vals),
                "last_50_clv": last_50_clv,
                "decay_status": (
                    "DECAYING" if (avg_clv and last_50_clv and last_50_clv < avg_clv - 3)
                    else "IMPROVING" if (avg_clv and last_50_clv and last_50_clv > avg_clv + 2)
                    else "STABLE"
                ),
            },
            "signals_status": signals_status,
        }
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, indent=2)
        _log(f"  Cache written. STEAM n={n}, avg_clv={avg_clv}, last_50={last_50_clv}")

        # Write daily snapshot to performance_history table
        sig_path2 = os.path.join(DATA, "signal_discovery_results.json")
        if os.path.exists(sig_path2):
            try:
                ph_db = os.path.join(DATA, "deepfield_browser_data", "completed_fixtures.db")
                ph_con = sqlite3.connect(ph_db)
                ph_con.execute("""CREATE TABLE IF NOT EXISTS performance_history (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    date         TEXT,
                    signal_name  TEXT,
                    samples      INTEGER,
                    avg_clv      REAL,
                    roi          REAL,
                    status       TEXT,
                    UNIQUE(date, signal_name)
                )""")
                disc2 = json.load(open(sig_path2))
                today_str = datetime.date.today().isoformat()
                for sig2, r2 in disc2.get("signals", {}).items():
                    sn2, sc2 = r2.get("n", 0), r2.get("avg_clv")
                    if sn2 >= 100 and sc2 is not None:
                        st2 = "PROMOTE" if sc2 >= 3.0 else ("DISABLE" if sc2 < 0.0 else "WATCH")
                    else:
                        st2 = "WATCH"
                    ph_con.execute(
                        "INSERT OR REPLACE INTO performance_history (date, signal_name, samples, avg_clv, roi, status) "
                        "VALUES (?,?,?,?,?,?)",
                        (today_str, sig2, sn2, sc2, None, st2),
                    )
                ph_con.commit()
                ph_con.close()
                _log(f"  Performance history snapshot written ({len(disc2.get('signals', {}))} signals).")
            except Exception as ph_e:
                _log(f"  [warn] performance_history write failed: {ph_e}")

        return True
    except Exception as e:
        _log(f"  [ERROR] {e}")
        return False


def _compute_lifecycle_stage(sig, disc_r, val_r, rolling_clv_7d):
    """Compute current lifecycle stage for a signal from available evidence."""
    from_reg  = disc_r.get("registry_enabled", True)
    promoted  = disc_r.get("registry_promoted", False)
    n         = disc_r.get("n", 0)
    clv       = disc_r.get("avg_clv")
    val_n     = (val_r or {}).get("n", 0)
    val_clv   = (val_r or {}).get("avg_clv")
    val_ci_lo = (val_r or {}).get("ci_lower")

    if not from_reg:
        return "DISABLED"
    if promoted:
        if rolling_clv_7d is not None and clv is not None and rolling_clv_7d < clv - 3.0:
            return "DECAYING"
        return "ACTIVE"
    if val_n >= 20 and val_clv is not None and val_clv >= 2.0 and (val_ci_lo is None or val_ci_lo >= 0):
        return "VALIDATED"
    if n >= 10:
        return "INCUBATING"
    if n >= 1:
        return "DISCOVERED"
    return "UNKNOWN"


def job_write_lifecycle(disc_results, val_results):
    """Write signal_lifecycle transitions: insert a row when a signal's stage changes."""
    _log("=== POST-RUN: Signal Lifecycle ===")
    SIGNALS_DB = os.path.join(DATA, "deepfield_browser_data", "completed_fixtures.db")
    BET_DB     = os.path.join(DATA, "bet_log.db")
    try:
        con = sqlite3.connect(SIGNALS_DB)
        con.execute("""CREATE TABLE IF NOT EXISTS signal_lifecycle (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            signal_name TEXT,
            stage       TEXT,
            entered_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
            n           INTEGER,
            avg_clv     REAL,
            metadata    TEXT
        )""")
        # Load registry flags
        reg = {}
        try:
            for row in con.execute("SELECT signal_name, enabled, promoted FROM signal_registry"):
                reg[row[0]] = {"registry_enabled": bool(row[1]), "registry_promoted": bool(row[2])}
        except Exception:
            pass
        # Load rolling 7d CLV from bet_log
        rolling_7d = {}
        try:
            cutoff = (datetime.datetime.now() - datetime.timedelta(days=7)).isoformat()
            bcon = sqlite3.connect(BET_DB)
            for row in bcon.execute(
                """SELECT signal_name, AVG(clv) FROM bet_log
                   WHERE bet_source='STEAM' AND result IN ('W','L','WIN','LOSS')
                     AND placed_at >= ? AND clv IS NOT NULL
                   GROUP BY signal_name""",
                (cutoff,)
            ):
                rolling_7d[row[0]] = round(row[1] * 100, 2) if row[1] else None
            bcon.close()
        except Exception:
            pass
        # Compute and record stage for each known signal
        all_sigs = set(disc_results) | set(val_results) | set(reg)
        transitions = []
        for sig in all_sigs:
            disc_r = {**(disc_results.get(sig) or {}), **(reg.get(sig) or {})}
            val_r  = val_results.get(sig)
            stage  = _compute_lifecycle_stage(sig, disc_r, val_r, rolling_7d.get(sig))
            n      = disc_r.get("n", 0)
            clv    = disc_r.get("avg_clv")
            # Check last recorded stage to detect transitions
            last = con.execute(
                "SELECT stage FROM signal_lifecycle WHERE signal_name=? ORDER BY id DESC LIMIT 1",
                (sig,)
            ).fetchone()
            if last is None or last[0] != stage:
                meta = json.dumps({"n": n, "clv": clv, "val_clv": (val_r or {}).get("avg_clv")})
                con.execute(
                    "INSERT INTO signal_lifecycle (signal_name, stage, n, avg_clv, metadata) VALUES (?,?,?,?,?)",
                    (sig, stage, n, clv, meta)
                )
                transitions.append(f"{sig}: {(last[0] if last else '?')} → {stage}")
        con.commit()
        con.close()
        if transitions:
            _log(f"  Lifecycle transitions: {'; '.join(transitions)}")
        else:
            _log(f"  No stage changes (all {len(all_sigs)} signals stable).")
        return True
    except Exception as e:
        _log(f"  [ERROR] lifecycle: {e}")
        return False


def job_write_audit_trail(job_results, disc_results, val_results, health_score, avg_clv):
    """Write a versioned audit record for today's nightly run to research_runs table."""
    _log("=== POST-RUN: Research Audit Trail ===")
    SIGNALS_DB = os.path.join(DATA, "deepfield_browser_data", "completed_fixtures.db")
    BET_DB     = os.path.join(DATA, "bet_log.db")
    today_str  = datetime.date.today().isoformat()
    try:
        bets_analyzed = 0
        try:
            bcon = sqlite3.connect(BET_DB)
            row = bcon.execute(
                "SELECT COUNT(*) FROM bet_log WHERE bet_source='STEAM' AND result IN ('W','L','WIN','LOSS')"
            ).fetchone()
            bets_analyzed = row[0] if row else 0
            bcon.close()
        except Exception:
            pass

        promoted = [s for s, r in disc_results.items()
                    if (r.get("n", 0) >= 100 and (r.get("avg_clv") or 0) >= 3.0)]
        disabled = [s for s, r in disc_results.items()
                    if (r.get("n", 0) >= 100 and (r.get("avg_clv") or 0) < 0.0)]

        con = sqlite3.connect(SIGNALS_DB)
        con.execute("""CREATE TABLE IF NOT EXISTS research_runs (
            id                 INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id             TEXT UNIQUE,
            run_at             DATETIME DEFAULT CURRENT_TIMESTAMP,
            signals_evaluated  INTEGER,
            bets_analyzed      INTEGER,
            promoted           TEXT,
            disabled           TEXT,
            health_score       INTEGER,
            avg_clv            REAL,
            jobs_ok            TEXT
        )""")
        con.execute(
            """INSERT OR REPLACE INTO research_runs
               (run_id, signals_evaluated, bets_analyzed, promoted, disabled,
                health_score, avg_clv, jobs_ok)
               VALUES (?,?,?,?,?,?,?,?)""",
            (today_str, len(disc_results), bets_analyzed,
             json.dumps(promoted), json.dumps(disabled),
             health_score, round(avg_clv, 2) if avg_clv is not None else None,
             json.dumps({k: bool(v) for k, v in job_results.items()}))
        )
        con.commit()
        con.close()
        _log(f"  Audit record written: run_id={today_str}, bets={bets_analyzed}, "
             f"promoted={promoted}, disabled={disabled}, health={health_score}")
        return True
    except Exception as e:
        _log(f"  [ERROR] audit trail: {e}")
        return False


def job_write_snapshot(disc_results, val_results, health_score, avg_clv):
    """Write a deterministic dated snapshot to data/research_snapshots/ (config versioning)."""
    _log("=== POST-RUN: Research Snapshot (Config Versioning) ===")
    snap_dir = os.path.join(DATA, "research_snapshots")
    os.makedirs(snap_dir, exist_ok=True)
    today_str = datetime.date.today().isoformat()
    try:
        SIGNALS_DB = os.path.join(DATA, "deepfield_browser_data", "completed_fixtures.db")
        # Signal registry
        reg = {}
        try:
            con = sqlite3.connect(SIGNALS_DB)
            for row in con.execute("SELECT signal_name, enabled, promoted, updated_at FROM signal_registry"):
                reg[row[0]] = {"enabled": bool(row[1]), "promoted": bool(row[2]), "updated_at": row[3]}
            con.close()
        except Exception:
            pass
        # settings.json — runtime config snapshot
        settings_snap = {}
        try:
            settings_path = os.path.join(DATA, "settings.json")
            if os.path.exists(settings_path):
                settings_snap = json.load(open(settings_path))
        except Exception:
            pass
        # Active experiment (if any)
        active_exp = None
        try:
            con = sqlite3.connect(SIGNALS_DB)
            row = con.execute(
                "SELECT id, hypothesis, config_snapshot FROM experiments "
                "WHERE status='ACTIVE' ORDER BY start_date DESC LIMIT 1"
            ).fetchone()
            con.close()
            if row:
                active_exp = {"id": row[0], "hypothesis": row[1],
                              "config": json.loads(row[2] or "{}")}
        except Exception:
            pass

        snapshot = {
            "date": today_str,
            "health_score": health_score,
            "avg_clv": round(avg_clv, 2) if avg_clv is not None else None,
            "signal_registry": reg,
            "discovery_results": disc_results,
            "validation_results": val_results,
            "settings_snapshot": settings_snap,
            "active_experiment": active_exp,
        }
        out_path = os.path.join(snap_dir, f"{today_str}.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(snapshot, f, indent=2)
        _log(f"  Snapshot written to {out_path} (includes settings.json + experiment ref)")
        return True
    except Exception as e:
        _log(f"  [ERROR] snapshot: {e}")
        return False


def job_write_report(disc_results, val_results, health_score, avg_clv, cache):
    """Generate a nightly markdown research report in reports/YYYY-MM-DD.md."""
    _log("=== POST-RUN: Research Report ===")
    reports_dir = os.path.join(ROOT, "reports")
    os.makedirs(reports_dir, exist_ok=True)
    today_str = datetime.date.today().isoformat()
    try:
        SIGNALS_DB = os.path.join(DATA, "deepfield_browser_data", "completed_fixtures.db")
        # Load lifecycle
        lifecycle = {}
        try:
            con = sqlite3.connect(SIGNALS_DB)
            for row in con.execute(
                "SELECT signal_name, stage, n, avg_clv FROM signal_lifecycle "
                "WHERE id IN (SELECT MAX(id) FROM signal_lifecycle GROUP BY signal_name)"
            ):
                lifecycle[row[0]] = {"stage": row[1], "n": row[2], "avg_clv": row[3]}
            con.close()
        except Exception:
            pass
        # Load active experiment
        active_exp = None
        try:
            con = sqlite3.connect(SIGNALS_DB)
            row = con.execute(
                "SELECT id, hypothesis, start_date FROM experiments WHERE status='ACTIVE' "
                "ORDER BY start_date DESC LIMIT 1"
            ).fetchone()
            con.close()
            if row:
                active_exp = {"id": row[0], "hypothesis": row[1], "start_date": row[2]}
        except Exception:
            pass
        # Rolling CLV from cache
        steam = cache.get("steam", {})
        last50_clv = steam.get("last_50_clv")
        decay_status = steam.get("decay_status", "UNKNOWN")
        n_total = steam.get("n", 0)
        # STEAM_FWD validation
        steam_fwd_val = val_results.get("STEAM_FWD") or disc_results.get("STEAM_FWD") or {}
        val_n  = steam_fwd_val.get("n", 0)
        val_clv = steam_fwd_val.get("avg_clv")
        val_ci_lo = steam_fwd_val.get("ci_lower")
        val_ci_hi = steam_fwd_val.get("ci_upper")

        # Build the report
        lines = [
            f"# DeepFieldPro Research Summary — {today_str}",
            f"",
            f"## Platform Health",
            f"",
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| Health Score | {health_score}/100 |",
            f"| Overall Avg CLV | {f'+{avg_clv:.1f}%' if avg_clv and avg_clv >= 0 else f'{avg_clv:.1f}%' if avg_clv else '—'} |",
            f"| Total Settled Bets | {n_total} |",
            f"| Last 50 Bets CLV | {f'+{last50_clv:.1f}%' if last50_clv and last50_clv >= 0 else f'{last50_clv:.1f}%' if last50_clv else '—'} |",
            f"| Regime | {decay_status} |",
            f"",
            f"## Signals",
            f"",
            f"| Signal | Stage | n | CLV | Status |",
            f"|--------|-------|---|-----|--------|",
        ]
        all_sigs = set(lifecycle) | set(disc_results)
        stage_order = ["ACTIVE","VALIDATED","PROMOTED","INCUBATING","DISCOVERED","DECAYING","DISABLED","UNKNOWN"]
        sorted_sigs = sorted(all_sigs, key=lambda s: stage_order.index(lifecycle.get(s, {}).get("stage", "UNKNOWN")) if lifecycle.get(s, {}).get("stage","UNKNOWN") in stage_order else 99)
        for sig in sorted_sigs:
            lc = lifecycle.get(sig, {})
            dr = disc_results.get(sig, {})
            stage = lc.get("stage", "?")
            n     = lc.get("n") or dr.get("n", 0)
            clv   = lc.get("avg_clv") if lc.get("avg_clv") is not None else dr.get("avg_clv")
            clv_str = f"+{clv:.1f}%" if clv and clv >= 0 else f"{clv:.1f}%" if clv else "—"
            status = "✅" if clv and clv >= 3 else "⚠️" if clv and clv >= 0 else "❌" if clv else "—"
            lines.append(f"| {sig} | {stage} | {n} | {clv_str} | {status} |")

        lines += [
            f"",
            f"## STEAM_FWD Walk-Forward Validation",
            f"",
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| Validation Samples | {val_n} / 100 |",
            f"| Validation CLV | {f'+{val_clv:.1f}%' if val_clv and val_clv >= 0 else f'{val_clv:.1f}%' if val_clv else '—'} |",
            f"| 95% CI Lower | {f'+{val_ci_lo:.1f}%' if val_ci_lo and val_ci_lo >= 0 else f'{val_ci_lo:.1f}%' if val_ci_lo is not None else '—'} |",
            f"| 95% CI Upper | {f'+{val_ci_hi:.1f}%' if val_ci_hi and val_ci_hi >= 0 else f'{val_ci_hi:.1f}%' if val_ci_hi is not None else '—'} |",
            f"",
        ]

        # Active experiment section
        if active_exp:
            lines += [
                f"## Active Experiment",
                f"",
                f"**{active_exp['id']}** (started {active_exp['start_date']})",
                f"> {active_exp['hypothesis']}",
                f"",
            ]

        # Alerts
        lines += ["## Alerts", ""]
        if val_n < 100:
            lines.append(f"- 🎯 Need **{100 - val_n} more** walk-forward samples to reach statistical significance.")
        if decay_status == "DECAYING":
            lines.append("- ⚠️  **Regime alert**: Last 50 CLV trailing lifetime CLV by >3pp — possible decay.")
        if val_n >= 100 and val_clv and val_clv > 0 and (val_ci_lo is None or val_ci_lo >= 0):
            lines.append("- ✅ **MILESTONE REACHED**: STEAM_FWD has 100+ validated samples with positive CLV and CI above zero.")
        if not any(l.startswith("- ") for l in lines[-5:]):
            lines.append("- ✅ No alerts.")

        lines += ["", "---", f"*Generated by DeepFieldPro nightly_jobs.py on {today_str}*"]

        report_path = os.path.join(reports_dir, f"{today_str}.md")
        with open(report_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        _log(f"  Report written to {report_path}")
        return True
    except Exception as e:
        _log(f"  [ERROR] report: {e}")
        return False


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    _log("=" * 60)
    _log(f"NIGHTLY JOBS START — {datetime.date.today()}")
    _log("=" * 60)

    results = {
        "signal_discovery": job_signal_discovery(),
        "steam_monitor":    job_steam_monitor(),
        "clv_summary":      job_clv_summary(),
        "signal_validate":  job_signal_validate(),
    }

    # ── Post-run: load outputs for audit/lifecycle/snapshot
    _disc, _val = {}, {}
    try:
        sig_path = os.path.join(DATA, "signal_discovery_results.json")
        if os.path.exists(sig_path):
            _disc = json.load(open(sig_path)).get("signals", {})
    except Exception:
        pass
    try:
        val_path = os.path.join(DATA, "signal_validation_results.json")
        if os.path.exists(val_path):
            _val = json.load(open(val_path)).get("signals", {})
    except Exception:
        pass
    try:
        cache_path = os.path.join(DATA, "nightly_cache.json")
        _cache = json.load(open(cache_path)) if os.path.exists(cache_path) else {}
    except Exception:
        _cache = {}
    _health = _cache.get("steam", {}).get("decay_status") and 50 or 0  # rough placeholder
    _avg_clv = _cache.get("steam", {}).get("avg_clv")

    # ── Compute health score: n/300*30 + clv/10*25 (mirrors dashboard logic)
    _n = _cache.get("steam", {}).get("n", 0)
    _health = min(30, _n / 300 * 30) + min(25, max(0, (_avg_clv or 0) / 10 * 25))
    _health = round(_health)

    results["signal_lifecycle"] = job_write_lifecycle(_disc, _val)
    results["audit_trail"]      = job_write_audit_trail(results, _disc, _val, _health, _avg_clv)
    results["snapshot"]         = job_write_snapshot(_disc, _val, _health, _avg_clv)
    results["report"]           = job_write_report(_disc, _val, _health, _avg_clv, _cache)

    _log("=" * 60)
    passed = sum(1 for v in results.values() if v)
    _log(f"NIGHTLY JOBS DONE — {passed}/{len(results)} OK")
    for job, ok in results.items():
        _log(f"  {'[OK]' if ok else '[FAIL]'}  {job}")
    _log("=" * 60)
    sys.exit(0 if all(results.values()) else 1)
