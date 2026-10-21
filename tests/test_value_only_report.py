"""Daily VALUE_ONLY report: is the strategy beating Pinnacle's closing price?

Realized P&L on a few dozen bets is noise; closing-line value (pinnacle_clv,
recorded at settlement) is the leading indicator. The report reads only
VALUE_ONLY rows, splits by market and by book, and gives the same verdict as
tools/edge_status.py (>= 100 bets with CLV, CLV > 0 at the 95% lower bound).
It is pushed once per UTC day and saved under reports/.
"""

import datetime
import importlib
import sqlite3

import pytest

rep = importlib.import_module("tools.value_only_report")
edge = importlib.import_module("tools.edge_status")


@pytest.fixture
def db(tmp_path):
    path = str(tmp_path / "bet_log.db")
    con = sqlite3.connect(path)
    con.execute(
        "CREATE TABLE bet_log (bet_id TEXT, bet_source TEXT, market_type TEXT, side TEXT, entry_odds REAL, "
        "stake REAL, result TEXT, pnl REAL, pinnacle_clv REAL, book TEXT, placed_at TEXT)"
    )
    rows = [
        ("1", "VALUE_ONLY", "1X2", "Away (2)", 3.10, 1.0, "W", 2.10, 0.05, "Kambi", "2026-10-21T16:00:00"),
        ("2", "VALUE_ONLY", "1X2", "Draw (X)", 5.00, 1.0, "L", -1.0, 0.03, "Kambi", "2026-10-21T16:00:00"),
        ("3", "VALUE_ONLY", "Over/Under 2.5", "Under 2.5", 3.05, 1.0, "L", -1.0, -0.01, "Betarabia", "2026-10-21T16:00:00"),
        ("4", "VALUE_ONLY", "BTTS", "No", 2.10, 1.0, "OPEN", 0.0, None, "Kambi", "2026-10-21T17:00:00"),
        ("5", "VALUE_ONLY", "1X2", "Home (1)", 2.00, 1.0, "VOID", 0.0, None, "Kambi", "2026-10-21T17:00:00"),
        ("6", "MODEL_VALUE_ALIGN", "Over/Under 2.5", "Under 2.5", 3.35, 5.0, "W", 11.75, 0.20, None, "2026-10-21T13:00:00"),
    ]
    con.executemany("INSERT INTO bet_log VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows)
    con.commit()
    con.close()
    return path


def test_report_counts_value_only_bets_only(db):
    r = rep.build_report(db)
    assert (r["placed"], r["settled"], r["open"], r["void"]) == (5, 3, 1, 1)
    assert r["pnl"] == pytest.approx(0.10)
    assert r["roi"] == pytest.approx(0.10 / 3)


def test_clv_and_the_split_by_market_and_book(db):
    r = rep.build_report(db)
    assert r["clv_n"] == 3
    assert r["clv_mean"] == pytest.approx((0.05 + 0.03 - 0.01) / 3)
    assert r["beat_close"] == pytest.approx(2 / 3)
    assert r["by_market"]["1X2"]["clv_n"] == 2
    assert r["by_book"]["Betarabia"]["clv_mean"] == pytest.approx(-0.01)


def test_verdict_is_the_same_rule_as_the_edge_gate(db):
    r = rep.build_report(db)
    assert r["verdict"] == edge._verdict(r["clv_n"], r["clv_mean"], r["clv_lo"])[0] == "WAIT"
    text = rep.format_report(r)
    assert "VALUE_ONLY" in text and "WAIT" in text and "Kambi" in text


def test_daily_push_fires_once_per_day_after_the_hour(db, tmp_path):
    sent = []
    state = str(tmp_path / "state.json")
    reports = tmp_path / "reports"

    def at(h):
        return datetime.datetime(2026, 10, 22, h, 5, tzinfo=datetime.timezone.utc)

    kw = dict(db_path=db, state_path=state, reports_dir=str(reports), send=lambda t, b: sent.append(b))
    rep.maybe_send_daily_report(now=at(rep.SEND_HOUR_UTC - 1), **kw)
    assert sent == []
    rep.maybe_send_daily_report(now=at(rep.SEND_HOUR_UTC), **kw)
    rep.maybe_send_daily_report(now=at(rep.SEND_HOUR_UTC + 3), **kw)
    assert len(sent) == 1 and "VALUE_ONLY" in sent[0]
    assert (reports / "value_only_2026-10-22.txt").exists()
