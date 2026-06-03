"""
Experiment Registry
Immutable tracking of research hypotheses, parameters, and results.
Every strategy begins here before advancing through the lifecycle.
"""

import os
import sys
import sqlite3
import uuid
import json
import datetime
import logging

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, BASE)

DB_PATH = os.path.join(BASE, "data", "experiments.db")
logger = logging.getLogger(__name__)


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS experiments (
            experiment_id TEXT PRIMARY KEY,
            name TEXT, hypothesis TEXT,
            parameters TEXT, status TEXT DEFAULT 'RESEARCH',
            created_at TEXT, updated_at TEXT,
            clv_avg REAL, roi REAL, sharpe REAL,
            notes TEXT
        )
    """
    )
    conn.commit()
    conn.close()


def register(name, hypothesis, parameters=None):
    """Register a new experiment. Returns experiment_id."""
    init_db()
    exp_id = str(uuid.uuid4())[:8].upper()
    now = datetime.datetime.now(datetime.UTC).isoformat()
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        INSERT INTO experiments (experiment_id, name, hypothesis, parameters, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """,
        (exp_id, name, hypothesis, json.dumps(parameters or {}), now, now),
    )
    conn.commit()
    conn.close()
    logger.info(f"Experiment registered: {exp_id} — {name}")
    return exp_id


def update_results(
    experiment_id, clv_avg=None, roi=None, sharpe=None, status=None, notes=None
):
    """Update experiment results after validation."""
    init_db()
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        UPDATE experiments SET
            clv_avg=COALESCE(?, clv_avg),
            roi=COALESCE(?, roi),
            sharpe=COALESCE(?, sharpe),
            status=COALESCE(?, status),
            notes=COALESCE(?, notes),
            updated_at=?
        WHERE experiment_id=?
    """,
        (
            clv_avg,
            roi,
            sharpe,
            status,
            notes,
            datetime.datetime.now(datetime.UTC).isoformat(),
            experiment_id,
        ),
    )
    conn.commit()
    conn.close()


def list_experiments():
    init_db()
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT experiment_id, name, status, clv_avg, roi FROM experiments ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    return [
        {"id": r[0], "name": r[1], "status": r[2], "clv_avg": r[3], "roi": r[4]}
        for r in rows
    ]


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    eid = register(
        "Market-Implied EV",
        "Vig-free fair probs beat flat Poisson priors",
        {"kelly_frac": 0.25},
    )
    update_results(eid, clv_avg=0.031, roi=0.08, sharpe=1.6, status="SHADOW")
    print("Experiments:", list_experiments())
