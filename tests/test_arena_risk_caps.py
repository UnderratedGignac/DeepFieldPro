"""Risk-cap guardrail tests for the real-money Arena path (added 2026-07-10).

Context: the 'TOURNAMENT MODE' drift left the ARMED autopilot with no dollar
ceiling below the full wallet (per-order cap $100 on a ~$113 wallet, daily
caps $999, wallet buffer $0) and the book went to -$226 unrealized. These
tests pin the tightened regime:

  per-order <= $10 | daily <= $25 | last $10 untouchable | <= 10% wallet/pick
  conf >= 0.50 | edge >= 0.05 | AP2 mandate fail-CLOSED | control endpoints
  localhost-only | ntfy unlock never resets the daily spend counter

If one of these fails, the real-money path has been loosened. Do that
deliberately (and update this file in the same commit) or not at all.
"""
import json
import os
import sys
import time

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

os.environ.setdefault("DEEPFIELD_ARENA_LIVE", "0")
os.environ.setdefault("DEEPFIELD_DISABLE_DAEMON", "1")

import src.arena_betting as ab
from src.ap2_mandate import SpendingMandate


# ---------------------------------------------------------------------------
# 1. Module constants — the hard code-level ceilings
# ---------------------------------------------------------------------------
class TestDollarCaps:
    def test_per_bet_cap_at_most_10(self):
        assert ab.MAX_USD_PER_BET <= 10.0

    def test_ap2_cap_matches_per_bet_cap(self):
        assert ab.AP2_MAX_PER_ORDER == ab.MAX_USD_PER_BET

    def test_daily_spend_cap_at_most_25(self):
        assert ab.DAILY_SPEND_CAP <= 25.0

    def test_wallet_buffer_at_least_10(self):
        assert ab.WALLET_BUFFER >= 10.0

    def test_single_pick_wallet_fraction_at_most_25pct(self):
        assert ab.MAX_WALLET_FRACTION <= 0.25

    def test_max_bets_per_run_at_most_5(self):
        assert ab.MAX_BETS_PER_RUN <= 5

    def test_confidence_floor_at_least_50pct(self):
        assert ab.CONF_MIN_DEFAULT >= 0.50

    def test_edge_floor_at_least_5pp(self):
        assert ab.EDGE_MIN_DEFAULT >= 0.05


# ---------------------------------------------------------------------------
# 2. settings.json overrides — AP2 mandate as actually loaded
# ---------------------------------------------------------------------------
class TestMandateFromLiveSettings:
    @pytest.fixture()
    def mandate(self):
        return SpendingMandate.from_settings()

    def test_max_per_order(self, mandate):
        assert mandate.max_per_order <= 10.0

    def test_daily_cap(self, mandate):
        assert mandate.daily_cap <= 25.0

    def test_wallet_buffer(self, mandate):
        assert mandate.wallet_buffer >= 10.0

    def test_conf_min(self, mandate):
        assert mandate.conf_min >= 0.50

    def test_edge_min(self, mandate):
        assert mandate.edge_min >= 0.05


# ---------------------------------------------------------------------------
# 3. AP2 is fail-CLOSED: no mandate layer -> no order, mandate error -> no order
# ---------------------------------------------------------------------------
class TestAP2FailClosed:
    @pytest.fixture(autouse=True)
    def no_network(self, monkeypatch):
        def _boom(*a, **k):
            raise AssertionError("network call attempted on a blocked order path")

        monkeypatch.setattr(ab.requests, "post", _boom, raising=True)
        monkeypatch.setattr(ab.requests, "get", _boom, raising=True)

    def test_place_order_refuses_when_ap2_unavailable(self, monkeypatch):
        monkeypatch.setattr(ab, "_AP2", False)
        # Even with the live gate open, no AP2 layer must mean no order.
        monkeypatch.setattr(ab, "_arena_live", lambda: True)
        sc, resp = ab.place_order("123", "FRA", 5.0, 0.50)
        assert sc != 200 and sc != 201
        assert "fail-closed" in json.dumps(resp).lower()

    def test_place_order_refuses_when_mandate_check_errors(self, monkeypatch):
        class _BrokenMandate:
            @classmethod
            def from_settings(cls, *a, **k):
                raise RuntimeError("settings unreadable")

        monkeypatch.setattr(ab, "_AP2", True)
        monkeypatch.setattr(ab, "_Mandate", _BrokenMandate)
        monkeypatch.setattr(ab, "_arena_live", lambda: True)
        sc, resp = ab.place_order("123", "FRA", 5.0, 0.50)
        assert sc != 200 and sc != 201
        assert "fail-closed" in json.dumps(resp).lower()

    def test_submit_order_fok_blocked_when_disarmed(self, monkeypatch):
        # The FOK helper is called by tools directly — its gates live inside.
        monkeypatch.setattr(ab, "_arena_live", lambda: False)
        sc, resp = ab.submit_order_fok("1", "FRA", 113.0, 0.99)
        assert sc == 0
        assert resp.get("error") == "blocked"

    def test_submit_order_fok_fail_closed_without_ap2(self, monkeypatch):
        monkeypatch.setattr(ab, "_arena_live", lambda: True)
        monkeypatch.setattr(ab, "_AP2", False)
        sc, resp = ab.submit_order_fok("1", "FRA", 5.0, 0.50)
        assert sc == 402
        assert "fail-closed" in json.dumps(resp).lower()


# ---------------------------------------------------------------------------
# 4. Control endpoints are localhost-only
# ---------------------------------------------------------------------------
class TestEndpointLocalhostGate:
    @pytest.fixture()
    def client(self, monkeypatch, tmp_path):
        from flask import Flask

        monkeypatch.setattr(ab, "STATE_FILE", str(tmp_path / "autopilot_state.json"))
        app = Flask(__name__)
        app.register_blueprint(ab.arena_bp)
        return app.test_client()

    def test_toggle_blocked_from_lan(self, client):
        r = client.post(
            "/arena/api/toggle",
            json={"enabled": True},
            environ_base={"REMOTE_ADDR": "192.168.1.50"},
        )
        assert r.status_code == 403

    def test_toggle_allowed_from_localhost(self, client):
        r = client.post(
            "/arena/api/toggle",
            json={"enabled": False},
            environ_base={"REMOTE_ADDR": "127.0.0.1"},
        )
        assert r.status_code == 200
        assert r.get_json()["enabled"] is False

    def test_pause_allowed_from_lan_as_kill_switch(self, client):
        # Pausing must stay reachable from any device (emergency stop);
        # only ARMING is localhost-restricted.
        r = client.post(
            "/arena/api/toggle",
            json={"enabled": False},
            environ_base={"REMOTE_ADDR": "192.168.1.50"},
        )
        assert r.status_code == 200
        assert r.get_json()["enabled"] is False

    def test_order_fok_blocked_from_lan(self, client):
        r = client.post(
            "/arena/api/order_fok",
            json={"fixture_id": "1", "team_code": "FRA", "usd_size": 113,
                  "worst_price": 0.99, "confirm": True},
            environ_base={"REMOTE_ADDR": "10.0.0.7"},
        )
        assert r.status_code == 403

    def test_order_fok_requires_confirm(self, client):
        r = client.post(
            "/arena/api/order_fok",
            json={"fixture_id": "1", "team_code": "FRA", "usd_size": 5,
                  "worst_price": 0.5},
            environ_base={"REMOTE_ADDR": "127.0.0.1"},
        )
        assert r.status_code == 400

    def test_close_blocked_from_lan(self, client):
        r = client.post(
            "/arena/api/close",
            json={"order_id": "x", "limit_price": 0.01, "confirm": True},
            environ_base={"REMOTE_ADDR": "10.0.0.7"},
        )
        assert r.status_code == 403

    def test_close_requires_confirm(self, client):
        r = client.post(
            "/arena/api/close",
            json={"order_id": "x", "limit_price": 0.01},
            environ_base={"REMOTE_ADDR": "127.0.0.1"},
        )
        assert r.status_code == 400

    def test_research_sweep_blocked_from_lan(self, client):
        r = client.post(
            "/arena/api/research_sweep",
            json={"source": "wc", "confirm": True},
            environ_base={"REMOTE_ADDR": "10.0.0.7"},
        )
        assert r.status_code == 403

    def test_settings_post_blocked_from_lan(self, client):
        r = client.post(
            "/arena/api/settings",
            json={"conf_min": 0.0, "edge_min": 0.0, "max_per_bet": 100},
            environ_base={"REMOTE_ADDR": "10.0.0.7"},
        )
        assert r.status_code == 403

    def test_settings_get_still_readable(self, client):
        r = client.get(
            "/arena/api/settings", environ_base={"REMOTE_ADDR": "10.0.0.7"}
        )
        assert r.status_code == 200

    def test_place_still_blocked_from_lan(self, client):
        r = client.post(
            "/arena/api/place",
            json={"confirm": True},
            environ_base={"REMOTE_ADDR": "10.0.0.7"},
        )
        assert r.status_code == 403


# ---------------------------------------------------------------------------
# 5. Conviction cap — huge model-vs-market disagreement is error, not value
# ---------------------------------------------------------------------------
class TestConvictionCap:
    """The 2,386-bet line study showed the model's largest disagreements with
    the market are its largest ERRORS. The two biggest recent real-money
    losses were placed at '66.5pp' and '72.3pp' edges (France $87.05,
    Argentina $35.17) — data-bug-sized numbers no real edge produces. The
    paper daemon caps conviction at 10pp; the arena must cap too."""

    def _risk(self):
        r = ab._load_risk_settings()
        return r

    def test_edge_cap_configured_at_most_20pp(self):
        assert self._risk()["edge_cap_pp"] <= 20.0

    def test_bug_sized_edge_is_blocked(self):
        c = {"edge_pp": 66.5, "real_arb": False}
        assert ab._conviction_capped(c, self._risk()) is True

    def test_moderate_edge_passes(self):
        c = {"edge_pp": 8.0, "real_arb": False}
        assert ab._conviction_capped(c, self._risk()) is False

    def test_real_arbitrage_exempt(self):
        c = {"edge_pp": 66.5, "real_arb": True}
        assert ab._conviction_capped(c, self._risk()) is False

    def test_fractional_edge_field_fallback(self):
        # candidates sometimes carry edge as a fraction, not pp
        c = {"edge": 0.45, "real_arb": False}
        assert ab._conviction_capped(c, self._risk()) is True


# ---------------------------------------------------------------------------
# 6. ntfy unlock must never reset the daily spend counter
# ---------------------------------------------------------------------------
class TestNtfyUnlock:
    def test_unlock_keeps_daily_spend_and_started_fixtures(self):
        now_ts = time.time()
        st = {
            "daily": {"date": "2026-07-10", "spent": 12.50},
            "placed_keys": ["f_future:home", "f_started:away"],
            "last_candidates": [
                {"fixture_id": "f_future", "kickoff_ts": now_ts + 3600},
                {"fixture_id": "f_started", "kickoff_ts": now_ts - 60},
            ],
        }
        unlocked = ab._apply_ntfy_unlock(st, now_ts)
        assert unlocked == 1
        assert st["placed_keys"] == ["f_started:away"]  # started stays deduped
        assert st["daily"]["spent"] == pytest.approx(12.50)  # cap still binds
