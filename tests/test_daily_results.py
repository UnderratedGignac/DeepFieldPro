"""End-of-day ntfy push: what was won, what was lost, and the net.

Matches finish late (Champions League ~21:00 UTC, Liga MX after midnight), so
the push covers every bet SETTLED since the previous push (settle_checked_at,
stamped by settlement), not bets placed today: each result appears in exactly
one report. Voids are counted but are neither a win nor a loss. Paper only.
"""

import datetime
import importlib
import json
import sqlite3

import pytest

dr = importlib.import_module("tools.daily_results")

UTC = datetime.timezone.utc
T0 = datetime.datetime(2026, 10, 21, 21, 0, tzinfo=UTC)  # previous push


def _ts(hours_after_t0):
    return (T0 + datetime.timedelta(hours=hours_after_t0)).isoformat()


@pytest.fixture
def db(tmp_path):
    path = str(tmp_path / "bet_log.db")
    con = sqlite3.connect(path)
    con.execute(
        "CREATE TABLE bet_log (bet_id TEXT, match_id TEXT, market_type TEXT, side TEXT, entry_odds REAL, "
        "stake REAL, result TEXT, pnl REAL, bet_source TEXT, book TEXT, settle_checked_at TEXT)"
    )
    rows = [
        ("1", "Sporting Lisbon vs LASK Linz", "1X2", "Away (2)", 10.5, 0.22, "W", 2.09, "VALUE_ONLY", "Kambi", _ts(2)),
        ("2", "Club Brugge vs Lens", "Over/Under 2.5", "Under 2.5", 3.3, 5.0, "L", -5.0, "MODEL_VALUE_ALIGN", "Kambi", _ts(3)),
        ("3", "Lille vs Galatasaray", "Over/Under 2.5", "Under 2.5", 2.3, 1.0, "W", 1.30, "VALUE_ONLY", "Kambi", _ts(4)),
        ("4", "Harju vs Flora", "BTTS", "No", 2.75, 0.33, "L", -0.33, "VALUE_ONLY", "Kambi", _ts(5)),
        ("5", "Old Match", "1X2", "Home (1)", 2.0, 5.0, "W", 5.0, "VALUE_ONLY", "Kambi", _ts(-2)),  # previous report
        ("6", "Pachuca U21 vs Cruz Azul U21", "1X2", "Draw (X)", 3.8, 1.0, "VOID", 0.0, "VALUE_ONLY", "Betarabia", _ts(6)),
        ("7", "Toluca vs Tijuana", "1X2", "Draw (X)", 5.0, 1.0, "OPEN", 0.0, "VALUE_ONLY", "Kambi", None),
    ]
    con.executemany("INSERT INTO bet_log VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows)
    con.commit()
    con.close()
    return path


def test_window_is_settled_since_the_last_push(db):
    r = dr.build_results(db, since=T0, until=T0 + datetime.timedelta(hours=24))
    assert [b["match_id"] for b in r["won"]] == ["Sporting Lisbon vs LASK Linz", "Lille vs Galatasaray"]
    assert [b["match_id"] for b in r["lost"]] == ["Club Brugge vs Lens", "Harju vs Flora"]
    assert r["void"] == 1 and r["open"] == 1


def test_earned_lost_and_net(db):
    r = dr.build_results(db, since=T0, until=T0 + datetime.timedelta(hours=24))
    assert r["earned"] == pytest.approx(2.09 + 1.30)
    assert r["lost_amount"] == pytest.approx(5.0 + 0.33)
    assert r["net"] == pytest.approx(3.39 - 5.33)
    assert r["by_strategy"]["VALUE_ONLY"] == {"won": 2, "lost": 1, "net": pytest.approx(3.06)}


def test_message_shows_each_winner_and_loser(db):
    r = dr.build_results(db, since=T0, until=T0 + datetime.timedelta(hours=24))
    text = dr.format_results(r)
    assert "Sporting Lisbon vs LASK Linz" in text and "Club Brugge vs Lens" in text
    assert "Kambi" in text and "VALUE_ONLY" in text
    assert "-1.94" in text  # net


def test_long_lists_are_trimmed_for_ntfy(db):
    r = dr.build_results(db, since=T0, until=T0 + datetime.timedelta(hours=24))
    r["won"] = r["won"] * 20
    text = dr.format_results(r)
    assert "more" in text and len(text.encode("utf-8")) < 4000


def test_pushes_once_per_day_and_never_repeats_a_bet(db, tmp_path):
    state, sent = str(tmp_path / "state.json"), []
    with open(state, "w") as f:
        json.dump({"sent_date": "2026-10-21", "last_until": T0.isoformat()}, f)
    kw = dict(db_path=db, state_path=state, send=lambda title, body: sent.append(body))

    day2 = datetime.datetime(2026, 10, 22, dr.RESULTS_HOUR_UTC, 1, tzinfo=UTC)
    assert dr.maybe_send_daily_results(now=day2 - datetime.timedelta(hours=1), **kw) is False
    assert dr.maybe_send_daily_results(now=day2, **kw) is True
    assert dr.maybe_send_daily_results(now=day2 + datetime.timedelta(hours=2), **kw) is False
    assert len(sent) == 1 and "Old Match" not in sent[0] and "Sporting Lisbon" in sent[0]
    assert json.load(open(state))["last_until"] == day2.isoformat()
