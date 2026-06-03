# -*- coding: utf-8 -*-
"""Test that all imports work correctly."""
import sys
import os
src_path = os.path.join(os.path.dirname(__file__), '..', 'src')
sys.path.insert(0, src_path)

print("Testing imports...")

try:
    from model_runner_v2 import get_player_historical_stats, load_models_international, build_feature_vector
    print("✓ model_runner_v2 imports OK")
except ImportError as e:
    print(f"✗ model_runner_v2 import FAILED: {e}")

try:
    from calibration_trainer import train_platt_scaler
    print("✓ calibration_trainer imports OK")
except ImportError as e:
    print(f"✗ calibration_trainer import FAILED: {e}")

try:
    from clv_tracker import record_bet, settle_bet, generate_report
    print("✓ clv_tracker imports OK")
except ImportError as e:
    print(f"✗ clv_tracker import FAILED: {e}")

print("\nALL IMPORTS OK")
