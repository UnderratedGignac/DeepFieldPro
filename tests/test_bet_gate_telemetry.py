"""Why didn't the engine bet? Gate telemetry.

No strategy has placed a bet since 2026-08-18 even though MODEL_VALUE_ALIGN and
PINNACLE_VALUE are both enabled in settings.json. The daemon evaluates a long
`and` chain per selection and logs nothing when it fails, so a silently-blocked
engine is indistinguishable from one with nothing to bet — the same class of
invisibility that hid the dead daemon thread on 2026-08-24.

GateCounter records which conditions rejected each selection. The number that
matters is `sole_blocker`: selections where exactly ONE gate failed, i.e. the
gate you would change to start betting again.
"""

import importlib

import pytest

bgt = importlib.import_module("src.bet_gate_telemetry")


@pytest.fixture
def gc():
    return bgt.GateCounter()


# ---------------------------------------------------------------------------
# record() must behave exactly like the `and` chain it replaces
# ---------------------------------------------------------------------------


def test_record_returns_true_when_every_gate_passes(gc):
    assert gc.record("MODEL", {"ev": True, "prob": True}) is True


def test_record_returns_false_when_any_gate_fails(gc):
    assert gc.record("MODEL", {"ev": True, "prob": False}) is False


def test_record_coerces_truthy_values_like_the_and_chain(gc):
    """The original chain included bare values such as `and odds`."""
    assert gc.record("PV", {"odds": 2.5, "edge": 0.1}) is True
    assert gc.record("PV", {"odds": 0, "edge": 0.1}) is False
    assert gc.record("PV", {"odds": None, "edge": 0.1}) is False


def test_empty_gate_set_passes(gc):
    assert gc.record("MODEL", {}) is True


# ---------------------------------------------------------------------------
# counting
# ---------------------------------------------------------------------------


def test_counts_evaluated_and_passed(gc):
    gc.record("MODEL", {"a": True})
    gc.record("MODEL", {"a": False})
    gc.record("MODEL", {"a": True})
    s = gc.summary()["MODEL"]
    assert s["evaluated"] == 3
    assert s["passed"] == 2


def test_counts_every_failing_gate_not_just_the_first(gc):
    gc.record("MODEL", {"a": False, "b": False, "c": True})
    s = gc.summary()["MODEL"]
    assert s["blocked_by"]["a"] == 1
    assert s["blocked_by"]["b"] == 1
    assert "c" not in s["blocked_by"]


def test_sole_blocker_identifies_the_one_gate_to_change(gc):
    # 5 selections blocked ONLY by tipster_ok -> flipping it unblocks 5 bets
    for _ in range(5):
        gc.record("MODEL", {"ev": True, "tipster_ok": False, "odds_fresh": True})
    # 2 blocked by two things at once -> not actionable on its own
    for _ in range(2):
        gc.record("MODEL", {"ev": False, "tipster_ok": False, "odds_fresh": True})
    s = gc.summary()["MODEL"]
    assert s["sole_blocker"]["tipster_ok"] == 5
    assert "ev" not in s["sole_blocker"]
    assert s["blocked_by"]["tipster_ok"] == 7


def test_strategies_are_counted_separately(gc):
    gc.record("MODEL", {"a": False})
    gc.record("PV", {"b": False})
    s = gc.summary()
    assert set(s) == {"MODEL", "PV"}
    assert s["MODEL"]["blocked_by"] == {"a": 1}
    assert s["PV"]["blocked_by"] == {"b": 1}


def test_reset_clears_everything(gc):
    gc.record("MODEL", {"a": False})
    gc.reset()
    assert gc.summary() == {}


# ---------------------------------------------------------------------------
# reporting
# ---------------------------------------------------------------------------


def test_format_summary_names_the_dominant_blocker(gc):
    for _ in range(9):
        gc.record("MODEL", {"ev": True, "tipster_ok": False})
    gc.record("MODEL", {"ev": False, "tipster_ok": True})
    out = gc.format_summary()
    assert "MODEL" in out
    assert "tipster_ok" in out
    assert "0/10" in out or "0 of 10" in out


def test_format_summary_is_quiet_when_nothing_was_evaluated(gc):
    assert gc.format_summary() == ""


def test_format_summary_reports_a_healthy_engine(gc):
    for _ in range(3):
        gc.record("MODEL", {"ev": True})
    out = gc.format_summary()
    assert "3/3" in out or "3 of 3" in out


def test_module_singleton_exists():
    assert isinstance(bgt.GATES, bgt.GateCounter)


def test_record_never_raises_on_junk(gc):
    """Telemetry must never be able to break the bet path."""
    assert gc.record("MODEL", None) is True
    gc.record(None, {"a": False})
    gc.format_summary()


def test_roll_snapshots_then_resets(gc):
    gc.record("MODEL", {"tipster_ok": False})
    snap = gc.roll()
    assert snap["MODEL"]["blocked_by"]["tipster_ok"] == 1
    assert gc.summary() == {}, "counts must be per-cycle"
    assert gc.last_summary["MODEL"]["blocked_by"]["tipster_ok"] == 1


def test_last_summary_survives_between_cycles(gc):
    gc.record("MODEL", {"a": False})
    gc.roll()
    gc.record("MODEL", {"a": True})   # next cycle in progress
    assert gc.last_summary["MODEL"]["passed"] == 0


def test_last_summary_starts_empty(gc):
    assert gc.last_summary == {}
