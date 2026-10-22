"""bet_gate_telemetry.py — record WHY a selection was not bet.

The daemon decides whether to bet with long `and` chains (is_recommended,
_pv_qualifies). When one fails nothing is logged, so an engine that is silently
gated off looks exactly like an engine with nothing worth betting. That is how
no strategy placed a bet between 2026-08-18 and 2026-08-25 while
MODEL_VALUE_ALIGN and PINNACLE_VALUE both sat enabled in settings.json — the
same invisibility that hid the dead daemon thread on 2026-08-24.

GateCounter turns each chain into a named dict, so `record()` both evaluates the
chain (identically to `and`-ing the values) and counts the rejections.

The actionable number is `sole_blocker`: selections where exactly ONE gate
failed. "1,150 selections blocked only by tipster_ok" tells you precisely which
setting to change to start betting again; a gate that only ever fails alongside
others is not on its own the reason.

Never raises — telemetry must not be able to break the bet path.
"""

import threading
from collections import Counter, defaultdict


class GateCounter:
    """Counts gate outcomes per strategy. Thread-safe."""

    def __init__(self):
        self.last_summary = {}  # previous cycle, for /api/health
        self._lock = threading.Lock()
        self._evaluated = Counter()
        self._passed = Counter()
        self._blocked = defaultdict(Counter)
        self._sole = defaultdict(Counter)

    def record(self, strategy, gates):
        """Evaluate *gates* (dict of name -> truthy) and count the failures.

        Returns bool(all values truthy) — the same verdict as the `and` chain
        it replaces, since every downstream use is a boolean test.
        """
        try:
            if not gates:
                return True
            failed = [name for name, ok in gates.items() if not ok]
            with self._lock:
                self._evaluated[strategy] += 1
                if not failed:
                    self._passed[strategy] += 1
                else:
                    for name in failed:
                        self._blocked[strategy][name] += 1
                    if len(failed) == 1:
                        self._sole[strategy][failed[0]] += 1
            return not failed
        except Exception:
            # A telemetry bug must never change betting behaviour.
            try:
                return all(bool(v) for v in (gates or {}).values())
            except Exception:
                return True

    def summary(self):
        with self._lock:
            return {
                s: {
                    "evaluated": self._evaluated[s],
                    "passed": self._passed[s],
                    "blocked_by": dict(self._blocked[s]),
                    "sole_blocker": dict(self._sole[s]),
                }
                for s in self._evaluated
            }

    def format_summary(self):
        """One-line-per-strategy report for the cycle log. '' if nothing ran."""
        try:
            s = self.summary()
            if not s:
                return ""
            lines = []
            for name, d in sorted(s.items()):
                head = f"[GATES] {name}: {d['passed']}/{d['evaluated']} passed"
                if d["passed"] == d["evaluated"]:
                    lines.append(head)
                    continue
                sole = sorted(
                    d["sole_blocker"].items(), key=lambda kv: -kv[1]
                )[:3]
                top = sorted(d["blocked_by"].items(), key=lambda kv: -kv[1])[:4]
                bits = ", ".join(f"{k}={v}" for k, v in top)
                line = f"{head} | blocked_by: {bits}"
                if sole:
                    line += " | ONLY blocker: " + ", ".join(
                        f"{k}={v}" for k, v in sole
                    )
                lines.append(line)
            return "\n".join(lines)
        except Exception:
            return ""

    def reset(self):
        with self._lock:
            self._evaluated.clear()
            self._passed.clear()
            self._blocked.clear()
            self._sole.clear()

    def roll(self):
        """Snapshot the finished cycle into last_summary, then reset.

        Counts are per-cycle (a cumulative total would hide a gate that only
        started blocking today), but /api/health still needs something to show
        between cycles — that is what last_summary holds.
        """
        try:
            snap = self.summary()
            self.last_summary = snap
            self.reset()
            return snap
        except Exception:
            return {}


# Process-wide counter the daemon writes to and /api/health can read.
GATES = GateCounter()
