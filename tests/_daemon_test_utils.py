"""Shared guarded import of src.live_predictions_daemon for unit tests.

The daemon module is heavyweight (pandas / joblib / SQLAlchemy) but performs no
network I/O at import time — verified by importing with sockets blocked. This
helper re-applies that guard on every fresh import so a future regression
(e.g. a module-level requests call sneaking in) fails loudly inside the test
suite instead of silently hitting the internet.

Not a test file (name doesn't match test_*.py) — import helpers only.
"""

import os
import socket
import sys

# Hard safety defaults for any test process that pulls this in.
os.environ["DEEPFIELD_ARENA_LIVE"] = "0"
os.environ.setdefault("DEEPFIELD_DISABLE_DAEMON", "1")
os.environ.pop("DEEPFIELD_DAEMON_LIVE_ORDERS", None)


class _BlockedSocket(socket.socket):
    def connect(self, *args, **kwargs):  # pragma: no cover - guard only
        raise RuntimeError(f"network blocked during daemon import: connect{args}")

    def connect_ex(self, *args, **kwargs):  # pragma: no cover - guard only
        raise RuntimeError(f"network blocked during daemon import: connect_ex{args}")


def _blocked_create_connection(*args, **kwargs):  # pragma: no cover - guard only
    raise RuntimeError("network blocked during daemon import")


def import_daemon():
    """Import src.live_predictions_daemon with outbound sockets disabled.

    Returns the (cached) module. Safe to call from multiple test modules.
    """
    if "src.live_predictions_daemon" in sys.modules:
        return sys.modules["src.live_predictions_daemon"]

    real_socket = socket.socket
    real_create_connection = socket.create_connection
    socket.socket = _BlockedSocket
    socket.create_connection = _blocked_create_connection
    try:
        import src.live_predictions_daemon as lpd
    finally:
        socket.socket = real_socket
        socket.create_connection = real_create_connection
    return lpd
