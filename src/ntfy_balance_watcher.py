"""ntfy_balance_watcher.py — listens for the user's balance replies on ntfy.

The user maintains their REAL betting balance by replying to the DeepField
ntfy topic from their phone with a bare number ("100" = $100, also "$100",
"100$", "balance 100"). This watcher polls the topic, ignores DeepField's
own outgoing pushes (they always carry a Title header; plain phone replies
don't), saves the number via src.user_bankroll, and confirms back with a
push so the user knows it registered.

Dedup/restart safety: processed message ids + the last-seen timestamp are
persisted in the user_bankroll store file's sibling state, so a daemon
restart doesn't re-apply an old "100" over a since-deducted balance.

Started as a daemon thread by live_predictions_daemon.run_daemon().
"""

import json
import os
import re
import threading
import time

from src import user_bankroll

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_FILE = os.path.join(BASE, "data", "ntfy_watcher_state.json")

POLL_INTERVAL_SEC = 30
MAX_PLAUSIBLE_BALANCE = 1_000_000.0

# Bare number, optionally $-prefixed/suffixed, optionally "balance"-prefixed.
_BALANCE_RE = re.compile(
    r"^\s*(?:balance\s+)?\$?(\d+(?:\.\d+)?)\s*\$?\s*$", re.IGNORECASE
)


def _read_topic() -> str | None:
    """Resolve NTFY_TOPIC the same resilient way alerting.py does."""
    topic = os.getenv("NTFY_TOPIC")
    if topic:
        return topic.strip()
    try:
        with open(os.path.join(BASE, ".env"), encoding="utf-8") as f:
            for line in f:
                if line.startswith("NTFY_TOPIC="):
                    return line.split("=", 1)[1].strip()
    except OSError:
        pass
    return None


def extract_balance(msg: dict) -> float | None:
    """Parse a single ntfy JSON event into a balance, or None.

    Only untitled messages count (DeepField's own pushes always set a title),
    and only a BARE number / '$100' / 'balance 100' form — free text with an
    incidental number ('won 2 today') is never a balance report.
    """
    if msg.get("title"):
        return None
    text = (msg.get("message") or "").strip()
    if not text:
        return None
    m = _BALANCE_RE.match(text)
    if not m:
        return None
    try:
        value = float(m.group(1))
    except ValueError:
        return None
    if value < 0 or value > MAX_PLAUSIBLE_BALANCE:
        return None
    return value


def _load_state() -> dict:
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save_state(state: dict):
    state["seen_ids"] = (state.get("seen_ids") or [])[-500:]
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f)
    os.replace(tmp, STATE_FILE)


def _send_confirmation(balance: float):
    try:
        from src.services.alerting import NotificationManager

        NotificationManager()._notify(
            f"Balance saved: ${balance:.2f}\n"
            "Every new pick will now be sized from this. "
            "Send a new number anytime to correct it.",
            title="DeepField - Balance received",
            priority="default",
            tags="white_check_mark",
        )
    except Exception as e:
        print(f"[NTFY_WATCHER] confirmation push failed: {e}")


def process_messages(messages: list[dict]) -> int:
    """Apply any balance reports found in `messages`. Returns how many were
    applied. Skips already-seen message ids; when several balance reports
    arrive in one batch, the latest (by time) wins."""
    state = _load_state()
    seen = set(state.get("seen_ids") or [])

    candidates = []
    for msg in messages:
        mid = msg.get("id")
        if not mid or mid in seen:
            continue
        seen.add(mid)
        bal = extract_balance(msg)
        if bal is not None:
            candidates.append((msg.get("time") or 0, bal))

    applied = 0
    if candidates:
        candidates.sort()
        for _, bal in candidates:
            user_bankroll.set_balance(bal, source="user", note="ntfy reply")
            applied += 1
        _send_confirmation(candidates[-1][1])

    state["seen_ids"] = list(seen)
    _save_state(state)
    return applied


def _poll_once(topic: str) -> int:
    import requests

    resp = requests.get(
        f"https://ntfy.sh/{topic}/json?poll=1&since=15m", timeout=15
    )
    if resp.status_code != 200:
        return 0
    messages = []
    for line in resp.text.strip().splitlines():
        if not line.strip():
            continue
        try:
            messages.append(json.loads(line))
        except ValueError:
            continue
    return process_messages(messages)


def _watch_loop():
    topic = _read_topic()
    if not topic:
        print("[NTFY_WATCHER] No NTFY_TOPIC configured — watcher disabled.")
        return
    print(f"[NTFY_WATCHER] Watching ntfy topic '{topic}' for balance replies "
          f"(every {POLL_INTERVAL_SEC}s). Reply with a number to set your balance.")
    while True:
        try:
            _poll_once(topic)
        except Exception as e:
            print(f"[NTFY_WATCHER] poll error (will retry): {e}")
        time.sleep(POLL_INTERVAL_SEC)


_started = False


def start_watcher():
    """Start the balance watcher as a daemon thread (idempotent)."""
    global _started
    if _started:
        return
    _started = True
    t = threading.Thread(target=_watch_loop, name="ntfy-balance-watcher", daemon=True)
    t.start()
