import os
import sqlite3
import pandas as pd
import streamlit as st
import plotly.express as px
from datetime import datetime, timezone
from src.dfp_config import settings

st.set_page_config(page_title="Deep Field Pro Dashboard", layout="wide")

# Source of truth: Consolidated deepfield.db
DB_DEEPFIELD = settings.DATABASE_URL.replace("sqlite:///", "")


def get_db_connection():
    if not os.path.exists(DB_DEEPFIELD):
        return None
    return sqlite3.connect(DB_DEEPFIELD)


st.title("📈 Deep Field Pro v2.0 - Performance Dashboard")

# --- GLOBAL TOGGLE: SHADOW VS LIVE ---
st.sidebar.header("Dashboard Settings")
view_mode = st.sidebar.radio(
    "Select View Mode",
    ["Shadow Data", "Live Data"],
    index=0 if settings.SHADOW_MODE else 1,
)
status_filter = "SHADOW" if view_mode == "Shadow Data" else "settled"

# --- Section 1: Bankroll Overview ---
st.header(f"Bankroll & {view_mode}")
conn = get_db_connection()

if conn:
    # Get Bets based on mode
    query = f"SELECT * FROM bets WHERE status = '{status_filter}' OR status = 'pending' ORDER BY placed_at DESC"
    if view_mode == "Live Data":
        # For live, we show settled + pending (excluding shadow)
        query = "SELECT * FROM bets WHERE status != 'SHADOW' ORDER BY placed_at DESC"

    df_bets = pd.read_sql_query(query, conn)

    if not df_bets.empty:
        total_pnl = df_bets["result"].sum() if "result" in df_bets else 0.0
        total_staked = df_bets["stake"].sum()
        roi = (total_pnl / total_staked) * 100 if total_staked > 0 else 0.0
        win_rate = (
            (
                len(df_bets[df_bets["status"] == "won"])
                / len(df_bets[df_bets["status"] != "pending"])
            )
            * 100
            if len(df_bets[df_bets["status"] != "pending"]) > 0
            else 0.0
        )

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total P&L", f"${total_pnl:,.2f}")
        col2.metric("Total Staked", f"${total_staked:,.2f}")
        col3.metric("ROI", f"{roi:.2f}%")
        col4.metric("Win Rate", f"{win_rate:.1f}%")

        # Performance Chart
        df_bets["placed_at"] = pd.to_datetime(df_bets["placed_at"])
        df_daily = (
            df_bets.set_index("placed_at")
            .resample("D")["result"]
            .sum()
            .cumsum()
            .reset_index()
        )
        fig = px.line(
            df_daily, x="placed_at", y="result", title=f"Cumulative {view_mode} Profit"
        )
        st.plotly_chart(fig, use_container_width=True)

        # Recent Bets Table
        st.subheader(f"Recent {view_mode} History")
        st.dataframe(
            df_bets[
                [
                    "placed_at",
                    "market_type",
                    "selection",
                    "odds",
                    "stake",
                    "status",
                    "result",
                ]
            ].head(20)
        )
    else:
        st.info(f"No {view_mode} recorded yet.")
    conn.close()
else:
    st.error("DeepField database not found. Please run migrations.")
