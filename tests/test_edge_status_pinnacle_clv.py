"""edge_status.py must grade on the Pinnacle CLV the settler actually writes.

The gate's whole job is "did we beat the sharp close?", but it read the
`clv_sharp` column, which no code path ever populates (every writer inserts
None). Settlement records the sharp-close CLV in `pinnacle_clv` instead, so the
gate saw 0 graded bets for every strategy and could only ever print WAIT.

These tests pin the gate to `pinnacle_clv`, and keep the Betarabia self-CLV
(`clv`) out of the verdict.
"""

import importlib
import sqlite3

import pytest

es = importlib.import_module("tools.edge_status")

PLACED_AT = "2026-08-01T12:00:00"


@pytest.fixture
def bet_db(tmp_path, monkeypatch):
    path = str(tmp_path / "bet_log.db")
    con = sqlite3.connect(path)
    con.execute(
        "CREATE TABLE bet_log (bet_source TEXT, market_type TEXT, result TEXT, "
        "stake REAL, pnl REAL, clv REAL, clv_sharp REAL, pinnacle_clv REAL, "
        "placed_at TEXT)"
    )
    con.commit()
    con.close()
    monkeypatch.setattr(es, "DB", path)
    return path


def _insert(path, rows):
    con = sqlite3.connect(path)
    con.executemany(
        "INSERT INTO bet_log VALUES (?,?,?,?,?,?,?,?,?)",
        [
            ("STEAM", "1X2", res, 10.0, pnl, clv, None, pclv, PLACED_AT)
            for res, pnl, clv, pclv in rows
        ],
    )
    con.commit()
    con.close()


def _steam_block(out):
    """The STEAM strategy's report block, starting at its verdict tag."""
    return next(b for b in out.split("\n[") if "Steam / line-movement 1X2" in b)


def test_pinnacle_clv_is_counted_as_sharp_clv(bet_db, capsys):
    n = es.MIN_SETTLED_WITH_CLV + 20
    _insert(
        bet_db,
        [("W" if i % 2 else "L", 5.0, None, 0.04 if i % 2 else 0.06) for i in range(n)],
    )
    es.main()
    block = _steam_block(capsys.readouterr().out)
    assert f"with SHARP CLV ...... {n}" in block
    assert block.startswith("GO]")


def test_negative_pinnacle_clv_is_no_go(bet_db, capsys):
    n = es.MIN_SETTLED_WITH_CLV + 20
    _insert(
        bet_db,
        [("W" if i % 2 else "L", 5.0, None, -0.04 if i % 2 else -0.06) for i in range(n)],
    )
    es.main()
    assert _steam_block(capsys.readouterr().out).startswith("NO-GO]")


def test_self_clv_alone_never_grades(bet_db, capsys):
    """Betarabia self-CLV is a diagnostic; it must not stand in for the sharp close."""
    n = es.MIN_SETTLED_WITH_CLV + 20
    _insert(bet_db, [("W", 5.0, 0.05, None) for _ in range(n)])
    es.main()
    block = _steam_block(capsys.readouterr().out)
    assert "with SHARP CLV ...... 0" in block
    assert block.startswith("WAIT]")
