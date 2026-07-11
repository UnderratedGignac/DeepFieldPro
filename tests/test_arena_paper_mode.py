"""Arena PAPER mode (2026-07-10): enabled=True while DEEPFIELD_ARENA_LIVE=0
runs the full gate/sizing pipeline but records shadow bets — no order POSTs.

Also covers tools/arena_paper_report.py grading.
"""
import importlib.util
import json
import os
import sys
import time
import types

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

os.environ.setdefault("DEEPFIELD_ARENA_LIVE", "0")
os.environ.setdefault("DEEPFIELD_DISABLE_DAEMON", "1")

import src.arena_betting as ab


def _candidate(**over):
    ko = time.time() + 3600
    c = {
        "fixture_id": "990001",
        "sportmonks_fixture_id": "990001",
        "polymarket_fid": None,
        "match": "Testland vs Mocktopia",
        "team_code": "TST",
        "outcome": "home",
        "model_prob": 0.62,
        "market_mid": 0.54,
        "devigged_mid": 0.53,
        "edge": 0.08,
        "edge_pp": 8.0,
        "suggested_usd": 80.0,  # above the $50 cap on purpose
        "limit_price": 0.56,
        "kickoff": "2026-07-11 20:00:00",
        "kickoff_ts": ko,
        "qualifies": True,
        "real_arb": False,
        "token_id": "tok1",
        "prob_source": "WC+DFP",
    }
    c.update(over)
    return c


@pytest.fixture()
def paper_env(monkeypatch, tmp_path):
    """Sandbox: tmp state file, enabled=True, disarmed, all network stubbed."""
    state_file = tmp_path / "autopilot_state.json"
    base = ab._default_state()
    base["enabled"] = True
    state_file.write_text(json.dumps(base), encoding="utf-8")
    monkeypatch.setattr(ab, "STATE_FILE", str(state_file))
    monkeypatch.setattr(ab, "_arena_live", lambda: False)

    # Network touchpoints — stubbed; requests itself raises as a backstop.
    ledger_calls = []
    monkeypatch.setattr(
        ab, "submit_ledger", lambda *a, **k: ledger_calls.append(a) or (200, {})
    )
    order_calls = []
    monkeypatch.setattr(
        ab, "place_order", lambda *a, **k: order_calls.append(a) or (0, {"error": "should not be called"})
    )
    monkeypatch.setattr(ab, "analyze", lambda *a, **k: [_candidate()])
    monkeypatch.setattr(ab, "get_wallet", lambda: None)
    monkeypatch.setattr(ab, "get_order_book", lambda *a, **k: None)
    monkeypatch.setattr(ab, "get_exposure", lambda: None)
    monkeypatch.setattr(ab, "list_orders", lambda *a, **k: [])
    monkeypatch.setattr(ab, "get_settlement", lambda *a, **k: None)
    monkeypatch.setattr(ab, "get_leaderboard", lambda *a, **k: [])
    monkeypatch.setattr(ab, "get_mapping", lambda *a, **k: None)
    monkeypatch.setattr(ab, "_get_tipster_picks", lambda: [{"stub": True}])
    monkeypatch.setattr(ab, "_tipster_agrees", lambda *a, **k: True)

    def _boom(*a, **k):
        raise AssertionError("raw network call attempted in paper mode")

    monkeypatch.setattr(ab.requests, "post", _boom, raising=True)
    monkeypatch.setattr(ab.requests, "get", _boom, raising=True)

    fake_alerting = types.SimpleNamespace(
        notifier=types.SimpleNamespace(_notify=lambda *a, **k: None)
    )
    monkeypatch.setitem(sys.modules, "src.services.alerting", fake_alerting)

    return {"state_file": state_file, "orders": order_calls, "ledger": ledger_calls}


class TestPaperMode:
    def test_shadow_bet_recorded_no_order_posted(self, paper_env):
        summary = ab.autopilot_cycle()
        assert "[PAPER]" in summary
        assert paper_env["orders"] == []  # place_order never touched

        st = json.loads(paper_env["state_file"].read_text(encoding="utf-8"))
        placed = [p for p in st.get("placed", []) if p.get("paper")]
        assert len(placed) == 1
        bet = placed[0]
        assert bet["ok"] is True
        assert bet["order_status"] == "PAPER"
        # $80 suggested must be clamped by the $50 per-order cap
        assert bet["staked_usd"] == pytest.approx(50.0)
        assert "990001:home" in st.get("placed_keys", [])
        assert st["daily"]["spent"] == pytest.approx(50.0)

    def test_paused_autopilot_places_nothing_even_in_paper(self, paper_env):
        st = json.loads(paper_env["state_file"].read_text(encoding="utf-8"))
        st["enabled"] = False
        paper_env["state_file"].write_text(json.dumps(st), encoding="utf-8")
        summary = ab.autopilot_cycle()
        assert "[PAPER]" not in summary
        st2 = json.loads(paper_env["state_file"].read_text(encoding="utf-8"))
        assert [p for p in st2.get("placed", []) if p.get("paper")] == []

    def test_paper_bets_still_respect_conviction_cap(self, paper_env, monkeypatch):
        monkeypatch.setattr(
            ab, "analyze", lambda *a, **k: [_candidate(edge=0.66, edge_pp=66.0)]
        )
        ab.autopilot_cycle()
        st = json.loads(paper_env["state_file"].read_text(encoding="utf-8"))
        assert [p for p in st.get("placed", []) if p.get("paper")] == []

    def test_paper_bets_still_respect_forebet_gate(self, paper_env, monkeypatch):
        monkeypatch.setattr(ab, "_tipster_agrees", lambda *a, **k: False)
        ab.autopilot_cycle()
        st = json.loads(paper_env["state_file"].read_text(encoding="utf-8"))
        assert [p for p in st.get("placed", []) if p.get("paper")] == []


class TestPaperReport:
    def _load_tool(self):
        path = os.path.join(ROOT, "tools", "arena_paper_report.py")
        spec = importlib.util.spec_from_file_location("arena_paper_report_t", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_grading_win_loss_open(self):
        mod = self._load_tool()
        state = {
            "placed": [
                {"paper": True, "ok": True, "fixture_id": "1", "outcome": "home",
                 "staked_usd": 50.0, "limit_price": 0.50, "match": "A vs B",
                 "model_prob": 0.6, "edge_pp": 8.0, "ts": "t1"},
                {"paper": True, "ok": True, "fixture_id": "2", "outcome": "away",
                 "staked_usd": 20.0, "limit_price": 0.25, "match": "C vs D",
                 "model_prob": 0.55, "edge_pp": 6.0, "ts": "t2"},
                {"paper": True, "ok": True, "fixture_id": "3", "outcome": "draw",
                 "staked_usd": 10.0, "limit_price": 0.30, "match": "E vs F",
                 "model_prob": 0.52, "edge_pp": 5.5, "ts": "t3"},
                # real bet must be excluded from the paper report
                {"paper": False, "ok": True, "fixture_id": "1", "outcome": "home",
                 "staked_usd": 87.0, "limit_price": 0.15, "match": "A vs B",
                 "model_prob": 0.8, "edge_pp": 66.0, "ts": "t0"},
            ],
            "settlements": [
                {"fixture_id": "1", "outcome": "home"},   # win
                {"fixture_id": "2", "outcome": "home"},   # loss (bet away)
            ],
        }
        rows = mod.grade(state)
        assert len(rows) == 3
        by_fid = {r["match"]: r for r in rows}
        assert by_fid["A vs B"]["result"] == "WIN"
        assert by_fid["A vs B"]["pnl"] == pytest.approx(50.0)  # 50*(1/0.5-1)
        assert by_fid["C vs D"]["result"] == "LOSS"
        assert by_fid["C vs D"]["pnl"] == pytest.approx(-20.0)
        assert by_fid["E vs F"]["result"] == "OPEN"
        s = mod.summarize(rows)
        assert s["settled"] == 2 and s["wins"] == 1
        assert s["pnl"] == pytest.approx(30.0)
        assert s["staked"] == pytest.approx(70.0)
