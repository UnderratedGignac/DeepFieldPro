import os
import sqlite3
import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timezone

st.set_page_config(page_title="Deep Field Pro Dashboard", layout="wide")

DB_BANKROLL = os.path.join(os.path.dirname(__file__), '..', 'data', 'bankroll.db')
DB_BETLOG = os.path.join(os.path.dirname(__file__), '..', 'data', 'bet_log.db')
DB_ACCOUNTS = os.path.join(os.path.dirname(__file__), '..', 'data', 'book_accounts.db')

def get_db_connection(db_path):
    if not os.path.exists(db_path):
        return None
    return sqlite3.connect(db_path)

st.title("📈 Deep Field Pro v2.0 - Live Dashboard")

# --- Section 1: System Status & Bankroll ---
st.header("Bankroll & System Status")
conn_bankroll = get_db_connection(DB_BANKROLL)
if conn_bankroll:
    today = datetime.now(timezone.utc).date().isoformat()
    df_bankroll = pd.read_sql_query("SELECT * FROM bankroll WHERE date = ?", conn_bankroll, params=(today,))
    
    if not df_bankroll.empty:
        status = df_bankroll['system_status'].iloc[0]
        current_balance = df_bankroll['current_balance'].iloc[0]
        daily_pnl = df_bankroll['daily_pnl'].iloc[0]
        exposure = df_bankroll['daily_exposure'].iloc[0]
        
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("System Status", status, delta_color="off" if status == "ACTIVE" else "inverse")
        col2.metric("Current Balance", f"${current_balance:,.2f}", f"${daily_pnl:,.2f} today")
        col3.metric("Daily Exposure", f"${exposure:,.2f}")
        col4.metric("Peak Balance", f"${df_bankroll['peak_balance'].iloc[0]:,.2f}")
    else:
        st.warning("No bankroll data for today.")
    
    # Historical Bankroll Chart
    df_all_bankroll = pd.read_sql_query("SELECT date, current_balance FROM bankroll ORDER BY date", conn_bankroll)
    if not df_all_bankroll.empty:
        fig = px.line(df_all_bankroll, x='date', y='current_balance', title="Bankroll Growth Over Time")
        st.plotly_chart(fig, use_container_width=True)
    
    conn_bankroll.close()
else:
    st.error("Bankroll database not found.")

st.divider()

# --- Section 2: CLV & Edge Tracking ---
st.header("CLV & Edge Tracking")
conn_betlog = get_db_connection(DB_BETLOG)
if conn_betlog:
    df_betlog = pd.read_sql_query("SELECT * FROM bet_log ORDER BY placed_at DESC", conn_betlog)
    
    if not df_betlog.empty:
        # Metrics
        total_bets = len(df_betlog)
        avg_clv = df_betlog['clv'].mean() * 100 if 'clv' in df_betlog and not df_betlog['clv'].isnull().all() else 0.0
        
        col1, col2 = st.columns(2)
        col1.metric("Total Bets Logged", total_bets)
        col2.metric("Average CLV Capture", f"{avg_clv:.2f}%")
        
        # Display recent bets
        st.subheader("Recent Bets")
        st.dataframe(df_betlog[['placed_at', 'match_id', 'market_type', 'side', 'entry_odds', 'stake', 'book', 'clv', 'result']].head(10))
    else:
        st.info("No bets logged yet.")
    conn_betlog.close()
else:
    st.error("Bet log database not found.")

st.divider()

# --- Section 3: Account Health ---
st.header("Bookmaker Account Health")
conn_accounts = get_db_connection(DB_ACCOUNTS)
if conn_accounts:
    df_accounts = pd.read_sql_query("SELECT * FROM book_accounts ORDER BY tier ASC", conn_accounts)
    if not df_accounts.empty:
        st.dataframe(df_accounts[['book_name', 'tier', 'status', 'current_balance', 'max_stake', 'total_pnl']])
    else:
        st.info("No account data found.")
    conn_accounts.close()
else:
    st.error("Accounts database not found.")
