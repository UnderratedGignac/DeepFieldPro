"""
role_shift_detector.py
----------------------
Detects when a player's role in today's lineup differs from their historical baseline.

IMPORTANT — Multiplier Calibration Policy:
  The ROLE_SHIFT_MULTIPLIERS dict contains PLACEHOLDER values for initial testing.
  These must be replaced with empirically measured values from your historical data
  once you have >= 10 match samples per shift type.

  Until calibrated, uncalibrated shift types will be FLAGGED but NOT applied.
  Applying uncalibrated multipliers is worse than doing nothing.

  To calibrate: run this SQL against your historical data:
    SELECT old_role || '->' || new_role as shift_type,
           AVG(actual_passes / expected_passes_baseline) as empirical_multiplier,
           COUNT(*) as sample_size
    FROM historical_shift_outcomes
    GROUP BY shift_type
    HAVING COUNT(*) >= 10
"""

import os
import sqlite3
from alerter import alert_role_shift_detected

DB_PATH_HISTORY = os.path.join(
    os.path.dirname(__file__), "..", "data", "player_role_history.db"
)

# ─────────────────────────────────────────────────────────
# CALIBRATION STATUS:
#   True  = empirically validated (safe to apply)
#   False = placeholder guess (flag only, do NOT apply to model)
# ─────────────────────────────────────────────────────────
ROLE_SHIFT_MULTIPLIERS = {
    # shift_key                   : (multiplier, is_calibrated)
    "fullback->wingback": (1.35, False),  # More passes expected — UNCALIBRATED
    "wingback->winger": (0.85, False),  # Fewer passes — UNCALIBRATED
    "fullback->center_back": (1.20, False),  # UNCALIBRATED
    "center_back->fullback": (0.85, False),  # UNCALIBRATED
    "winger->central_mid": (1.55, False),  # Big alpha source — UNCALIBRATED
    "winger->midfield": (1.40, False),  # UNCALIBRATED
    "midfield->defensive_mid": (
        1.20,
        False,
    ),  # Deeper = more recycling passes — UNCALIBRATED
    "midfield->attacking_mid": (0.80, False),  # Higher = fewer passes — UNCALIBRATED
    "striker->winger": (1.40, False),  # UNCALIBRATED
    "central_mid->attacking_mid": (0.80, False),  # UNCALIBRATED
    "defensive_mid->central_mid": (0.95, False),  # UNCALIBRATED
}


def detect_shifts(current_lineup):
    """
    Detect role changes for a given match's lineup.

    current_lineup: list of dicts, each containing:
      {'player_id': str, 'name': str, 'expected_role': str}

    Returns: list of shift dicts:
      {
        'player_id': str,
        'player_name': str,
        'old_role': str,
        'new_role': str,
        'multiplier': float or None,
        'is_calibrated': bool,
        'apply_to_model': bool   ← only True if calibrated
      }
    """
    if not os.path.exists(DB_PATH_HISTORY):
        print(
            "WARNING: Role history DB missing. Cannot detect shifts. "
            "Run role_baseline_builder.py first."
        )
        return []

    conn = sqlite3.connect(DB_PATH_HISTORY)
    cursor = conn.cursor()
    shifts_detected = []

    for player in current_lineup:
        pid = str(player["player_id"])
        new_role = player.get("expected_role", "unknown")
        name = player.get("name", "Unknown")

        if new_role == "unknown":
            continue  # Can't detect a shift if we don't know the new role

        cursor.execute(
            "SELECT usual_role FROM role_baseline WHERE player_id = ?", (pid,)
        )
        row = cursor.fetchone()

        if not row:
            continue  # New player — no baseline yet

        usual_role = row[0]

        if usual_role == "unknown" or usual_role == new_role:
            continue  # No shift detected

        shift_key = f"{usual_role}->{new_role}"
        shift_config = ROLE_SHIFT_MULTIPLIERS.get(shift_key)

        if shift_config:
            multiplier, is_calibrated = shift_config
        else:
            multiplier, is_calibrated = None, False

        apply_to_model = is_calibrated  # Only apply if we trust the data

        shift = {
            "player_id": pid,
            "player_name": name,
            "old_role": usual_role,
            "new_role": new_role,
            "multiplier": multiplier,
            "is_calibrated": is_calibrated,
            "apply_to_model": apply_to_model,
        }
        shifts_detected.append(shift)

        # Always alert for visibility regardless of calibration
        alert_role_shift_detected(name, usual_role, new_role)

        if apply_to_model:
            print(
                f"✅ CALIBRATED shift: {name} | {shift_key} | Multiplier: {multiplier:.2f}"
            )
        else:
            print(
                f"⚠️  UNCALIBRATED shift: {name} | {shift_key} | "
                f"Flagged only — NOT applied to model until calibrated."
            )

    conn.close()
    return shifts_detected


if __name__ == "__main__":
    # Test with mock data (requires role_baseline_builder to have been run first)
    mock_lineup = [
        {"player_id": "883", "name": "Kyle Walker", "expected_role": "wingback"},
        {"player_id": "284", "name": "Rodri", "expected_role": "defensive_mid"},
        {
            "player_id": "622",
            "name": "Kevin De Bruyne",
            "expected_role": "attacking_mid",
        },
    ]
    shifts = detect_shifts(mock_lineup)
    print(f"\nTotal shifts detected: {len(shifts)}")
    for s in shifts:
        print(s)
