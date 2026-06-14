import os, sqlite3
import pandas as pd

DB = os.path.join(os.path.dirname(__file__), "data", "bet_log.db")
con = sqlite3.connect(DB)
df = pd.read_sql_query("SELECT * FROM bet_log", con)
con.close()

print(f"TOTAL bets logged: {len(df)}")
print("result breakdown:", df["result"].value_counts().to_dict())
print("bet_source:", df["bet_source"].value_counts().to_dict() if "bet_source" in df else "n/a")
print("date range:", df["placed_at"].min(), "->", df["placed_at"].max())

settled = df[df["result"].isin(["W", "L", "WIN", "LOSS", "WON", "LOST"])].copy()
def norm(r): return "W" if str(r).upper().startswith("W") else "L"
settled["res"] = settled["result"].map(norm)
settled["stake"] = pd.to_numeric(settled["stake"], errors="coerce").fillna(0)
settled["pnl"] = pd.to_numeric(settled["pnl"], errors="coerce").fillna(0)
settled["entry_odds"] = pd.to_numeric(settled["entry_odds"], errors="coerce")

n = len(settled); wins = (settled["res"] == "W").sum()
stake = settled["stake"].sum(); pnl = settled["pnl"].sum()
print("\n=== REALIZED PAPER PERFORMANCE (settled bets) ===")
print(f"settled: {n} | wins: {wins} | losses: {n-wins} | hit-rate: {wins/n:.1%}" if n else "no settled bets")
print(f"total staked: ${stake:,.2f} | total P&L: ${pnl:,.2f} | ROI: {(pnl/stake*100) if stake else 0:.2f}%")
print(f"avg odds: {settled['entry_odds'].mean():.2f} | avg stake: ${settled['stake'].mean():.2f}")

# implied vs realized win rate (is it beating its own implied prob?)
imp = (1/settled["entry_odds"]).mean()
print(f"avg implied win prob (1/odds): {imp:.1%} vs realized hit-rate {wins/n:.1%}")

print("\n=== by market ===")
for mk, g in settled.groupby("market_type"):
    s = g["stake"].sum(); p = g["pnl"].sum(); w = (g["res"]=="W").sum()
    print(f"  {mk:14s} n={len(g):4d} hit={w/len(g):5.1%} staked=${s:8.2f} pnl=${p:8.2f} roi={(p/s*100) if s else 0:7.2f}%")

print("\n=== daily P&L ===")
settled["day"] = settled["placed_at"].astype(str).str[:10]
for d, g in settled.groupby("day"):
    print(f"  {d}: n={len(g):4d} pnl=${g['pnl'].sum():8.2f} roi={(g['pnl'].sum()/g['stake'].sum()*100) if g['stake'].sum() else 0:7.2f}%")
