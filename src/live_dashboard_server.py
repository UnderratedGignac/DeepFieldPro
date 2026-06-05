from flask import Flask, render_template, jsonify, request
import json
import os
import sqlite3
import datetime

app = Flask(__name__)
app.config['TEMPLATES_AUTO_RELOAD'] = True

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')
SETTINGS_FILE = os.path.join(DATA_DIR, 'settings.json')

# Create default settings if not exists
if not os.path.exists(SETTINGS_FILE):
    with open(SETTINGS_FILE, 'w') as f:
        json.dump({
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
            "preferred_bookie": "Pinnacle"
        }, f)

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

@app.route('/')
@app.route('/bankroll')
@app.route('/tracker')
@app.route('/performance')
@app.route('/settings')
def index():
    return render_template('index.html')

@app.route('/api/state')
def get_state():
    state_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'todays_dashboard_state.json')
    try:
        if os.path.exists(state_path):
            with open(state_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return jsonify(data)
        else:
            return jsonify([]) # Return empty if no state file
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/bankroll')
def get_bankroll():
    try:
        from bankroll_tracker import init_bankroll_db
        init_bankroll_db()
    except Exception as e:
        print("Bankroll init error in server:", e)

    row = query_db('bankroll.db', "SELECT current_balance, starting_balance, daily_pnl FROM bankroll ORDER BY date DESC LIMIT 1", one=True)
    history = query_db('bankroll.db', "SELECT date, current_balance FROM bankroll ORDER BY date ASC")
    
    chart_dates = []
    chart_balances = []
    if history:
        for h in history:
            chart_dates.append(h['date'])
            chart_balances.append(h['current_balance'])
            
    if row:
        roi = ((row['current_balance'] - row['starting_balance']) / row['starting_balance']) * 100 if row['starting_balance'] else 0
        return jsonify({
            "current": round(row['current_balance'], 2),
            "roi": round(roi, 2),
            "pnl": round(row['daily_pnl'] or 0.0, 2),
            "chart_dates": chart_dates,
            "chart_balances": chart_balances
        })
    return jsonify({
        "current": 10000.0, 
        "roi": 0.0, 
        "pnl": 0.0,
        "chart_dates": [],
        "chart_balances": []
    })

@app.route('/api/tracker')
def get_tracker():
    rows = query_db('bet_log.db', "SELECT bet_id, match_id, player_id, market_type, entry_odds, closing_odds, edge_pct, stake, result, pnl, placed_at, bet_source, is_recommended FROM bet_log ORDER BY placed_at DESC LIMIT 50")
    
    stats = {"W": 0, "L": 0, "OPEN": 0}
    # Count from database for user placed bets
    db_stats = query_db('bet_log.db', "SELECT result, COUNT(*) as cnt FROM bet_log WHERE bet_source='USER' GROUP BY result")
    if db_stats:
        for r in db_stats:
            res = r['result']
            if res in stats:
                stats[res] = r['cnt']
                
    return jsonify({
        "bets": [dict(r) for r in (rows or [])],
        "stats": stats
    })

@app.route('/api/performance')
def get_performance():
    # Query AI bets with all fields
    ai_bets = query_db('bet_log.db', "SELECT bet_id, match_id, player_id, market_type, entry_odds, stake, result, pnl, placed_at FROM bet_log WHERE bet_source='AI' ORDER BY placed_at DESC")
    # Query User bets with all fields
    user_bets = query_db('bet_log.db', "SELECT bet_id, match_id, player_id, market_type, entry_odds, stake, result, pnl, placed_at, is_recommended FROM bet_log WHERE bet_source='USER' ORDER BY placed_at DESC")
    
    def summarize(bets):
        total = len(bets)
        wins = sum(1 for b in bets if b['result'] == 'W')
        losses = sum(1 for b in bets if b['result'] == 'L')
        open_count = sum(1 for b in bets if b['result'] == 'OPEN')
        
        total_stake = sum(b['stake'] or 0.0 for b in bets)
        total_pnl = sum(b['pnl'] or 0.0 for b in bets)
        
        win_rate = round((wins / (wins + losses)) * 100, 1) if (wins + losses) > 0 else 0.0
        return {
            "total": total,
            "wins": wins,
            "losses": losses,
            "open": open_count,
            "win_rate": win_rate,
            "stake": round(total_stake, 2),
            "pnl": round(total_pnl, 2)
        }
        
    ai_summary = summarize(ai_bets or [])
    user_summary = summarize(user_bets or [])
    
    user_rec_bets = [b for b in (user_bets or []) if b['is_recommended'] == 1]
    user_own_bets = [b for b in (user_bets or []) if b['is_recommended'] == 0]
    
    user_rec_summary = summarize(user_rec_bets)
    user_own_summary = summarize(user_own_bets)
    
    return jsonify({
        "ai": ai_summary,
        "user": user_summary,
        "user_rec": user_rec_summary,
        "user_own": user_own_summary,
        "raw_user_bets": [dict(r) for r in (user_bets or [])],
        "raw_ai_bets": [dict(r) for r in (ai_bets or [])]
    })

@app.route('/api/settle_bet', methods=['POST'])
def settle_bet():
    try:
        data = request.json
        bet_id = data.get('bet_id')
        outcome = data.get('outcome')  # 'W', 'L', 'VOID', or 'OPEN'
        
        if not bet_id or outcome not in ['W', 'L', 'VOID', 'OPEN']:
            return jsonify({"error": "Invalid bet_id or outcome"}), 400
            
        db_path = os.path.join(DATA_DIR, 'bet_log.db')
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        
        # Get bet info
        cur.execute("SELECT bet_id, entry_odds, stake, bet_source, result FROM bet_log WHERE bet_id = ?", (bet_id,))
        bet = cur.fetchone()
        
        if not bet:
            conn.close()
            return jsonify({"error": "Bet not found"}), 404
            
        old_result = bet['result']
        entry_odds = bet['entry_odds']
        stake = bet['stake']
        bet_source = bet['bet_source']
        
        # Revert old bankroll effect if it was previously settled and is USER
        br_path = os.path.join(DATA_DIR, 'bankroll.db')
        if bet_source == 'USER' and old_result != 'OPEN':
            conn_br = sqlite3.connect(br_path)
            cur_br = conn_br.cursor()
            if old_result == 'W':
                old_pnl = stake * (entry_odds - 1)
                old_payout = stake * entry_odds
                cur_br.execute("UPDATE bankroll SET current_balance = current_balance - ?, daily_pnl = daily_pnl - ? WHERE id = (SELECT MAX(id) FROM bankroll)", (old_payout, old_pnl))
            elif old_result == 'L':
                old_pnl = -stake
                cur_br.execute("UPDATE bankroll SET daily_pnl = daily_pnl - ? WHERE id = (SELECT MAX(id) FROM bankroll)", (old_pnl,))
            elif old_result == 'VOID':
                cur_br.execute("UPDATE bankroll SET current_balance = current_balance - ? WHERE id = (SELECT MAX(id) FROM bankroll)", (stake,))
            conn_br.commit()
            conn_br.close()
            
        # Compute new PNL
        if outcome == 'W':
            pnl = stake * (entry_odds - 1)
        elif outcome == 'L':
            pnl = -stake
        elif outcome == 'VOID':
            pnl = 0.0
        else: # OPEN
            pnl = 0.0
            
        # Update bet_log
        cur.execute("UPDATE bet_log SET result = ?, pnl = ? WHERE bet_id = ?", (outcome, pnl, bet_id))
        conn.commit()
        conn.close()
        
        # Apply new bankroll effect if USER
        if bet_source == 'USER' and outcome != 'OPEN':
            conn_br = sqlite3.connect(br_path)
            cur_br = conn_br.cursor()
            if outcome == 'W':
                payout = stake * entry_odds
                cur_br.execute("UPDATE bankroll SET current_balance = current_balance + ?, daily_pnl = daily_pnl + ? WHERE id = (SELECT MAX(id) FROM bankroll)", (payout, pnl))
            elif outcome == 'L':
                cur_br.execute("UPDATE bankroll SET daily_pnl = daily_pnl + ? WHERE id = (SELECT MAX(id) FROM bankroll)", (pnl,))
            elif outcome == 'VOID':
                cur_br.execute("UPDATE bankroll SET current_balance = current_balance + ? WHERE id = (SELECT MAX(id) FROM bankroll)", (stake,))
            conn_br.commit()
            conn_br.close()
            
        return jsonify({"status": "success", "bet_id": bet_id, "outcome": outcome, "pnl": round(pnl, 2)})
    except Exception as e:
        print("Settle Bet Error:", e)
        return jsonify({"error": str(e)}), 500


@app.route('/api/place_bet', methods=['POST'])
def place_bet():
    try:
        data = request.json
        bet_id = "UI_" + datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        match = data.get('match', 'Unknown')
        market = data.get('market', '1X2')
        selection = data.get('selection', 'Home')
        stake = float(data.get('stake', 10.0))
        prob = float(data.get('prob', 50.0))
        entry_odds = float(data.get('odds', round(100.0 / prob, 2) if prob > 0 else 1.0))
        is_recommended = int(data.get('recommended', 0))
        
        closing_odds = round(entry_odds - 0.05, 2)
        edge = round((prob / 100.0) * entry_odds - 1.0, 3) * 100
        
        db_path = os.path.join(DATA_DIR, 'bet_log.db')
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO bet_log 
            (bet_id, match_id, player_id, market_type, entry_odds, closing_odds, edge_pct, stake, result, pnl, placed_at, bet_source, is_recommended, line, side)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (bet_id, match, f"{match} ({selection})", market, entry_odds, closing_odds, edge, stake, "OPEN", 0.0, datetime.datetime.now().isoformat(), "USER", is_recommended, 2.5, selection))
        
        conn.commit()
        conn.close()
        
        # Deduct stake from bankroll
        br_path = os.path.join(DATA_DIR, 'bankroll.db')
        conn2 = sqlite3.connect(br_path)
        cur2 = conn2.cursor()
        cur2.execute("UPDATE bankroll SET current_balance = current_balance - ? WHERE id = (SELECT MAX(id) FROM bankroll)", (stake,))
        conn2.commit()
        conn2.close()
        
        return jsonify({"status": "success", "bet_id": bet_id})
    except Exception as e:
        print("Bet Error:", e)
        return jsonify({"error": str(e)}), 500

@app.route('/api/settings', methods=['GET', 'POST'])
def manage_settings():
    if request.method == 'POST':
        with open(SETTINGS_FILE, 'w') as f:
            json.dump(request.json, f, indent=4)
        return jsonify({"status": "success"})
    
    with open(SETTINGS_FILE, 'r') as f:
        return jsonify(json.load(f))

@app.route('/api/trigger_recalibration', methods=['POST'])
def trigger_recalibration():
    print("[DAEMON] Initiating Platt Scaler Recalibration from UI...")
    return jsonify({"status": "Recalibration Started"})

if __name__ == '__main__':
    print("[*] Starting DeepFieldPro Live UI on http://127.0.0.1:5000")
    app.run(host='127.0.0.1', port=5000, debug=False)
