"""daemon_supervisor.py — keep the prediction worker alive and its state visible.

Why this exists
---------------
On 2026-08-24 23:02 the run_daemon thread raised

    TypeError: log_pinnacle_value_bet() got an unexpected keyword argument 'fixture_ns'

and exited. It was started as a bare `threading.Thread(target=run_daemon,
daemon=True)`, so nothing noticed and nothing restarted it. Flask carried on
answering /api/state every 30 minutes, the dashboard looked perfectly healthy,
and for the next ten hours nothing was scraped, predicted or settled. A
py-spy dump was what finally showed the thread simply wasn't there any more.

Two failures compounded: the worker could die, and a dead worker was
indistinguishable from a working one. supervise() fixes both — it restarts the
target with capped exponential backoff, and it publishes a health record the
API can surface so "engine stopped" is visible instead of inferred.

Never re-raises: the supervisor itself must be the one thing that cannot fail.
"""

import threading
import time
import traceback

_LOCK = threading.Lock()

_HEALTH = {
    "name": None,
    "alive": False,
    "started_at": None,      # epoch of the most recent target start
    "restarts": 0,
    "last_crash": None,      # "TypeError: ..." + traceback tail
    "last_crash_at": None,   # epoch
}


def reset_health():
    """Clear the health record (tests; also safe on a fresh process)."""
    with _LOCK:
        _HEALTH.update(
            name=None,
            alive=False,
            started_at=None,
            restarts=0,
            last_crash=None,
            last_crash_at=None,
        )


def get_health():
    """Snapshot of worker health. Safe to call from any thread."""
    with _LOCK:
        return dict(_HEALTH)


def supervise(
    target,
    name="daemon",
    sleep=time.sleep,
    base_backoff=5.0,
    max_backoff=300.0,
    max_restarts=None,
    on_crash=None,
    healthy_after=600.0,
):
    """Run *target* forever, restarting it if it crashes OR returns.

    target        callable taking no arguments (e.g. run_daemon)
    max_restarts  stop after this many runs (tests only; None = forever)
    healthy_after seconds a run must last to be considered healthy, which
                  resets the backoff — a crash after six hours of good work
                  should retry immediately, not inherit an old 5-minute delay
    on_crash      optional callback(exception) for alerting; its own failures
                  are swallowed so alerting can never take the worker down
    """
    backoff = base_backoff
    runs = 0

    while max_restarts is None or runs < max_restarts:
        runs += 1
        started = time.monotonic()
        with _LOCK:
            _HEALTH["name"] = name
            _HEALTH["alive"] = True
            _HEALTH["started_at"] = time.time()

        try:
            target()
            # run_daemon() is an infinite loop — a clean return means something
            # ended it, which is just as wrong as an exception.
            detail = f"{name} returned unexpectedly (it should loop forever)"
            print(f"[SUPERVISOR] {detail} — restarting.")
            exc = None
        except BaseException as e:  # noqa: BLE001 - the supervisor catches everything
            exc = e
            detail = f"{type(e).__name__}: {e}"
            print(f"[SUPERVISOR] {name} CRASHED: {detail}")
            traceback.print_exc()

        ran_for = time.monotonic() - started

        with _LOCK:
            _HEALTH["alive"] = False
            _HEALTH["restarts"] += 1
            _HEALTH["last_crash"] = (
                f"{detail}\n{traceback.format_exc()}" if exc is not None else detail
            )
            _HEALTH["last_crash_at"] = time.time()

        if on_crash is not None and exc is not None:
            try:
                on_crash(exc)
            except Exception:
                pass  # alerting must never be able to kill the worker

        # A long healthy run means the previous backoff is stale.
        if ran_for >= healthy_after:
            backoff = base_backoff

        if max_restarts is None or runs < max_restarts:
            print(f"[SUPERVISOR] restarting {name} in {backoff:.0f}s "
                  f"(restart #{_HEALTH['restarts']}).")
            sleep(backoff)
            backoff = min(backoff * 2.0, max_backoff)


def start_supervised(target, name="daemon", **kwargs):
    """Launch supervise() on a daemon thread. Returns the Thread."""
    t = threading.Thread(
        target=supervise,
        args=(target,),
        kwargs=dict(name=name, **kwargs),
        name=f"supervisor-{name}",
        daemon=True,
    )
    t.start()
    return t
