"""The prediction daemon must not be able to die silently.

On 2026-08-24 at 23:02 the run_daemon thread raised a TypeError and exited.
Flask kept serving /api/state every 30 minutes all night, so the dashboard
looked completely healthy while nothing scraped, predicted or settled for ten
hours. The bare `threading.Thread(target=run_daemon, daemon=True)` had nothing
watching it and nothing to restart it.

supervise() wraps the target so a crash is logged loudly, counted, exposed to
the API, and retried with backoff instead of ending the worker for good.
"""

import importlib

import pytest

ds = importlib.import_module("src.daemon_supervisor")


@pytest.fixture(autouse=True)
def fresh():
    ds.reset_health()
    yield
    ds.reset_health()


class _Sleeper:
    """Records backoff delays instead of actually sleeping."""

    def __init__(self):
        self.calls = []

    def __call__(self, seconds):
        self.calls.append(seconds)


# ---------------------------------------------------------------------------
# restart behaviour
# ---------------------------------------------------------------------------


def test_target_is_run():
    ran = []
    ds.supervise(lambda: ran.append(1), name="t", max_restarts=1, sleep=_Sleeper())
    assert ran == [1]


def test_crash_is_retried_not_fatal():
    calls = []

    def boom():
        calls.append(1)
        raise RuntimeError("kaboom")

    ds.supervise(boom, name="t", max_restarts=4, sleep=_Sleeper())
    assert len(calls) == 4, "a crashing target must be restarted, not abandoned"


def test_supervise_never_propagates_the_targets_exception():
    def boom():
        raise TypeError("log_pinnacle_value_bet() got an unexpected keyword argument")

    ds.supervise(boom, name="t", max_restarts=2, sleep=_Sleeper())  # must not raise


def test_clean_return_is_also_restarted():
    """run_daemon loops forever; returning at all means something ended it."""
    calls = []
    ds.supervise(lambda: calls.append(1), name="t", max_restarts=3, sleep=_Sleeper())
    assert len(calls) == 3


def test_backoff_grows_then_caps():
    s = _Sleeper()

    def boom():
        raise RuntimeError("x")

    ds.supervise(boom, name="t", max_restarts=8, sleep=s, base_backoff=2, max_backoff=10)
    assert s.calls == sorted(s.calls), "backoff must be non-decreasing"
    assert max(s.calls) <= 10, "backoff must be capped"
    assert s.calls[0] == 2


def test_backoff_resets_after_a_long_healthy_run(monkeypatch):
    """A crash after hours of healthy running must not inherit the old backoff."""
    s = _Sleeper()
    clock = {"t": 1000.0}
    monkeypatch.setattr(ds.time, "monotonic", lambda: clock["t"])
    n = {"i": 0}

    def target():
        n["i"] += 1
        clock["t"] += 3600 if n["i"] % 2 else 0  # every other run is long
        raise RuntimeError("x")

    ds.supervise(target, name="t", max_restarts=6, sleep=s, base_backoff=2, max_backoff=60)
    assert s.calls.count(2) >= 2, f"backoff should reset after a healthy run: {s.calls}"


# ---------------------------------------------------------------------------
# health reporting — the part that makes a dead worker visible
# ---------------------------------------------------------------------------


def test_health_starts_clean():
    h = ds.get_health()
    assert h["restarts"] == 0
    assert h["last_crash"] is None


def test_health_records_the_crash_details():
    def boom():
        raise TypeError("got an unexpected keyword argument 'fixture_ns'")

    ds.supervise(boom, name="predictions", max_restarts=1, sleep=_Sleeper())
    h = ds.get_health()
    assert h["restarts"] == 1
    assert "TypeError" in h["last_crash"]
    assert "fixture_ns" in h["last_crash"]
    assert h["last_crash_at"] is not None
    assert h["name"] == "predictions"


def test_health_counts_repeated_crashes():
    def boom():
        raise RuntimeError("x")

    ds.supervise(boom, name="t", max_restarts=5, sleep=_Sleeper())
    assert ds.get_health()["restarts"] == 5


def test_health_reports_alive_while_running():
    seen = {}

    def target():
        seen["alive"] = ds.get_health()["alive"]

    ds.supervise(target, name="t", max_restarts=1, sleep=_Sleeper())
    assert seen["alive"] is True


def test_health_is_not_alive_after_supervisor_exits():
    ds.supervise(lambda: None, name="t", max_restarts=1, sleep=_Sleeper())
    assert ds.get_health()["alive"] is False


def test_on_crash_hook_is_called_with_the_exception():
    got = []

    def boom():
        raise ValueError("nope")

    ds.supervise(
        boom, name="t", max_restarts=2, sleep=_Sleeper(), on_crash=lambda e: got.append(e)
    )
    assert len(got) == 2
    assert all(isinstance(e, ValueError) for e in got)


def test_a_failing_on_crash_hook_cannot_kill_the_supervisor():
    def boom():
        raise RuntimeError("x")

    def bad_hook(_e):
        raise OSError("alerting is down")

    ds.supervise(boom, name="t", max_restarts=3, sleep=_Sleeper(), on_crash=bad_hook)
    assert ds.get_health()["restarts"] == 3


# ---------------------------------------------------------------------------
# /api/health — the endpoint that makes "engine stopped" observable
# ---------------------------------------------------------------------------


@pytest.fixture
def client(tmp_path, monkeypatch):
    import importlib
    srv = importlib.import_module("src.live_dashboard_server")
    monkeypatch.setattr(srv, "DATA_DIR", str(tmp_path), raising=False)
    srv.app.config["TESTING"] = True
    return srv.app.test_client()


def test_health_endpoint_returns_json(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert "restarts" in r.get_json()


def test_health_endpoint_reports_not_ok_when_worker_is_dead(client):
    """The exact 2026-08-24 situation: Flask fine, worker gone."""
    ds.reset_health()  # alive=False
    body = client.get("/api/health").get_json()
    assert body["ok"] is False


def test_health_endpoint_surfaces_the_crash_reason(client):
    def boom():
        raise TypeError("got an unexpected keyword argument 'fixture_ns'")

    ds.supervise(boom, name="predictions", max_restarts=1, sleep=_Sleeper())
    body = client.get("/api/health").get_json()
    assert body["restarts"] == 1
    assert "fixture_ns" in body["last_crash"]
    assert body["ok"] is False


def test_health_endpoint_flags_a_stale_state_file(client):
    """A thread that exists but is wedged must still read as not-ok."""
    body = client.get("/api/health").get_json()
    assert body["state_stale"] is True  # tmp DATA_DIR has no state file
    assert body["ok"] is False
