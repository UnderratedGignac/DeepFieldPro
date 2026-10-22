"""Tests for src/ntfy_balance_watcher.py — parses the user's ntfy replies.

The user maintains their real balance by replying to the DeepField ntfy topic
with a bare number. The watcher polls the topic, ignores DeepField's own
outgoing messages (they always carry a Title header; plain phone replies
don't), extracts the number, and saves it via src.user_bankroll.

Only the pure pieces are tested here (extract_balance, process_messages);
the polling thread is a thin loop around them.
"""

import pytest

import src.ntfy_balance_watcher as w
import src.user_bankroll as ub


class TestExtractBalance:
    def test_bare_integer(self):
        assert w.extract_balance({"message": "100"}) == 100.0

    def test_bare_decimal(self):
        assert w.extract_balance({"message": "87.5"}) == 87.5

    def test_dollar_prefix_and_suffix(self):
        assert w.extract_balance({"message": "$100"}) == 100.0
        assert w.extract_balance({"message": "100$"}) == 100.0

    def test_surrounding_whitespace_ok(self):
        assert w.extract_balance({"message": "  250  "}) == 250.0

    def test_balance_keyword_form(self):
        assert w.extract_balance({"message": "balance 150"}) == 150.0

    def test_own_titled_message_ignored(self):
        """DeepField's own pushes always carry a title — never parse them,
        even when the body contains numbers (stake suggestions do)."""
        msg = {"title": "DeepField - New Pick", "message": "Suggested stake: $12.50"}
        assert w.extract_balance(msg) is None

    def test_free_text_with_incidental_number_ignored(self):
        """'won 2 today' must NOT be interpreted as balance=$2 — only a
        bare number (or 'balance N') counts as a balance report."""
        assert w.extract_balance({"message": "won 2 today"}) is None

    def test_non_message_events_ignored(self):
        assert w.extract_balance({"event": "open"}) is None
        assert w.extract_balance({"message": ""}) is None

    def test_negative_and_absurd_values_rejected(self):
        assert w.extract_balance({"message": "-50"}) is None
        assert w.extract_balance({"message": "99999999"}) is None


class TestProcessMessages:
    @pytest.fixture(autouse=True)
    def store(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ub, "STORE_FILE", str(tmp_path / "user_bankroll.json"))
        monkeypatch.setattr(w, "STATE_FILE", str(tmp_path / "ntfy_watcher_state.json"))
        # Confirmation pushes must not hit the network in tests.
        self.sent = []
        monkeypatch.setattr(w, "_send_confirmation", lambda bal: self.sent.append(bal))

    def test_balance_message_saves_and_confirms(self):
        n = w.process_messages([{"id": "m1", "message": "100", "time": 1}])
        assert n == 1
        assert ub.get_balance() == 100.0
        assert self.sent == [100.0]

    def test_latest_of_multiple_wins(self):
        """If the user sends 100 then corrects to 120 within one poll window,
        the LAST message is the balance that sticks."""
        w.process_messages([
            {"id": "m1", "message": "100", "time": 1},
            {"id": "m2", "message": "120", "time": 2},
        ])
        assert ub.get_balance() == 120.0

    def test_seen_ids_not_reprocessed(self):
        w.process_messages([{"id": "m1", "message": "100", "time": 1}])
        ub.deduct(10)  # tracked balance now 90
        # Same message id delivered again by a later poll — must not reset to 100.
        n = w.process_messages([{"id": "m1", "message": "100", "time": 1}])
        assert n == 0
        assert ub.get_balance() == 90.0

    def test_non_balance_messages_counted_zero(self):
        n = w.process_messages([
            {"id": "m3", "title": "DeepField - New Pick", "message": "stake $5", "time": 3},
            {"id": "m4", "message": "great job", "time": 4},
        ])
        assert n == 0
        assert ub.get_balance() is None
