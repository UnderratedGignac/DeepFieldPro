import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from src.agents.daemon_orchestrator import DaemonOrchestrator
if __name__ == "__main__":
    print("DeepFieldPro A2A System — one cycle demo")
    orch = DaemonOrchestrator()
    agents = [orch.fixture_scout, orch.steam_detector, orch.predictor,
              orch.bet_gatekeeper, orch.settler, orch.arena_monitor]
    for ag in agents:
        print(f"  {ag.agent_card['name']} v{ag.agent_card['version']} — {', '.join(ag.capabilities())}")
    print("\nRunning cycle...")
    result = orch.run_cycle()
    print(json.dumps(result, indent=2, default=str))
