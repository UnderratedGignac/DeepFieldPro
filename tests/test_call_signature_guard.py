"""Every keyword argument passed in the daemon must exist on the callee.

This exists because of a real outage. Threading `fixture_ns` onto the bet
loggers was done with a bulk text replace of `fixture_id=fid,`, which also hit
two calls that take no such parameter:

    log_pinnacle_value_bet(...)  -> TypeError, killed the run_daemon thread
    is_good_time_to_bet(...)     -> TypeError, swallowed by a bare `except`,
                                    silently disabling the bet-timing filter

The daemon thread died at 23:02 while Flask kept serving /api/state normally,
so the dashboard looked healthy through an entire night with zero settlements.
py_compile and import checks cannot catch this — the call is only type-checked
when it executes, and the loud one only executes deep inside a prediction cycle.

The check is static (AST): for every call in the module that uses keyword
arguments and resolves to a function defined in this repo, assert the callee
accepts those keywords. Cheap, and it fails at test time instead of at 23:02.
"""

import ast
import io
import os

import pytest

SRC = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"
)
DAEMON = os.path.join(SRC, "live_predictions_daemon.py")


def _defs_in(path):
    """{func_name: (accepted_kwarg_names, accepts_kwargs)} for one module."""
    tree = ast.parse(io.open(path, encoding="utf-8").read())
    out = {}
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            names = {a.arg for a in n.args.args} | {a.arg for a in n.args.kwonlyargs}
            out[n.name] = (names, n.args.kwarg is not None)
    return out


def _all_repo_defs():
    defs = {}
    for fn in sorted(os.listdir(SRC)):
        if not fn.endswith(".py"):
            continue
        try:
            for name, sig in _defs_in(os.path.join(SRC, fn)).items():
                # First definition wins; duplicates across modules are rare and
                # a false "accepted" is safer than a false failure here.
                defs.setdefault(name, sig)
        except SyntaxError:
            continue
    return defs


def _keyword_calls(path):
    """[(lineno, callee_name, {kwargs})] for calls with keyword arguments."""
    tree = ast.parse(io.open(path, encoding="utf-8").read())
    out = []
    for n in ast.walk(tree):
        if not isinstance(n, ast.Call) or not n.keywords:
            continue
        if not isinstance(n.func, ast.Name):
            continue  # skip obj.method() — receiver type is unknown statically
        kw = {k.arg for k in n.keywords if k.arg}
        if kw:
            out.append((n.lineno, n.func.id, kw))
    return out


DEFS = _all_repo_defs()
CALLS = _keyword_calls(DAEMON)


def test_there_are_calls_to_check():
    """Guard against the guard silently checking nothing."""
    assert len(CALLS) > 50


@pytest.mark.parametrize(
    "lineno,callee,kwargs",
    CALLS,
    ids=[f"{c[1]}:L{c[0]}" for c in CALLS],
)
def test_keyword_args_exist_on_callee(lineno, callee, kwargs):
    sig = DEFS.get(callee)
    if sig is None:
        pytest.skip(f"{callee} is not defined in src/ (stdlib or third-party)")
    accepted, takes_kwargs = sig
    if takes_kwargs:
        return  # **kwargs swallows anything
    unknown = kwargs - accepted
    assert not unknown, (
        f"live_predictions_daemon.py:{lineno} calls {callee}() with "
        f"{sorted(unknown)}, which it does not accept. Accepted: {sorted(accepted)}"
    )


def test_fixture_ns_only_goes_to_functions_that_take_it():
    """The specific regression: fixture_ns must only reach log_ai_bet."""
    offenders = []
    for lineno, callee, kwargs in CALLS:
        if "fixture_ns" not in kwargs:
            continue
        sig = DEFS.get(callee)
        if sig is None:
            offenders.append((lineno, callee, "not defined in src/"))
        elif "fixture_ns" not in sig[0] and not sig[1]:
            offenders.append((lineno, callee, "does not accept fixture_ns"))
    assert not offenders, f"fixture_ns passed to functions that reject it: {offenders}"
