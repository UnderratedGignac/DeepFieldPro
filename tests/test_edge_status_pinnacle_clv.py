"""edge_status.py must grade on Pinnacle's FAIR (margin-free) closing price.

The gate first read `clv_sharp`, which no code path populates, so it could only
print WAIT. It then read `pinnacle_clv` = entry / raw Pinnacle close - 1, but
the raw close carries Pinnacle's margin and flatters every bet (VALUE_ONLY on
2026-10-21: +9.1% raw vs +1.4% fair). It now grades `pinnacle_fair_clv` =
entry * de-vigged closing probability - 1.

These tests pin the gate to `pinnacle_fair_clv`, and keep both the raw
`pinnacle_clv` and the Betarabia self-CLV (`clv`) out of the verdict.
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
        "pinnacle_fair_clv REAL, placed_at TEXT)"
    )
    con.commit()
    con.close()
    monkeypatch.setattr(es, "DB", path)
    return path


def _insert(path, rows):
    """rows: (result, pnl, self_clv, raw_pinnacle_clv, fair_pinnacle_clv)."""
    con = sqlite3.connect(path)
    con.executemany(
        "INSERT INTO bet_log VALUES (?,?,?,?,?,?,?,?,?,?)",
        [
            ("STEAM", "1X2", res, 10.0, pnl, clv, None, raw, fair, PLACED_AT)
            for res, pnl, clv, raw, fair in rows
        ],
    )
    con.commit()
    con.close()


def _steam_block(out):
    """The STEAM strategy's report block, starting at its verdict tag."""
    return next(b for b in out.split("\n[") if "Steam / line-movement 1X2" in b)


N = es.MIN_SETTLED_WITH_CLV + 20


def test_fair_clv_is_counted_as_sharp_clv(bet_db, capsys):
    _insert(bet_db, [("W" if i % 2 else "L", 5.0, None, 0.12, 0.04 if i % 2 else 0.06) for i in range(N)])
    es.main()
    block = _steam_block(capsys.readouterr().out)
    assert f"with SHARP CLV ...... {N}" in block
    assert block.startswith("GO]")


def test_negative_fair_clv_is_no_go_even_when_the_raw_close_looks_positive(bet_db, capsys):
    _insert(bet_db, [("W" if i % 2 else "L", 5.0, None, 0.05, -0.04 if i % 2 else -0.06) for i in range(N)])
    es.main()
    assert _steam_block(capsys.readouterr().out).startswith("NO-GO]")


def test_raw_pinnacle_clv_alone_never_grades(bet_db, capsys):
    """The raw close carries Pinnacle's margin; it must not stand in for the fair close."""
    _insert(bet_db, [("W", 5.0, None, 0.10, None) for _ in range(N)])
    es.main()
    block = _steam_block(capsys.readouterr().out)
    assert "with SHARP CLV ...... 0" in block
    assert block.startswith("WAIT]")


def test_self_clv_alone_never_grades(bet_db, capsys):
    """Betarabia self-CLV is a diagnostic; it must not stand in for the sharp close."""
    _insert(bet_db, [("W", 5.0, 0.05, None, None) for _ in range(N)])
    es.main()
    block = _steam_block(capsys.readouterr().out)
    assert "with SHARP CLV ...... 0" in block
    assert block.startswith("WAIT]")
