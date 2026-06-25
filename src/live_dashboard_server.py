from flask import Flask, render_template, jsonify, request, Response
import json
import os
import sys
import sqlite3
import datetime
import time

# Ensure src is in path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

app = Flask(__name__)
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Stair AI World-Cup Arena value-betting page (real-money; placement is gated).
try:
    from arena_betting import arena_bp

    app.register_blueprint(arena_bp)
except Exception as _arena_err:  # never let the arena page break the main dashboard
    print(f"[!] Arena betting page not loaded: {_arena_err}")

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")

# Create default settings if not exists
if not os.path.exists(SETTINGS_FILE):
    with open(SETTINGS_FILE, "w") as f:
        json.dump(
            {
                "kelly_multiplier": 0.25,
                "min_ev_threshold": 0.05,
                "max_exposure_pct": 0.05,
                "platt_scaling": True,
                "refresh_interval_sec": 30,
                "data_source": "sofascore_free",
                "api_football_key": "",
                "target_leagues": "All",
                "min_confidence_pct": 55,
                "auto_place_bets": False,
                "home_adv_weight": 1.2,
                "fatigue_penalty": 0.8,
                "max_daily_loss_pct": 10.0,
                "stop_win_pct": 25.0,
                "preferred_bookie": "Pinnacle",
            },
            f,
        )


def query_db(db_name, query, args=(), one=False):
    db_path = os.path.join(DATA_DIR, db_name)
    if not os.path.exists(db_path):
        return None
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(query, args)
        rv = cur.fetchall()
        conn.close()
        return (rv[0] if rv else None) if one else rv
    except Exception as e:
        print("DB Error:", e)
        return None


@app.route("/")
@app.route("/bankroll")
@app.route("/tracker")
@app.route("/settings")
@app.route("/comparison")
@app.route("/ledger")
@app.route("/edge")
def index():
    return render_template("index.html")


@app.route("/api/state")
def get_state():
    state_path = os.path.join(
        os.path.dirname(__file__), "..", "data", "todays_dashboard_state.json"
    )
    try:
        if os.path.exists(state_path):
            with open(state_path, "r", encoding="utf-8") as f:
                state = json.load(f)
        else:
            state = []
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    # Fetch open bets + bankroll status to enrich the state response for the UI
    _open_bets = []
    _bankroll_status = {}
    _bk = 0.0
    try:
        import sqlite3 as _sq2

        _betdb = os.path.join(DATA_DIR, "bet_log.db")
        _bkdb = os.path.join(DATA_DIR, "bankroll.db")

        _bc = _sq2.connect(_betdb)
        _bc.row_factory = _sq2.Row
        _open_rows = _bc.execute(
            "SELECT match_id, market_type, side, entry_odds, stake, bet_source, placed_at "
            "FROM bet_log WHERE result='OPEN' ORDER BY placed_at DESC"
        ).fetchall()
        _open_bets = [dict(r) for r in _open_rows]
        _bc.close()

        _bkc = _sq2.connect(_bkdb)
        _bkrow = _bkc.execute(
            "SELECT current_balance, daily_exposure, daily_pnl, starting_balance, system_status "
            "FROM bankroll ORDER BY id DESC LIMIT 1"
        ).fetchone()
        _bkc.close()
        if _bkrow:
            _bal, _exp, _dpnl, _start, _stat = _bkrow
            _bk = float(_bal)
            _cap_pct = (_exp / _start * 100.0) if _start else 0.0
            _bankroll_status = {
                "current_balance": round(float(_bal), 2),
                "daily_exposure": round(float(_exp), 2),
                "daily_pnl": round(float(_dpnl), 2),
                "starting_balance": round(float(_start), 2),
                "system_status": _stat,
                "is_halted": _stat == "HALT",
                "daily_cap_pct": round(_cap_pct, 1),
                "open_bet_count": len(_open_bets),
            }
    except Exception:
        pass

    try:
        from src.a2ui_builder import build_dashboard_ui

        return jsonify(
            {
                "data": state,
                "ui": build_dashboard_ui(state or [], {}, _bk),
                "ui_available": True,
                "open_bets": _open_bets,
                "bankroll_status": _bankroll_status,
            }
        )
    except Exception as _ui_err:
        return jsonify(
            {
                "data": state,
                "ui": None,
                "ui_available": False,
                "open_bets": _open_bets,
                "bankroll_status": _bankroll_status,
            }
        )


@app.route("/api/stream")
def stream_state():
    def event_stream():
        state_path = os.path.join(
            os.path.dirname(__file__), "..", "data", "todays_dashboard_state.json"
        )
        last_mtime = 0
        last_heartbeat = 0
        while True:
            try:
                # Keep-alive heartbeat every 30s so proxies/firewalls don't kill the connection
                now = time.time()
                if now - last_heartbeat >= 30:
                    yield ": heartbeat\n\n"
                    last_heartbeat = now
                if os.path.exists(state_path):
                    mtime = os.path.getmtime(state_path)
                    if mtime > last_mtime:
                        last_mtime = mtime
                        try:
                            with open(state_path, "r", encoding="utf-8") as f:
                                state = json.load(f)
                        except (json.JSONDecodeError, OSError) as _e:
                            print(f"[SSE] state file error: {_e}")
                            time.sleep(2)
                            continue
                        # Enrich stream with open bets + bankroll status
                        _s_open = []
                        _s_bk = {}
                        _s_bal = 0.0
                        try:
                            import sqlite3 as _ssq

                            _sbc = _ssq.connect(os.path.join(DATA_DIR, "bet_log.db"))
                            _sbc.row_factory = _ssq.Row
                            _s_open = [
                                dict(r)
                                for r in _sbc.execute(
                                    "SELECT match_id, market_type, side, entry_odds, stake, bet_source, placed_at "
                                    "FROM bet_log WHERE result='OPEN' ORDER BY placed_at DESC"
                                ).fetchall()
                            ]
                            _sbc.close()
                            _sbkc = _ssq.connect(os.path.join(DATA_DIR, "bankroll.db"))
                            _sbkr = _sbkc.execute(
                                "SELECT current_balance, daily_exposure, daily_pnl, starting_balance, system_status "
                                "FROM bankroll ORDER BY id DESC LIMIT 1"
                            ).fetchone()
                            _sbkc.close()
                            if _sbkr:
                                _s_bal = float(_sbkr[0])
                                _s_bk = {
                                    "current_balance": round(float(_sbkr[0]), 2),
                                    "daily_exposure": round(float(_sbkr[1]), 2),
                                    "daily_pnl": round(float(_sbkr[2]), 2),
                                    "starting_balance": round(float(_sbkr[3]), 2),
                                    "system_status": _sbkr[4],
                                    "is_halted": _sbkr[4] == "HALT",
                                    "daily_cap_pct": (
                                        round(
                                            float(_sbkr[1]) / float(_sbkr[3]) * 100, 1
                                        )
                                        if _sbkr[3]
                                        else 0.0
                                    ),
                                    "open_bet_count": len(_s_open),
                                }
                        except Exception:
                            pass
                        try:
                            from src.a2ui_builder import build_dashboard_ui as _bdu

                            _pl = {
                                "data": state,
                                "ui": _bdu(state or [], {}, _s_bal),
                                "ui_available": True,
                                "open_bets": _s_open,
                                "bankroll_status": _s_bk,
                            }
                        except Exception:
                            _pl = {
                                "data": state,
                                "ui": None,
                                "ui_available": False,
                                "open_bets": _s_open,
                                "bankroll_status": _s_bk,
                            }
                        yield f"data: {json.dumps(_pl)}\n\n"
            except Exception:
                pass
            time.sleep(2)  # Check file every 2 seconds

    return Response(event_stream(), mimetype="text/event-stream")


INITIAL_CAPITAL = 1000.0  # paper bankroll seed (reset 2026-06-22)


@app.route("/api/bankroll")
def get_bankroll():
    # Compute everything from bet_log (ground truth) — bankroll.db drifts due to
    # hash-settled noise and manual resets so we no longer trust it for display.
    daily = (
        query_db(
            "bet_log.db",
            "SELECT DATE(placed_at) as day, SUM(pnl) as dpnl FROM bet_log "
            "WHERE result NOT IN ('OPEN') GROUP BY day ORDER BY day ASC",
        )
        or []
    )

    chart_dates, chart_balances = [], []
    running = INITIAL_CAPITAL
    today_str = datetime.datetime.now().strftime("%Y-%m-%d")
    today_pnl = 0.0
    for row in daily:
        running += row["dpnl"] or 0.0
        chart_dates.append(row["day"])
        chart_balances.append(round(running, 2))
        if row["day"] == today_str:
            today_pnl = row["dpnl"] or 0.0

    all_time_pnl = running - INITIAL_CAPITAL
    roi = (all_time_pnl / INITIAL_CAPITAL) * 100

    return jsonify(
        {
            "current": round(running, 2),
            "roi": round(roi, 2),
            "pnl": round(today_pnl, 2),
            "chart_dates": chart_dates,
            "chart_balances": chart_balances,
        }
    )


@app.route("/api/edge_report")
def get_edge_report():
    def run(sql):
        return query_db("bet_log.db", sql) or []

    def to_row(r):
        wins, losses = r["wins"] or 0, r["losses"] or 0
        stake = r["stake"] or 0.0
        pnl = r["pnl"] or 0.0
        total = wins + losses
        win_rate = round(100 * wins / total, 1) if total else 0.0
        roi = round(100 * pnl / stake, 1) if stake else 0.0
        return {
            "label": r["label"],
            "bets": r["cnt"] or 0,
            "wins": wins,
            "losses": losses,
            "win_rate": win_rate,
            "stake": round(stake, 2),
            "pnl": round(pnl, 2),
            "roi": roi,
        }

    base = "WHERE result NOT IN ('OPEN','VOID')"

    strategies = [
        to_row(dict(r, label=r["bet_source"] or "AI"))
        for r in run(
            f"SELECT bet_source, COUNT(*) as cnt, "
            f"SUM(CASE WHEN result='W' THEN 1 ELSE 0 END) as wins, "
            f"SUM(CASE WHEN result='L' THEN 1 ELSE 0 END) as losses, "
            f"SUM(stake) as stake, SUM(pnl) as pnl "
            f"FROM bet_log {base} GROUP BY bet_source ORDER BY pnl DESC"
        )
    ]

    markets = [
        to_row(dict(r, label=r["market_type"] or "Unknown"))
        for r in run(
            f"SELECT market_type, COUNT(*) as cnt, "
            f"SUM(CASE WHEN result='W' THEN 1 ELSE 0 END) as wins, "
            f"SUM(CASE WHEN result='L' THEN 1 ELSE 0 END) as losses, "
            f"SUM(stake) as stake, SUM(pnl) as pnl "
            f"FROM bet_log {base} GROUP BY market_type ORDER BY pnl DESC"
        )
    ]

    leagues = [
        to_row(dict(r, label=r["league"]))
        for r in run(
            f"SELECT league, COUNT(*) as cnt, "
            f"SUM(CASE WHEN result='W' THEN 1 ELSE 0 END) as wins, "
            f"SUM(CASE WHEN result='L' THEN 1 ELSE 0 END) as losses, "
            f"SUM(stake) as stake, SUM(pnl) as pnl "
            f"FROM bet_log {base} AND league IS NOT NULL AND league != '' "
            f"GROUP BY league HAVING cnt >= 2 ORDER BY pnl DESC"
        )
    ]

    return jsonify({"strategies": strategies, "markets": markets, "leagues": leagues})


@app.route("/api/stair_balance")
def get_stair_balance():
    try:
        import requests

        res = requests.get(
            "https://stair-ai.com/api/v1/arena/agents/me",
            headers={"x-api-key": (os.getenv("STAIR_AI_API_KEY") or "").strip()},
            timeout=5,
        )
        if res.status_code == 200:
            data = res.json()
            # Production returns wallet at the top level with snake_case usdc fields.
            wallet = data.get("wallet") or data.get("data", {}).get("wallet") or {}
            return jsonify(
                {
                    "available": wallet.get("available_balance_usdc")
                    or wallet.get("availableBalance", 0),
                    "locked": wallet.get("locked_balance_usdc")
                    or wallet.get("lockedBalance", 0),
                }
            )
    except Exception:
        pass
    return jsonify({"available": 0, "locked": 0})


@app.route("/api/settled_ledger")
def get_settled_ledger():
    singles = query_db(
        "bet_log.db",
        "SELECT match_id, player_id, market_type, entry_odds, stake, result, pnl, placed_at, bet_source, league FROM bet_log ORDER BY placed_at DESC",
    )
    return jsonify(
        {
            "singles": [dict(r) for r in (singles or [])],
        }
    )


@app.route("/api/tracker")
def get_tracker():
    rows = query_db(
        "bet_log.db",
        """
        SELECT b.bet_id, b.match_id, b.player_id, b.market_type, b.entry_odds,
               b.closing_odds, b.edge_pct, b.stake, b.result, b.pnl, b.placed_at,
               b.bet_source, b.is_recommended, b.league, p.kickoff
        FROM bet_log b
        LEFT JOIN predictions p ON b.match_id = p.match_name
        ORDER BY b.placed_at DESC LIMIT 50
        """,
    )

    stats = {"W": 0, "L": 0, "OPEN": 0}
    financials = {
        "total_staked": 0.0,
        "total_won": 0.0,
        "total_lost": 0.0,
        "total_pending": 0.0,
    }
    # Count from database for ALL bets so the donut chart isn't empty!
    db_stats = query_db(
        "bet_log.db",
        "SELECT result, COUNT(*) as cnt, SUM(stake) as total_stake, SUM(pnl) as total_pnl FROM bet_log GROUP BY result",
    )
    if db_stats:
        for r in db_stats:
            res = r["result"]
            if res in stats:
                stats[res] = r["cnt"]

            stake = r["total_stake"] or 0.0
            pnl = r["total_pnl"] or 0.0

            financials["total_staked"] += stake
            if res == "W":
                financials["total_won"] += pnl
            elif res == "L":
                financials["total_lost"] += abs(pnl)
            elif res == "OPEN":
                financials["total_pending"] += stake

    return jsonify(
        {
            "bets": [dict(r) for r in (rows or [])],
            "stats": stats,
            "financials": financials,
        }
    )


@app.route("/api/place_bet", methods=["POST"])
def place_bet():
    try:
        data = request.get_json(silent=True) or {}
        bet_id = "UI_" + datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        match = str(data.get("match", "Unknown"))[:200]
        market = str(data.get("market", "1X2"))[:50]
        selection = str(data.get("selection", "Home"))[:100]
        try:
            stake = float(data.get("stake", 10.0))
            prob = float(data.get("prob", 50.0))
        except (TypeError, ValueError):
            return jsonify({"error": "stake and prob must be numbers"}), 400
        if not (0.01 <= stake <= 500):
            return jsonify({"error": "stake must be between 0.01 and 500"}), 400
        if not (0.1 <= prob <= 99.9):
            return jsonify({"error": "prob must be between 0.1 and 99.9"}), 400
        try:
            entry_odds = float(
                data.get("odds", round(100.0 / prob, 2) if prob > 0 else 1.0)
            )
        except (TypeError, ValueError):
            return jsonify({"error": "odds must be a number"}), 400
        if not (1.01 <= entry_odds <= 1000):
            return jsonify({"error": "odds must be between 1.01 and 1000"}), 400
        is_recommended = int(bool(data.get("recommended", 0)))

        closing_odds = round(entry_odds - 0.05, 2)
        edge = round((prob / 100.0) * entry_odds - 1.0, 3) * 100

        db_path = os.path.join(DATA_DIR, "bet_log.db")
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO bet_log 
            (bet_id, match_id, player_id, market_type, entry_odds, closing_odds, edge_pct, stake, result, pnl, placed_at, bet_source, is_recommended, line, side)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                bet_id,
                match,
                f"{match} ({selection})",
                market,
                entry_odds,
                closing_odds,
                edge,
                stake,
                "OPEN",
                0.0,
                datetime.datetime.now().isoformat(),
                "USER",
                is_recommended,
                2.5,
                selection,
            ),
        )

        conn.commit()
        conn.close()

        # Deduct stake from bankroll via tracker
        from src.bankroll_tracker import register_bet

        register_bet(stake)

        return jsonify({"status": "success", "bet_id": bet_id})
    except Exception as e:
        print("Bet Error:", e)
        return jsonify({"error": str(e)}), 500


@app.route("/api/clv")
def get_clv():
    """CLV dashboard — closing-line value stats for STEAM bets broken down by
    league, week, and move-size bucket. Returns only bets that have a closing_odds
    recorded so the numbers are grounded in real prices."""
    import os as _os

    SIGNALS_DB = _os.path.join(
        DATA_DIR, "deepfield_browser_data", "completed_fixtures.db"
    )

    rows = query_db(
        "bet_log.db",
        """SELECT b.match_id, b.league, b.entry_odds, b.closing_odds, b.clv,
                  b.result, b.pnl, b.stake, b.placed_at, b.fixture_id, b.bet_id
           FROM bet_log b
           WHERE b.bet_source = 'STEAM' AND b.result IN ('W','L','WIN','LOSS')
           ORDER BY b.placed_at ASC""",
    )

    # Enrich with steam_move from signals db
    move_map = {}
    try:
        import sqlite3 as _sql

        con2 = _sql.connect(SIGNALS_DB)
        sigs = con2.execute(
            "SELECT fixture_id, steam_move FROM steam_signals"
        ).fetchall()
        con2.close()
        move_map = {str(r[0]): r[1] for r in sigs}
    except Exception:
        pass

    bets = []
    for r in rows or []:
        d = dict(r)
        d["steam_move_pct"] = round(
            move_map.get(str(d.get("fixture_id", "")), 0) * 100, 1
        )
        bets.append(d)

    settled_clv = [b for b in bets if b.get("clv") is not None]

    def _roi(pnl, staked):
        return round(pnl / staked * 100, 1) if staked else 0

    def _summary(subset):
        if not subset:
            return None
        clv_vals = [b["clv"] * 100 for b in subset if b.get("clv") is not None]
        pnl = sum(b.get("pnl") or 0 for b in subset)
        staked = sum(b.get("stake") or 0 for b in subset)
        wins = sum(1 for b in subset if b.get("result") in ("W", "WIN"))
        avg_clv = round(sum(clv_vals) / len(clv_vals), 2) if clv_vals else None
        # 95% confidence interval for avg CLV via t-distribution (normal approx for n≥30)
        ci_lower = ci_upper = None
        nc = len(clv_vals)
        if nc >= 2 and avg_clv is not None:
            import math

            variance = sum((v - avg_clv) ** 2 for v in clv_vals) / (nc - 1)
            se = math.sqrt(variance / nc)
            z = (
                1.96
                if nc >= 30
                else (2.045 if nc >= 25 else (2.131 if nc >= 20 else 2.571))
            )
            ci_lower = round(avg_clv - z * se, 1)
            ci_upper = round(avg_clv + z * se, 1)
        return {
            "n": len(subset),
            "wins": wins,
            "hit_rate": round(wins / len(subset) * 100, 1),
            "roi": _roi(pnl, staked),
            "pnl": round(pnl, 2),
            "staked": round(staked, 2),
            "avg_clv": avg_clv,
            "clv_n": nc,
            "ci_lower": ci_lower,
            "ci_upper": ci_upper,
        }

    # By league
    from collections import defaultdict

    by_league = defaultdict(list)
    for b in bets:
        by_league[b.get("league") or "Unknown"].append(b)
    leagues_out = {
        lg: _summary(v) for lg, v in sorted(by_league.items(), key=lambda x: -len(x[1]))
    }

    # By week
    by_week = defaultdict(list)
    for b in bets:
        try:
            import datetime

            d = datetime.date.fromisoformat((b.get("placed_at") or "")[:10])
            week = f"{d.isocalendar()[0]}-W{d.isocalendar()[1]:02d}"
        except Exception:
            week = "Unknown"
        by_week[week].append(b)
    weeks_out = {w: _summary(v) for w, v in sorted(by_week.items())}

    # By move bucket
    move_buckets = [
        ("5-8%", 5, 8),
        ("8-12%", 8, 12),
        ("12-20%", 12, 20),
        ("20%+", 20, 999),
    ]
    moves_out = {}
    for label, lo, hi in move_buckets:
        bucket = [b for b in bets if lo <= b["steam_move_pct"] < hi]
        moves_out[label] = _summary(bucket)

    # By monotonicity bucket (requires bet_log.monotonicity column from CLV attribution)
    mono_buckets = [
        ("0.0-0.25", 0.0, 0.25),
        ("0.25-0.5", 0.25, 0.5),
        ("0.5-0.75", 0.5, 0.75),
        ("0.75-1.0", 0.75, 1.01),
    ]
    mono_out = {}
    mono_rows = (
        query_db(
            "bet_log.db",
            """SELECT b.match_id, b.league, b.entry_odds, b.closing_odds, b.clv,
                  b.result, b.pnl, b.stake, b.placed_at, b.fixture_id, b.monotonicity
           FROM bet_log b
           WHERE b.bet_source = 'STEAM' AND b.result IN ('W','L','WIN','LOSS')
             AND b.monotonicity IS NOT NULL
           ORDER BY b.placed_at ASC""",
        )
        or []
    )
    for label, lo, hi in mono_buckets:
        bucket = [dict(r) for r in mono_rows if lo <= (r[10] or 0) < hi]
        mono_out[label] = _summary(bucket)

    # Signal decay: rolling windows (last 50, last 100, lifetime) for STEAM
    decay_out = {}
    sorted_bets = sorted(bets, key=lambda b: b.get("placed_at") or "")
    for window_label, window_n in [
        ("last_50", 50),
        ("last_100", 100),
        ("lifetime", None),
    ]:
        subset = sorted_bets[-window_n:] if window_n else sorted_bets
        decay_out[window_label] = _summary(subset)

    # Load signal discovery results; merge with registry for live status
    signals_out = {}
    try:
        import json as _json, sqlite3 as _sql

        sig_path = _os.path.join(DATA_DIR, "signal_discovery_results.json")
        # Load registry state
        reg = {}
        try:
            _rcon = _sql.connect(
                _os.path.join(
                    DATA_DIR, "deepfield_browser_data", "completed_fixtures.db"
                )
            )
            for row in _rcon.execute(
                "SELECT signal_name, enabled, promoted, updated_at FROM signal_registry"
            ):
                reg[row[0]] = {
                    "registry_enabled": bool(row[1]),
                    "registry_promoted": bool(row[2]),
                    "registry_updated": row[3],
                }
            _rcon.close()
        except Exception:
            pass
        if _os.path.exists(sig_path):
            disc = _json.load(open(sig_path))
            raw_sigs = disc.get("signals", {})
            for sig_name, r in raw_sigs.items():
                n = r.get("n", 0)
                clv = r.get("avg_clv")
                if n >= 100 and clv is not None:
                    auto_status = (
                        "PROMOTE"
                        if clv >= 3.0
                        else ("DISABLE" if clv < 0.0 else "WATCH")
                    )
                else:
                    auto_status = "WATCH"
                signals_out[sig_name] = {
                    **r,
                    "auto_status": auto_status,
                    **reg.get(sig_name, {}),
                }
    except Exception:
        pass

    # Scatter data for CLV attribution plot (move_size x CLV, bubble = monotonicity)
    scatter_rows = (
        query_db(
            "bet_log.db",
            """SELECT match_id, entry_odds, clv, move_size, monotonicity, league, placed_at, bet_id
           FROM bet_log
           WHERE bet_source='STEAM' AND result IN ('W','L','WIN','LOSS')
             AND clv IS NOT NULL AND move_size IS NOT NULL
           ORDER BY placed_at ASC""",
        )
        or []
    )
    scatter_out = [
        {
            "match": r[0],
            "entry_odds": r[1],
            "clv": round(r[2] * 100, 2),
            "move_size": r[3],
            "monotonicity": r[4],
            "league": r[5],
            "bet_id": r[7],
        }
        for r in scatter_rows
    ]

    # Rolling windows (7d / 30d / 90d) for regime / decay detection
    import datetime as _dt

    _now = _dt.datetime.now()
    rolling_out = {}
    for label, days in [("7d", 7), ("30d", 30), ("90d", 90)]:
        cutoff = (_now - _dt.timedelta(days=days)).isoformat()
        subset = [b for b in bets if (b.get("placed_at") or "") >= cutoff]
        rolling_out[label] = _summary(subset)

    # Validation status from signal_validation table
    validation_out = {}
    try:
        import sqlite3 as _sql2

        _vcon = _sql2.connect(
            _os.path.join(DATA_DIR, "deepfield_browser_data", "completed_fixtures.db")
        )
        _vrows = _vcon.execute(
            "SELECT signal_name, discovery_date, validation_bets, validation_clv, status FROM signal_validation"
        ).fetchall()
        _vcon.close()
        for row in _vrows:
            validation_out[row[0]] = {
                "discovery_date": row[1],
                "validation_bets": row[2],
                "validation_clv": row[3],
                "status": row[4],
            }
        # Merge into signals_out
        for sig, vdata in validation_out.items():
            if sig in signals_out:
                signals_out[sig]["validation"] = vdata
    except Exception:
        pass

    # Research Health Score (0–100)
    def _health_score(ov, roll):
        score = 0.0
        n = (ov or {}).get("n", 0)
        clv = (ov or {}).get("avg_clv") or 0
        ci_lo = (ov or {}).get("ci_lower")
        ci_hi = (ov or {}).get("ci_upper")
        # Sample size (max 30 pts)
        score += min(30.0, n / 300.0 * 30.0)
        # CLV magnitude (max 25 pts — 10% CLV = full score)
        score += min(25.0, max(0.0, clv / 10.0 * 25.0))
        # CI quality (max 20 pts)
        if ci_lo is not None and ci_hi is not None:
            score += 20.0 if ci_lo > 0 else (0.0 if (ci_hi or 0) < 0 else 10.0)
        # 7d vs 30d trend (max 15 pts)
        clv_7d = (roll.get("7d") or {}).get("avg_clv")
        clv_30d = (roll.get("30d") or {}).get("avg_clv")
        if clv_7d is not None and clv_30d is not None:
            score += (
                15.0 if clv_7d >= clv_30d else (7.5 if clv_7d >= clv_30d - 3 else 0.0)
            )
        elif clv > 0:
            score += 7.5
        # Signal diversity bonus (max 10 pts)
        n_promoted = sum(
            1
            for s in signals_out.values()
            if s.get("registry_promoted") or s.get("auto_status") == "PROMOTE"
        )
        score += min(10.0, n_promoted * 3.3)
        return round(score)

    ov_summary = _summary(bets)
    health = _health_score(ov_summary, rolling_out)

    return jsonify(
        {
            "overall": ov_summary,
            "by_league": leagues_out,
            "by_week": weeks_out,
            "by_move_bucket": moves_out,
            "by_monotonicity": mono_out,
            "decay": decay_out,
            "rolling": rolling_out,
            "health_score": health,
            "signals": signals_out,
            "validation": validation_out,
            "scatter": scatter_out,
            "bets": bets,
        }
    )


@app.route("/api/signal_registry", methods=["GET"])
def get_signal_registry():
    """Return all signal_registry rows for the dashboard control panel."""
    import sqlite3 as _sql

    reg_db = os.path.join(DATA_DIR, "deepfield_browser_data", "completed_fixtures.db")
    try:
        con = _sql.connect(reg_db)
        rows = con.execute(
            "SELECT signal_name, enabled, promoted, min_samples, owner, updated_at FROM signal_registry ORDER BY signal_name"
        ).fetchall()
        con.close()
        return jsonify(
            [
                {
                    "signal_name": r[0],
                    "enabled": bool(r[1]),
                    "promoted": bool(r[2]),
                    "min_samples": r[3],
                    "owner": r[4],
                    "updated_at": r[5],
                }
                for r in rows
            ]
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/signal_registry/<signal_name>", methods=["POST"])
def update_signal_registry(signal_name):
    """Toggle enabled/promoted for a signal. Body: {enabled?: bool, promoted?: bool}"""
    import sqlite3 as _sql

    reg_db = os.path.join(DATA_DIR, "deepfield_browser_data", "completed_fixtures.db")
    data = request.get_json() or {}
    try:
        con = _sql.connect(reg_db)
        if "enabled" in data:
            con.execute(
                "UPDATE signal_registry SET enabled=?, updated_at=CURRENT_TIMESTAMP WHERE signal_name=?",
                (1 if data["enabled"] else 0, signal_name),
            )
        if "promoted" in data:
            con.execute(
                "UPDATE signal_registry SET promoted=?, updated_at=CURRENT_TIMESTAMP WHERE signal_name=?",
                (1 if data["promoted"] else 0, signal_name),
            )
        con.commit()
        con.close()
        return jsonify({"status": "ok", "signal": signal_name})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/bet_replay/<bet_id>")
def get_bet_replay(bet_id):
    """Return bet details + full odds timeline for the Replay Explorer."""
    import sqlite3 as _sql

    SIGNALS_DB = os.path.join(
        DATA_DIR, "deepfield_browser_data", "completed_fixtures.db"
    )

    # Fetch bet metadata
    bet_rows = query_db(
        "bet_log.db",
        """SELECT bet_id, match_id, market_type, entry_odds, closing_odds, clv,
                  result, pnl, stake, placed_at, league, move_size, monotonicity, fixture_id, signal_name
           FROM bet_log WHERE bet_id = ?""",
        (bet_id,),
    )
    if not bet_rows:
        return jsonify({"error": "Bet not found"}), 404
    bet = dict(bet_rows[0])
    if bet.get("clv") is not None:
        bet["clv_pct"] = round(bet["clv"] * 100, 2)

    # Fetch odds timeline from odds_history
    timeline = []
    fid = bet.get("fixture_id")
    mtype = bet.get("market_type", "1X2")
    if fid:
        try:
            con = _sql.connect(SIGNALS_DB)
            oh_rows = con.execute(
                "SELECT selection, odds, timestamp FROM odds_history "
                "WHERE fixture_id=? AND market=? ORDER BY timestamp ASC",
                (str(fid), mtype),
            ).fetchall()
            con.close()
            # Group by timestamp → {ts: {sel: odds}}
            from collections import defaultdict

            by_ts: dict = defaultdict(dict)
            for sel, odds, ts in oh_rows:
                if odds and odds > 0:
                    by_ts[ts][sel] = odds

            # De-vig each snapshot
            def _dv(snap):
                inv = {s: 1 / o for s, o in snap.items() if o and o > 0}
                tot = sum(inv.values())
                return (
                    {s: round(v / tot * 100, 1) for s, v in inv.items()}
                    if tot > 0
                    else {}
                )

            for ts in sorted(by_ts):
                snap = by_ts[ts]
                probs = _dv(snap)
                timeline.append(
                    {
                        "ts": ts,
                        "odds": {s: round(o, 3) for s, o in snap.items()},
                        "prob": probs,
                    }
                )
        except Exception as e:
            timeline = [{"error": str(e)}]

    return jsonify({"bet": bet, "timeline": timeline})


@app.route("/api/research_runs")
def get_research_runs():
    """Return last N nightly audit records from research_runs table."""
    import sqlite3 as _sql

    SIGNALS_DB = os.path.join(
        DATA_DIR, "deepfield_browser_data", "completed_fixtures.db"
    )
    limit = int(request.args.get("limit", 30))
    try:
        con = _sql.connect(SIGNALS_DB)
        rows = con.execute(
            """SELECT run_id, run_at, signals_evaluated, bets_analyzed,
                      promoted, disabled, health_score, avg_clv, jobs_ok
               FROM research_runs ORDER BY run_id DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        con.close()
        runs = []
        for r in rows:
            import json as _j

            runs.append(
                {
                    "run_id": r[0],
                    "run_at": r[1],
                    "signals_evaluated": r[2],
                    "bets_analyzed": r[3],
                    "promoted": _j.loads(r[4] or "[]"),
                    "disabled": _j.loads(r[5] or "[]"),
                    "health_score": r[6],
                    "avg_clv": r[7],
                    "jobs_ok": _j.loads(r[8] or "{}"),
                }
            )
        return jsonify(runs)
    except Exception as e:
        return jsonify([])


@app.route("/api/signal_lifecycle")
def get_signal_lifecycle():
    """Return current lifecycle stage for every signal plus full transition history."""
    import sqlite3 as _sql

    SIGNALS_DB = os.path.join(
        DATA_DIR, "deepfield_browser_data", "completed_fixtures.db"
    )
    try:
        con = _sql.connect(SIGNALS_DB)
        # Current stage = most recent row per signal
        cur_rows = con.execute(
            """SELECT signal_name, stage, entered_at, n, avg_clv, metadata
               FROM signal_lifecycle
               WHERE id IN (
                   SELECT MAX(id) FROM signal_lifecycle GROUP BY signal_name
               )
               ORDER BY signal_name"""
        ).fetchall()
        # History for timeline
        hist_rows = con.execute(
            """SELECT signal_name, stage, entered_at FROM signal_lifecycle
               ORDER BY signal_name, id ASC"""
        ).fetchall()
        con.close()
        import json as _j

        current = {}
        for r in cur_rows:
            meta = {}
            try:
                meta = _j.loads(r[5] or "{}")
            except Exception:
                pass
            # Days in current stage
            import datetime as _dt

            try:
                entered = (
                    _dt.datetime.fromisoformat(r[2]) if r[2] else _dt.datetime.now()
                )
                days_in_stage = (_dt.datetime.now() - entered).days
            except Exception:
                days_in_stage = 0
            current[r[0]] = {
                "signal_name": r[0],
                "stage": r[1],
                "entered_at": r[2],
                "n": r[3],
                "avg_clv": r[4],
                "days_in_stage": days_in_stage,
                **meta,
            }
        history = {}
        for r in hist_rows:
            history.setdefault(r[0], []).append({"stage": r[1], "at": r[2]})
        return jsonify({"current": current, "history": history})
    except Exception as e:
        return jsonify({"current": {}, "history": {}, "error": str(e)})


@app.route("/api/edge_attribution")
def get_edge_attribution():
    """Break down CLV contribution by move_size, monotonicity, league, and timing."""
    rows = query_db(
        "bet_log.db",
        """SELECT match_id, league, entry_odds, closing_odds, clv,
                  result, pnl, stake, placed_at, move_size, monotonicity
           FROM bet_log
           WHERE bet_source='STEAM' AND result IN ('W','L','WIN','LOSS')
             AND clv IS NOT NULL""",
    )
    if not rows:
        return jsonify({"error": "no_data"})

    bets = [dict(r) for r in rows]
    n_total = len(bets)
    clv_vals = [b["clv"] * 100 for b in bets]
    overall = sum(clv_vals) / len(clv_vals) if clv_vals else 0

    def _bucket_contrib(key_fn, label_fn, bets):
        buckets: dict = {}
        for b in bets:
            k = key_fn(b)
            if k is None:
                continue
            buckets.setdefault(k, []).append(b["clv"] * 100)
        result = []
        for k in sorted(buckets):
            vals = buckets[k]
            avg = sum(vals) / len(vals)
            frac = len(vals) / n_total
            result.append(
                {
                    "label": label_fn(k),
                    "n": len(vals),
                    "avg_clv": round(avg, 2),
                    "contribution": round((avg - overall) * frac, 2),
                    "weight_pct": round(frac * 100, 1),
                }
            )
        return result

    # Move size buckets
    def _move_key(b):
        m = b.get("move_size")
        if m is None:
            return None
        if m < 8:
            return 0
        if m < 12:
            return 1
        if m < 18:
            return 2
        return 3

    move_labels = {0: "5-8%", 1: "8-12%", 2: "12-18%", 3: "18%+"}
    move_out = _bucket_contrib(_move_key, lambda k: move_labels.get(k, str(k)), bets)

    # Monotonicity buckets
    def _mono_key(b):
        m = b.get("monotonicity")
        if m is None:
            return None
        if m < 0.25:
            return 0
        if m < 0.50:
            return 1
        if m < 0.75:
            return 2
        return 3

    mono_labels = {0: "0.00-0.25", 1: "0.25-0.50", 2: "0.50-0.75", 3: "0.75-1.00"}
    mono_out = _bucket_contrib(_mono_key, lambda k: mono_labels.get(k, str(k)), bets)

    # League (top 6 by count, rest = Other)
    from collections import Counter

    league_counts = Counter(b.get("league") or "Unknown" for b in bets)
    top_leagues = {lg for lg, _ in league_counts.most_common(6)}

    def _lg_key(b):
        lg = b.get("league") or "Unknown"
        return lg if lg in top_leagues else "Other"

    league_out = _bucket_contrib(_lg_key, lambda k: k, bets)
    league_out.sort(key=lambda r: r["n"], reverse=True)

    # Timing buckets (hour of day placed_at)
    def _hour_key(b):
        pa = b.get("placed_at") or ""
        try:
            import datetime as _dt

            h = _dt.datetime.fromisoformat(pa).hour
            if h < 6:
                return 0
            if h < 12:
                return 1
            if h < 18:
                return 2
            return 3
        except Exception:
            return None

    time_labels = {0: "00-06h", 1: "06-12h", 2: "12-18h", 3: "18-24h"}
    timing_out = _bucket_contrib(_hour_key, lambda k: time_labels.get(k, str(k)), bets)

    return jsonify(
        {
            "overall_clv": round(overall, 2),
            "n_total": n_total,
            "by_move_size": move_out,
            "by_monotonicity": mono_out,
            "by_league": league_out,
            "by_timing": timing_out,
        }
    )


@app.route("/api/experiments", methods=["GET", "POST"])
def manage_experiments():
    """GET: list all experiments. POST: create a new one."""
    import sqlite3 as _sql
    import hashlib as _hl

    SIGNALS_DB = os.path.join(
        DATA_DIR, "deepfield_browser_data", "completed_fixtures.db"
    )

    def _ensure_table(con):
        con.execute(
            """CREATE TABLE IF NOT EXISTS experiments (
            id              TEXT PRIMARY KEY,
            start_date      TEXT,
            end_date        TEXT,
            config_hash     TEXT,
            hypothesis      TEXT,
            config_snapshot TEXT,
            status          TEXT DEFAULT 'ACTIVE',
            result          TEXT,
            created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
        )"""
        )

    if request.method == "GET":
        try:
            con = _sql.connect(SIGNALS_DB)
            _ensure_table(con)
            rows = con.execute(
                "SELECT id, start_date, end_date, config_hash, hypothesis, status, result, created_at "
                "FROM experiments ORDER BY start_date DESC"
            ).fetchall()
            con.close()
            exps = []
            for r in rows:
                exps.append(
                    {
                        "id": r[0],
                        "start_date": r[1],
                        "end_date": r[2],
                        "config_hash": r[3],
                        "hypothesis": r[4],
                        "status": r[5],
                        "result": r[6],
                        "created_at": r[7],
                    }
                )
            return jsonify(exps)
        except Exception as e:
            return jsonify([])

    # POST: create a new experiment
    body = request.json or {}
    hypothesis = (body.get("hypothesis") or "").strip()
    if not hypothesis:
        return jsonify({"error": "hypothesis required"}), 400
    try:
        # Snapshot current settings.json + registry as the experiment config
        settings_snap = {}
        try:
            with open(SETTINGS_FILE) as f:
                settings_snap = json.load(f)
        except Exception:
            pass
        reg_snap = {}
        try:
            con2 = _sql.connect(SIGNALS_DB)
            for row in con2.execute(
                "SELECT signal_name, enabled, promoted FROM signal_registry"
            ):
                reg_snap[row[0]] = {"enabled": bool(row[1]), "promoted": bool(row[2])}
            con2.close()
        except Exception:
            pass
        config = {"settings": settings_snap, "signal_registry": reg_snap}
        config_json = json.dumps(config, sort_keys=True)
        config_hash = _hl.md5(config_json.encode()).hexdigest()[:8]

        # Auto-increment experiment ID
        con = _sql.connect(SIGNALS_DB)
        _ensure_table(con)
        count = con.execute("SELECT COUNT(*) FROM experiments").fetchone()[0]
        exp_id = f"EXP{(count + 1):03d}"
        today = __import__("datetime").date.today().isoformat()

        # Mark any currently ACTIVE experiment as COMPLETED before creating new one
        if body.get("supersede", False):
            con.execute(
                "UPDATE experiments SET status='COMPLETED', end_date=? WHERE status='ACTIVE'",
                (today,),
            )

        con.execute(
            "INSERT OR IGNORE INTO experiments "
            "(id, start_date, config_hash, hypothesis, config_snapshot, status) "
            "VALUES (?,?,?,?,?,?)",
            (exp_id, today, config_hash, hypothesis, config_json, "ACTIVE"),
        )
        con.commit()
        con.close()
        return jsonify({"id": exp_id, "config_hash": config_hash, "status": "ACTIVE"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/experiments/<exp_id>", methods=["PATCH"])
def update_experiment(exp_id):
    """Update experiment status or result."""
    import sqlite3 as _sql

    SIGNALS_DB = os.path.join(
        DATA_DIR, "deepfield_browser_data", "completed_fixtures.db"
    )
    body = request.json or {}
    try:
        con = _sql.connect(SIGNALS_DB)
        today = __import__("datetime").date.today().isoformat()
        if "status" in body:
            end_date = today if body["status"] in ("COMPLETED", "CANCELLED") else None
            con.execute(
                "UPDATE experiments SET status=?, end_date=? WHERE id=?",
                (body["status"], end_date, exp_id),
            )
        if "result" in body:
            con.execute(
                "UPDATE experiments SET result=? WHERE id=?",
                (
                    (
                        json.dumps(body["result"])
                        if isinstance(body["result"], dict)
                        else body["result"]
                    ),
                    exp_id,
                ),
            )
        con.commit()
        con.close()
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/counterfactual")
def get_counterfactual():
    """Re-evaluate STEAM_FWD at multiple thresholds against historical data."""
    import sqlite3 as _sql
    from collections import defaultdict
    import re as _re

    SIGNALS_DB = os.path.join(
        DATA_DIR, "deepfield_browser_data", "completed_fixtures.db"
    )

    thresholds_raw = request.args.get("thresholds", "3,5,7,10,15")
    signal_type = request.args.get("signal", "STEAM_FWD")
    thresholds = [float(t) / 100.0 for t in thresholds_raw.split(",") if t.strip()]

    # Load odds history
    try:
        con = _sql.connect(SIGNALS_DB)
        oh_rows = con.execute(
            "SELECT fixture_id, selection, odds, timestamp FROM odds_history "
            "WHERE market='1X2' ORDER BY fixture_id, timestamp ASC"
        ).fetchall()
        con.close()
    except Exception as e:
        return jsonify({"error": str(e)})

    by_fid: dict = defaultdict(list)
    for fid, sel, odds, ts in oh_rows:
        by_fid[str(fid)].append((sel, float(odds) if odds else 0, ts))

    # Load settled bets
    try:
        bcon = _sql.connect(os.path.join(DATA_DIR, "bet_log.db"))
        bet_rows = bcon.execute(
            "SELECT fixture_id, player_id, result, entry_odds, closing_odds "
            "FROM bet_log WHERE bet_source='STEAM' AND result IN ('W','L','WIN','LOSS')"
        ).fetchall()
        bcon.close()
    except Exception:
        bet_rows = []

    settled: dict = {}
    for fid, pid, result, eo, co in bet_rows:
        if not fid:
            continue
        m = _re.search(r"\((Home \(1\)|Away \(2\)|Draw)\)$", pid or "")
        sel = m.group(1) if m else pid
        clv = (eo / co - 1) if co and co > 0 else None
        settled.setdefault(str(fid), {})[sel] = {
            "won": result in ("W", "WIN"),
            "clv": clv,
        }

    def _devig(odds_dict):
        inv = {s: 1 / o for s, o in odds_dict.items() if o and o > 0}
        tot = sum(inv.values())
        return (
            {s: v / tot for s, v in inv.items()} if tot > 0 and len(inv) >= 2 else None
        )

    def _steam_fire(snaps, threshold):
        by_ts: dict = defaultdict(dict)
        for sel, odds, ts in snaps:
            if odds > 0:
                by_ts[ts][sel] = odds
        series = {ts: _devig(by_ts[ts]) for ts in sorted(by_ts) if _devig(by_ts[ts])}
        ts_list = sorted(series)
        if len(ts_list) < 2:
            return None
        first, last = series[ts_list[0]], series[ts_list[-1]]
        best = max(
            ((s, last[s] - first[s]) for s in set(first) & set(last)),
            key=lambda x: x[1],
            default=None,
        )
        return best if (best and best[1] >= threshold) else None

    results = []
    for thr in thresholds:
        n = wins = clv_sum = clv_n = 0
        for fid, snaps in by_fid.items():
            if fid not in settled:
                continue
            hit = _steam_fire(snaps, thr)
            if not hit:
                continue
            sel_key = hit[0]
            info = next(
                (v for k, v in settled[fid].items() if sel_key == k or sel_key in k),
                None,
            )
            if not info:
                continue
            n += 1
            if info["won"]:
                wins += 1
            if info["clv"] is not None:
                clv_sum += info["clv"]
                clv_n += 1
        avg_clv = round(clv_sum / clv_n * 100, 2) if clv_n > 0 else None
        results.append(
            {
                "threshold_pct": round(thr * 100, 1),
                "n": n,
                "wins": wins,
                "hit": round(wins / n * 100, 1) if n else 0,
                "avg_clv": avg_clv,
                "clv_n": clv_n,
            }
        )

    # Find optimal
    scored = [(r, r["avg_clv"] or -999) for r in results if r["n"] >= 5]
    optimal = max(scored, key=lambda x: x[1])[0] if scored else None

    return jsonify(
        {
            "signal_type": signal_type,
            "thresholds_pct": thresholds_raw,
            "results": results,
            "optimal": optimal,
        }
    )


_SETTINGS_SCHEMA = {
    # key: (type, min, max)  — only whitelisted keys accepted
    "allowed_markets": list,
    "exclude_draws": bool,
    "league_blocklist": list,
    "steam_betting_enabled": bool,
    "steam_flat_stake": (float, 0, 500),
    "steam_min_move_pct": (float, 0, 50),
    "steam_kelly_frac": (float, 0, 1),
    "ai_real_staking_enabled": bool,
    "kelly_multiplier": (float, 0.01, 1.0),
    "min_ev_threshold": (float, 0, 1),
    "max_exposure_pct": (float, 0, 0.25),
    "min_confidence_pct": (float, 0, 100),
    "require_steam_confirm": bool,
    "edge_cap_pct": (float, 0, 50),
    "market_blend_weight": (float, 0, 1),
    "refresh_interval_sec": (float, 5, 300),
    "show_live_matches": bool,
    "max_odds_staleness_min": (float, 1, 1440),
    "arena_max_per_order": (float, 0.5, 25),
    "arena_daily_cap": (float, 0, 100),
    "arena_wallet_buffer": (float, 0.5, 50),
    "conf_min": (float, 0.3, 0.99),
    "edge_min": (float, 0, 0.5),
    "ah_betting_enabled": bool,
    "daily_stop_loss_pct": (float, 0.01, 1.0),
    "max_drawdown_pct": (float, 0.01, 1.0),
    "max_daily_exposure_pct": (float, 0.01, 1.0),
}


@app.route("/api/settings", methods=["GET", "POST"])
def manage_settings():
    if request.method == "POST":
        incoming = request.get_json(silent=True) or {}
        # Load current settings to merge into (unknown keys preserved, not overwritten)
        try:
            with open(SETTINGS_FILE, "r") as f:
                current = json.load(f)
        except (OSError, ValueError):
            current = {}
        errors = []
        for key, val in incoming.items():
            spec = _SETTINGS_SCHEMA.get(key)
            if spec is None:
                errors.append(f"Unknown setting: {key}")
                continue
            if isinstance(spec, tuple):
                typ, lo, hi = spec
                try:
                    val = typ(val)
                except (TypeError, ValueError):
                    errors.append(f"{key} must be {typ.__name__}")
                    continue
                if not (lo <= val <= hi):
                    errors.append(f"{key}={val} out of range [{lo}, {hi}]")
                    continue
            elif spec is bool:
                if not isinstance(val, bool):
                    errors.append(f"{key} must be boolean")
                    continue
            elif spec is list:
                if not isinstance(val, list):
                    errors.append(f"{key} must be a list")
                    continue
            current[key] = val
        if errors:
            return jsonify({"error": "Validation failed", "details": errors}), 400
        with open(SETTINGS_FILE, "w") as f:
            json.dump(current, f, indent=2)
        return jsonify({"status": "success"})

    with open(SETTINGS_FILE, "r") as f:
        return jsonify(json.load(f))


@app.route("/api/comparisons")
def get_comparisons_list():
    state_path = os.path.join(DATA_DIR, "todays_dashboard_state.json")
    completed_path = os.path.join(DATA_DIR, "completed_comparisons.json")

    completed = {}
    if os.path.exists(completed_path):
        try:
            with open(completed_path, "r", encoding="utf-8") as f:
                completed = json.load(f)
        except Exception:
            pass

    matches_list = []
    if os.path.exists(state_path):
        try:
            with open(state_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for m in data:
                if m.get("prediction") is not None:
                    fid_str = str(m["fixture_id"])
                    has_actuals = fid_str in completed or fid_str == "15458376"
                    matches_list.append(
                        {
                            "fixture_id": m["fixture_id"],
                            "match": m["match"],
                            "league": m["league"],
                            "kickoff": m["kickoff"],
                            "status_code": m["status_code"],
                            "has_actuals": has_actuals,
                        }
                    )
        except Exception as e:
            print("Error parsing state JSON:", e)

    return jsonify(matches_list)


@app.route("/api/comparison/<fixture_id>")
def get_comparison(fixture_id):

    db_path = os.path.join(DATA_DIR, "bet_log.db")
    prediction = None
    if os.path.exists(db_path):
        try:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute(
                "SELECT * FROM predictions WHERE fixture_id = ?", (str(fixture_id),)
            )
            row = cur.fetchone()
            if row:
                extra = {}
                if row["extra_json"]:
                    try:
                        extra = json.loads(row["extra_json"])
                    except Exception:
                        pass
                prediction = {
                    "fixture_id": int(row["fixture_id"]),
                    "match": row["match_name"],
                    "league": row["league"],
                    "kickoff": row["kickoff"],
                    "prediction": row["prediction"],
                    "expected_score": row["expected_score"],
                    "has_lineup": bool(row["has_lineup"]),
                    "team_impacts": extra.get("team_impacts", ""),
                    "corners": extra.get("corners", ""),
                    "fouls": extra.get("fouls", ""),
                    "cards": extra.get("cards", ""),
                    "home_players": extra.get("home_players", []),
                    "away_players": extra.get("away_players", []),
                    "detailed_prediction": extra.get("detailed_prediction", {}),
                    "markets": {
                        "1X2": [
                            {"selection": "Home (1)", "prob": row["home_prob"]},
                            {"selection": "Draw (X)", "prob": row["draw_prob"]},
                            {"selection": "Away (2)", "prob": row["away_prob"]},
                        ],
                        "Over/Under 2.5": [
                            {"selection": "Over 2.5", "prob": row["over_prob"]},
                            {"selection": "Under 2.5", "prob": row["under_prob"]},
                        ],
                        "BTTS": [
                            {"selection": "Yes", "prob": row["btts_yes_prob"]},
                            {"selection": "No", "prob": row["btts_no_prob"]},
                        ],
                    },
                }
            conn.close()
        except Exception as e:
            print("Error loading prediction for comparison:", e)

    if not prediction:
        state_path = os.path.join(DATA_DIR, "todays_dashboard_state.json")
        if os.path.exists(state_path):
            try:
                with open(state_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for m in data:
                    if str(m["fixture_id"]) == str(fixture_id):
                        prediction = m.get("prediction")
                        break
            except Exception:
                pass

    actuals = None

    if not prediction:
        return jsonify({"error": "Prediction not found"}), 404

    completed_path = os.path.join(DATA_DIR, "completed_comparisons.json")
    if os.path.exists(completed_path):
        try:
            with open(completed_path, "r", encoding="utf-8") as f:
                completed = json.load(f)
            if str(fixture_id) in completed:
                actuals = completed[str(fixture_id)]
        except Exception:
            pass

    if not actuals:
        state_path = os.path.join(DATA_DIR, "todays_dashboard_state.json")
        if os.path.exists(state_path):
            try:
                with open(state_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for m in data:
                    if str(m["fixture_id"]) == str(fixture_id):
                        fixture_obj = m.get("fixture", {})
                        home_s = fixture_obj.get("home_score")
                        away_s = fixture_obj.get("away_score")
                        score_str = (
                            f"{home_s} - {away_s}" if home_s is not None else "0 - 0"
                        )

                        winner_str = "DRAW"
                        if home_s is not None and away_s is not None:
                            if home_s > away_s:
                                winner_str = f"{m['match'].split(' vs ')[0]} WIN"
                            elif away_s > home_s:
                                winner_str = f"{m['match'].split(' vs ')[1]} WIN"

                        actuals = {
                            "fixture_id": int(fixture_id),
                            "match": m["match"],
                            "league": m["league"],
                            "status": m["status_code"],
                            "score": score_str,
                            "home_score": home_s or 0,
                            "away_score": away_s or 0,
                            "winner": winner_str,
                            "goals": [],
                            "possession_home": 50,
                            "possession_away": 50,
                            "corners_home": 0,
                            "corners_away": 0,
                            "corners_total": 0,
                            "fouls_home": 0,
                            "fouls_away": 0,
                            "cards_yellow_home": 0,
                            "cards_yellow_away": 0,
                            "cards_yellow_total": 0,
                            "cards_red_total": 0,
                            "shots_home": 0,
                            "shots_away": 0,
                            "shots_on_target_home": 0,
                            "shots_on_target_away": 0,
                            "player_stats": [],
                        }
                        break
            except Exception:
                pass

    return jsonify({"prediction": prediction, "actuals": actuals})


def init_databases():
    db_path = os.path.join(DATA_DIR, "bet_log.db")
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()

        # Ensure bet_log table exists using bet_logger
        try:
            from bet_logger import init_bet_log_db

            init_bet_log_db()
        except Exception as e:
            print("[!] Error calling init_bet_log_db:", e)

        # Ensure stair_orders table exists
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS stair_orders (
                bet_id TEXT PRIMARY KEY,
                order_id TEXT,
                FOREIGN KEY(bet_id) REFERENCES bet_log(bet_id)
            )
        """
        )

        # Backfill existing AI bets in bet_log with dummy order_ids if they don't exist in stair_orders
        cur.execute("SELECT bet_id FROM bet_log WHERE bet_source='AI'")
        ai_bets = [r[0] for r in cur.fetchall()]
        for bet_id in ai_bets:
            cur.execute(
                "INSERT OR IGNORE INTO stair_orders (bet_id, order_id) VALUES (?, ?)",
                (bet_id, f"STAIR_DUMMY_{bet_id[-8:]}"),
            )

        conn.commit()
        conn.close()
        print("[+] Databases verified and initialized successfully.")
    except Exception as e:
        print("[!] Error initializing databases in server:", e)


def start_background_prediction_worker():
    import threading

    if os.getenv("DEEPFIELD_USE_AGENTS") == "1":
        # A2A agent-based orchestrator — replaces the legacy monolithic daemon
        try:
            from src.agents.daemon_orchestrator import DaemonOrchestrator

            orch = DaemonOrchestrator()
            interval = int(os.getenv("DEEPFIELD_AGENT_INTERVAL", "300"))
            thread = threading.Thread(
                target=orch.run_loop, kwargs={"interval": interval}, daemon=True
            )
            thread.start()
            print(f"[*] A2A orchestrator thread started (interval={interval}s).")
        except Exception as e:
            print(f"[!] Failed to start A2A orchestrator thread: {e}")
    else:
        try:
            from live_predictions_daemon import run_daemon

            thread = threading.Thread(target=run_daemon, daemon=True)
            thread.start()
            print("[*] Background prediction worker thread started successfully.")
        except Exception as e:
            print("[!] Failed to start background prediction worker thread:", e)


if __name__ == "__main__":
    init_databases()

    # Warn loudly if the arena autopilot is already armed from a previous session
    try:
        import json as _j

        _ap_state_path = os.path.join(DATA_DIR, "arena_autopilot.json")
        if os.path.exists(_ap_state_path):
            _ap_state = _j.loads(open(_ap_state_path).read())
            if _ap_state.get("enabled") and os.getenv("DEEPFIELD_ARENA_LIVE") == "1":
                print(
                    "[!] WARNING: arena_autopilot.json::enabled=True AND DEEPFIELD_ARENA_LIVE=1"
                )
                print("[!] Arena autopilot will resume LIVE betting immediately.")
                print("[!] Visit /arena and click Pause to halt before it fires.")
            elif _ap_state.get("enabled"):
                print(
                    "[*] Arena autopilot enabled (predict-only; DEEPFIELD_ARENA_LIVE not set)."
                )
    except Exception:
        pass

    if os.getenv("DEEPFIELD_DISABLE_DAEMON") != "1":
        start_background_prediction_worker()
        # Start the autonomous Stair AI arena betting loop (real money, WC-only, pre-kickoff).
        try:
            from arena_betting import start_autopilot

            start_autopilot()
        except Exception as _ap_err:
            print(f"[!] Arena autopilot not started: {_ap_err}")
    else:
        print(
            "[*] Background prediction worker thread is DISABLED (running in multi-process mode)."
        )
    _port = int(os.getenv("DEEPFIELD_PORT", "5050"))
    print(f"[*] Starting DeepFieldPro Live UI on http://127.0.0.1:{_port}")
    # threaded=True is REQUIRED: the prediction daemon runs in a background thread in
    # this same process and its cycles are long (3-min scrapes, model inference). Without
    # a threaded server, Werkzeug handles one request at a time and the dashboard hangs
    # (HTTP timeouts) the entire time the daemon is busy. Threaded serving lets HTTP
    # requests be answered concurrently (the daemon's I/O releases the GIL).
    app.run(host="0.0.0.0", port=_port, debug=False, threaded=True)
