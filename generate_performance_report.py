import sqlite3
import pandas as pd
import datetime
import os

DB_PATH = 'data/bet_log.db'
REPORT_DIR = 'reports'

def generate_performance_report():
    os.makedirs(REPORT_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    
    # 1. Weekly Stats
    one_week_ago = (datetime.datetime.now() - datetime.timedelta(days=7)).isoformat()
    
    # ROI by Market
    query_roi = f"SELECT market_type, SUM(stake) as total_stake, SUM(pnl) as total_pnl, COUNT(*) as count FROM bet_log WHERE placed_at > '{one_week_ago}' GROUP BY market_type"
    roi_df = pd.read_sql_query(query_roi, conn)
    if not roi_df.empty:
        roi_df['roi'] = (roi_df['total_pnl'] / roi_df['total_stake']) * 100

    # CLV Stats
    query_clv = f"SELECT market_type, AVG(clv) as avg_clv, SUM(CASE WHEN clv > 0 THEN 1 ELSE 0 END) * 100.0 / COUNT(*) as beat_clv_pct FROM bet_log WHERE placed_at > '{one_week_ago}' AND clv IS NOT NULL GROUP BY market_type"
    clv_df = pd.read_sql_query(query_clv, conn)
    
    conn.close()
    
    # Save Report
    report_path = os.path.join(REPORT_DIR, f"weekly_report_{datetime.datetime.now().strftime('%Y%m%d')}.md")
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(f"# DeepFieldPro Performance Report — {datetime.datetime.now().strftime('%Y-%m-%d')}\n\n")
        f.write("## ROI by Market (Last 7 Days)\n\n")
        f.write(roi_df.to_markdown(index=False) if not roi_df.empty else "No bets in last 7 days.")
        f.write("\n\n## CLV Performance (Last 7 Days)\n\n")
        f.write(clv_df.to_markdown(index=False) if not clv_df.empty else "No CLV data available.")
        
    print(f"Report generated: {report_path}")

if __name__ == "__main__":
    generate_performance_report()
