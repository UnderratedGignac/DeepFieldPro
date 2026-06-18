"""
referee_report.py — Print referee booking-rate league table and home bias.

Run:  .venv\\Scripts\\python.exe tools\\referee_report.py

Requires: history.db with referee + HY/AY/HR/AR columns
          (run tools/ingest_history.py if the columns are missing)
"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.referee_data import top_card_referees, bottom_card_referees, _load_ref_stats, _LEAGUE_MEAN_BOOKING_RATE

stats = _load_ref_stats()
print(f"\nReferee database: {len(stats)} referees loaded")
print(f"League mean booking rate: {_LEAGUE_MEAN_BOOKING_RATE:.2f} (yellow + 2×red per match)\n")

if not stats:
    print("No referee data found. Run 'ingest_history.py' first to add referee/card columns.")
    sys.exit(0)

print("=" * 65)
print("TOP 15 HIGH-CARD REFEREES (avoid for Under / low-card markets)")
print("=" * 65)
print(f"{'Referee':<30} {'Rate':>6} {'Bias':>7} {'n':>5}")
print("-" * 65)
for ref, v in top_card_referees(15):
    bias_str = f"{v['home_bias']:+.2f}"
    flag = " HIGH" if v['booking_rate'] > _LEAGUE_MEAN_BOOKING_RATE * 1.25 else ""
    print(f"{ref:<30} {v['booking_rate']:>6.2f} {bias_str:>7} {v['n']:>5}{flag}")

print()
print("=" * 65)
print("TOP 15 LOW-CARD REFEREES (favour for Under / BTTS No)")
print("=" * 65)
print(f"{'Referee':<30} {'Rate':>6} {'Bias':>7} {'n':>5}")
print("-" * 65)
for ref, v in bottom_card_referees(15):
    bias_str = f"{v['home_bias']:+.2f}"
    flag = " LOW" if v['booking_rate'] < _LEAGUE_MEAN_BOOKING_RATE * 0.75 else ""
    print(f"{ref:<30} {v['booking_rate']:>6.2f} {bias_str:>7} {v['n']:>5}{flag}")

print()
print("Bias > 0: ref gives more cards to away team (home-favouring)")
print("Bias < 0: ref gives more cards to home team (away-favouring)")
