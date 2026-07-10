"""Arena real-money safety-gate invariants (src/arena_betting.py).

- _arena_live() must be False for env values '0', '11' (the documented .env
  typo), unset-with-no-.env, and any non-'1' string; True only for exactly '1'.
- place_order() must refuse (status 0, error 'blocked') whenever the gate is
  down, WITHOUT any network call — requests.post/get are patched to raise.

These tests never arm the gate against the real API: the only 'live' checks
are pure reads of _arena_live(), and place_order is only ever called with the
gate DOWN.
"""

import pytest

from src import arena_betting as ab


def _boom(*args, **kwargs):
    raise AssertionError("network call attempted from a unit test")


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    monkeypatch.setattr(ab.requests, "post", _boom)
    monkeypatch.setattr(ab.requests, "get", _boom)


# ---------------------------------------------------------------------------
# _arena_live() — env var forms
# ---------------------------------------------------------------------------

class TestArenaLiveEnv:
    def test_zero_is_not_live(self, monkeypatch):
        monkeypatch.setenv("DEEPFIELD_ARENA_LIVE", "0")
        assert ab._arena_live() is False

    def test_eleven_typo_is_not_live(self, monkeypatch):
        """Regression: the real .env once contained '11' — a typo, but it must
        read as NOT live ('1' exactly, no substring/prefix matching)."""
        monkeypatch.setenv("DEEPFIELD_ARENA_LIVE", "11")
        assert ab._arena_live() is False

    def test_one_is_live(self, monkeypatch):
        monkeypatch.setenv("DEEPFIELD_ARENA_LIVE", "1")
        assert ab._arena_live() is True

    def test_one_with_whitespace_is_live(self, monkeypatch):
        monkeypatch.setenv("DEEPFIELD_ARENA_LIVE", " 1 ")
        assert ab._arena_live() is True

    @pytest.mark.parametrize("v", ["", "true", "True", "yes", "on", "01", "1.0"])
    def test_other_values_are_not_live(self, monkeypatch, v):
        monkeypatch.setenv("DEEPFIELD_ARENA_LIVE", v)
        assert ab._arena_live() is False


# ---------------------------------------------------------------------------
# _arena_live() — .env file fallback (env var unset)
# ---------------------------------------------------------------------------

def _fake_module_location(monkeypatch, tmp_path):
    """Point the module's .env fallback path at tmp_path/.env."""
    (tmp_path / "src").mkdir(exist_ok=True)
    monkeypatch.setattr(ab, "__file__", str(tmp_path / "src" / "arena_betting.py"))
    return tmp_path / ".env"


class TestArenaLiveDotEnvFallback:
    def test_unset_env_and_missing_dotenv_is_not_live(self, monkeypatch, tmp_path):
        monkeypatch.delenv("DEEPFIELD_ARENA_LIVE", raising=False)
        _fake_module_location(monkeypatch, tmp_path)  # no .env written
        assert ab._arena_live() is False

    def test_dotenv_value_one_is_live(self, monkeypatch, tmp_path):
        monkeypatch.delenv("DEEPFIELD_ARENA_LIVE", raising=False)
        env = _fake_module_location(monkeypatch, tmp_path)
        env.write_text("OTHER=x\nDEEPFIELD_ARENA_LIVE=1\n", encoding="utf-8")
        assert ab._arena_live() is True

    def test_dotenv_typo_eleven_is_not_live(self, monkeypatch, tmp_path):
        """The exact 2026-07 incident: .env said DEEPFIELD_ARENA_LIVE=11."""
        monkeypatch.delenv("DEEPFIELD_ARENA_LIVE", raising=False)
        env = _fake_module_location(monkeypatch, tmp_path)
        env.write_text("DEEPFIELD_ARENA_LIVE=11\n", encoding="utf-8")
        assert ab._arena_live() is False

    def test_env_var_wins_over_dotenv(self, monkeypatch, tmp_path):
        env = _fake_module_location(monkeypatch, tmp_path)
        env.write_text("DEEPFIELD_ARENA_LIVE=1\n", encoding="utf-8")
        monkeypatch.setenv("DEEPFIELD_ARENA_LIVE", "0")
        assert ab._arena_live() is False


# ---------------------------------------------------------------------------
# place_order() — refuses without the live gate, no network ever
# ---------------------------------------------------------------------------

class TestPlaceOrderGate:
    @pytest.fixture(autouse=True)
    def ap2_off(self, monkeypatch):
        # AP2 pre-flight is a separate audit layer; keep it out of gate tests.
        monkeypatch.setattr(ab, "_AP2", False, raising=False)

    def _assert_blocked(self, status, body):
        assert status == 0
        assert body["error"] == "blocked"
        assert "DEEPFIELD_ARENA_LIVE" in body["reason"]

    def test_place_order_blocked_with_env_zero(self, monkeypatch):
        monkeypatch.setenv("DEEPFIELD_ARENA_LIVE", "0")
        status, body = ab.place_order("19606961", "COL", 5.0, 0.5)
        self._assert_blocked(status, body)

    def test_place_order_blocked_with_typo_eleven(self, monkeypatch):
        monkeypatch.setenv("DEEPFIELD_ARENA_LIVE", "11")
        status, body = ab.place_order("19606961", "COL", 5.0, 0.5)
        self._assert_blocked(status, body)

    def test_place_order_blocked_when_unset_and_no_dotenv(self, monkeypatch, tmp_path):
        monkeypatch.delenv("DEEPFIELD_ARENA_LIVE", raising=False)
        _fake_module_location(monkeypatch, tmp_path)
        status, body = ab.place_order("19606961", "COL", 5.0, 0.5)
        self._assert_blocked(status, body)

    def test_blocked_place_order_makes_no_network_call(self, monkeypatch):
        """The autouse no_network fixture raises on any requests call — reaching
        this assert proves the blocked path never touched the wire."""
        monkeypatch.setenv("DEEPFIELD_ARENA_LIVE", "0")
        status, _ = ab.place_order("19606961", "GHA", 1.0, 0.9)
        assert status == 0
