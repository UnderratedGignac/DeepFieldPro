"""
Deep audit: checks every module claimed in the README actually exists and imports cleanly.
"""
import os, sys, importlib, importlib.util

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

# Map: (label, file_path_relative_to_src)
MODULES_TO_CHECK = [
    # Acquisition
    ("Browser Engine",           "services/session_manager/browser_engine.py"),
    ("Session Manager",          "services/session_manager/service.py"),
    ("WebSocket Ingestor",       "services/odds_acquisition/websocket_ingestor.py"),
    ("Odds Collector",           "services/odds_acquisition/collector.py"),
    ("Odds Normalizer",          "services/normalizer/engine.py"),
    # Database
    ("DB Models",                "database/models.py"),
    # Research OS
    ("Research Walk-Forward",    "research/real_world_validation/statistical_significance_tester.py"),
    ("Reality Alignment",        "research/real_world_validation/reality_alignment_check.py"),
    ("Execution Friction",       "research/real_world_validation/execution_friction_analyzer.py"),
    ("Combinatorial CV",         "research/validation_framework/combinatorial_purged_cv.py"),
    ("Meta Governor",            "research/meta_governor/mgl_engine.py"),
    ("Policy Auditor",           "research/policy_outcome_auditor/autonomous_policy_optimizer.py"),
    # Risk
    ("Risk Engine",              "services/risk_engine/engine.py"),
    ("CLV Engine",               "services/clv/engine.py"),
    ("Shadow Execution",         "services/shadow_execution/engine.py"),
    ("Backtesting Replay",       "services/backtesting/historical_replay.py"),
    # Portfolio
    ("Capital Allocation",       "portfolio_optimization/capital_allocation_engine.py"),
    ("Drawdown Governor",        "portfolio_optimization/drawdown_governor.py"),
    ("Bayesian Confidence",      "portfolio_optimization/bayesian_confidence_engine.py"),
    ("Correlation Engine",       "portfolio_optimization/portfolio_correlation_engine.py"),
    # Telemetry
    ("Telemetry Archiver",       "telemetry_warehouse/telemetry_archiver.py"),
    ("Sportsbook Fingerprinter", "telemetry_warehouse/sportsbook_behavior_fingerprinter.py"),
    ("Adversarial Miner",        "telemetry_warehouse/adversarial_pattern_miner.py"),
    # Core pipeline
    ("Orchestrator",             "orchestrator.py"),
    ("Single Bet Predictor",     "single_bet_predictor.py"),
    ("Parlay Builder",           "parlay_builder.py"),
    ("Model Runner V2",          "model_runner_v2.py"),
    ("Pricing Engine",           "pricing_engine.py"),
    ("Kelly Calculator",         "kelly_calculator.py"),
    ("Betarabia Scraper",        "betarabia_scraper.py"),
    ("Lineup Monitor",           "lineup_monitor.py"),
    ("Scheduler Daemon",         "scheduler_daemon.py"),
    # README mentions these - check if they exist at all
    ("Live Ops - Shadow Orch",   "live_operations/shadow_deployment_orchestrator.py"),
    ("Live Ops - Edge Decay",    "live_operations/edge_decay_live.py"),
    ("Live Ops - Account Health","live_operations/account_health_engine.py"),
    ("Live Ops - CLV Tracker",   "live_operations/live_clv_tracker.py"),
    ("Live Ops - Alerting",      "live_operations/alerting_system.py"),
    ("Research OS - Experiment", "research_os/experiment_registry.py"),
    ("Research OS - Lifecycle",  "research_os/strategy_lifecycle.py"),
    ("Research OS - Graveyard",  "research_os/strategy_graveyard.py"),
]

print("=" * 70)
print("DEEPFIELDPRO MODULE AUDIT")
print("=" * 70)

present = []
missing = []
import_ok = []
import_err = []

for label, rel_path in MODULES_TO_CHECK:
    full = os.path.join(BASE, "src", rel_path.replace("/", os.sep))
    exists = os.path.exists(full)
    
    if exists:
        present.append((label, rel_path))
        # Try import
        try:
            spec = importlib.util.spec_from_file_location(label, full)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            import_ok.append(label)
            print(f"  OK    {label}")
        except Exception as e:
            short_err = str(e)[:80]
            import_err.append((label, short_err))
            print(f"  WARN  {label}: {short_err}")
    else:
        missing.append((label, rel_path))
        print(f"  MISS  {label}  ({rel_path})")

print()
print("=" * 70)
print(f"SUMMARY: {len(present)}/{len(MODULES_TO_CHECK)} files present")
print(f"         {len(import_ok)}/{len(present)} import cleanly")
print(f"         {len(missing)} files MISSING from README claims")
print("=" * 70)

if missing:
    print("\nMISSING FILES:")
    for lbl, path in missing:
        print(f"  - {lbl}: src/{path}")

if import_err:
    print("\nIMPORT ERRORS:")
    for lbl, err in import_err:
        print(f"  - {lbl}: {err}")
