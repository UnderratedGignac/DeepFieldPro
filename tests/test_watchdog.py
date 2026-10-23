"""The server must come back by itself, and there must never be two of it.

On 2026-10-23 the dashboard server died silently at ~08:07 because it had been
started from a Claude session that then restarted; nothing bet or settled for
~5 hours. tools/watchdog.py is now a one-shot check run by Task Scheduler every
5 minutes. These tests pin its decisions: start when nothing runs, restart only
on sustained failure (a single slow health call or a long first cycle is not a
fault), and collapse twin servers, which double-place every bet.
"""

import importlib

wd = importlib.import_module("tools.watchdog")

HEALTHY = {"alive": True, "ok": True, "state_age_sec": 120.0, "state_stale": False}


def _decide(roots=1, age_min=120.0, health=HEALTHY, fails=0):
    return wd.decide(roots, age_min, health, fails)


# ---------------------------------------------------------------------------
# decide()
# ---------------------------------------------------------------------------


def test_healthy_server_is_left_alone_and_resets_failures():
    action, _, fails = _decide(fails=2)
    assert action == "ok"
    assert fails == 0


def test_no_server_process_starts_one():
    action, _, _ = _decide(roots=0, age_min=None, health=None)
    assert action == "start"


def test_unreachable_health_waits_before_restarting():
    assert _decide(health=None, fails=0)[0] == "wait"
    assert _decide(health=None, fails=1)[0] == "wait"


def test_unreachable_health_restarts_on_third_consecutive_failure():
    action, _, fails = _decide(health=None, fails=2)
    assert action == "restart"
    assert fails == 0


def test_booting_server_without_http_yet_is_not_a_failure():
    action, _, fails = _decide(health=None, age_min=2.0, fails=2)
    assert action == "wait"
    assert fails == 2


def test_dead_worker_restarts_on_second_consecutive_report():
    dead = {**HEALTHY, "alive": False, "ok": False}
    assert _decide(health=dead, fails=0)[0] == "wait"
    assert _decide(health=dead, fails=1)[0] == "restart"


def test_long_first_cycle_is_not_a_wedge():
    # A restart after a long gap took ~30 min before the first state write.
    booting = {**HEALTHY, "ok": False, "state_stale": True, "state_age_sec": 6 * 3600.0}
    assert _decide(health=booting, age_min=40.0)[0] == "ok"


def test_wedged_server_with_stale_state_is_restarted():
    wedged = {**HEALTHY, "ok": False, "state_stale": True, "state_age_sec": 2 * 3600.0}
    action, reason, _ = _decide(health=wedged, age_min=180.0)
    assert action == "restart"
    assert "stale" in reason


def test_twin_servers_are_collapsed_to_one():
    action, reason, _ = _decide(roots=2)
    assert action == "restart"
    assert "2" in reason


# ---------------------------------------------------------------------------
# server_roots(): one server is a cmd wrapper + venv launcher + interpreter
# ---------------------------------------------------------------------------

CMD = 'cmd.exe /c "set DEEPFIELD_PORT=5058&& python.exe -u src\\live_dashboard_server.py"'
VENV = '"C:\\x\\.venv\\Scripts\\python.exe" -u src\\live_dashboard_server.py'
BASE = '"C:\\Python312\\python.exe" -u src\\live_dashboard_server.py'


def test_one_server_process_chain_is_one_root():
    procs = [(10, 1, CMD), (11, 10, VENV), (12, 11, BASE), (99, 1, "python.exe other.py")]
    assert wd.server_roots(procs) == [10]


def test_two_independent_chains_are_two_roots():
    procs = [(10, 1, CMD), (11, 10, VENV), (20, 3, VENV), (21, 20, BASE)]
    assert sorted(wd.server_roots(procs)) == [10, 20]


def test_unrelated_python_processes_are_never_counted():
    procs = [(5, 1, "python.exe oracle_mcp_server.py"), (6, 1, "pythonw.exe guardian.py")]
    assert wd.server_roots(procs) == []


# ---------------------------------------------------------------------------
# pick_port(): an orphaned LISTENING socket must not block the restart
# ---------------------------------------------------------------------------


def test_preferred_port_used_when_free():
    assert wd.pick_port(5058, lambda p: False) == 5058


def test_next_free_port_when_preferred_is_held_by_an_orphan():
    busy = {5058, 5059}
    assert wd.pick_port(5058, lambda p: p in busy) == 5060
