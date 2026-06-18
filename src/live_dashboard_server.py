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

    try:
        from src.a2ui_builder import build_dashboard_ui

        _bk = 0.0
        try:
            import sqlite3 as _sq2

            _bkdb = os.path.join(DATA_DIR, "bankroll.db")
            _bkc = _sq2.connect(_bkdb)
            _bkr = _bkc.execute(
                "SELECT current_balance FROM bankroll ORDER BY date DESC LIMIT 1"
            ).fetchone()
            _bkc.close()
            if _bkr:
                _bk = float(_bkr[0])
        except Exception:
            pass
        return jsonify(
            {
                "data": state,
                "ui": build_dashboard_ui(state or [], {}, _bk),
                "ui_available": True,
            }
        )
    except Exception as _ui_err:
        return jsonify({"data": state, "ui": None, "ui_available": False})


@app.route("/api/stream")
def stream_state():
    def event_stream():
        state_path = os.path.join(
            os.path.dirname(__file__), "..", "data", "todays_dashboard_state.json"
        )
        last_mtime = 0
        while True:
            try:
                if os.path.exists(state_path):
                    mtime = os.path.getmtime(state_path)
                    if mtime > last_mtime:
                        last_mtime = mtime
                        with open(state_path, "r", encoding="utf-8") as f:
                            state = json.load(f)
                        try:
                            from src.a2ui_builder import build_dashboard_ui as _bdu

                            _pl = {
                                "data": state,
                                "ui": _bdu(state or [], {}, 0.0),
                                "ui_available": True,
                            }
                        except Exception:
                            _pl = {"data": state, "ui": None, "ui_available": False}
                        yield f"data: {json.dumps(_pl)}\n\n"
            except Exception:
                pass
            time.sleep(2)  # Check file every 2 seconds

    return Response(event_stream(), mimetype="text/event-stream")


INITIAL_CAPITAL = 300.0  # paper bankroll seed


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
        "SELECT match_id, player_id, market_type, entry_odds, stake, result, pnl, placed_at, bet_source FROM bet_log ORDER BY placed_at DESC",
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
               b.bet_source, b.is_recommended, p.kickoff
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
        data = request.json
        bet_id = "UI_" + datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        match = data.get("match", "Unknown")
        market = data.get("market", "1X2")
        selection = data.get("selection", "Home")
        stake = float(data.get("stake", 10.0))
        prob = float(data.get("prob", 50.0))
        entry_odds = float(
            data.get("odds", round(100.0 / prob, 2) if prob > 0 else 1.0)
        )
        is_recommended = int(data.get("recommended", 0))

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
        from bankroll_tracker import register_bet

        register_bet(stake)

        return jsonify({"status": "success", "bet_id": bet_id})
    except Exception as e:
        print("Bet Error:", e)
        return jsonify({"error": str(e)}), 500


@app.route("/api/settings", methods=["GET", "POST"])
def manage_settings():
    if request.method == "POST":
        with open(SETTINGS_FILE, "w") as f:
            json.dump(request.json, f, indent=4)
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
