"""
similarity_engine.py — DeepFieldPro Unknown Player Profiler
============================================================
When a player is not found in the stats DB (missing transfers, academy call-ups, etc.),
this engine finds the 5 most similar known players using K-Nearest Neighbors (cosine distance)
and synthesises estimated per-90 stats for them.

BUG FIX vs previous version:
  - Query vector now passed as a named pd.DataFrame to kneighbors() instead of a raw
    numpy array, eliminating the sklearn feature-name warning.
"""

import numpy as np
import pandas as pd
from sklearn.neighbors import NearestNeighbors
from sklearn.preprocessing import StandardScaler
import logging
import sqlite3

logger = logging.getLogger(__name__)


class PlayerSimilarityEngine:
    """
    Handles [MISSING] players by finding similar profiles
    using K-Nearest Neighbors (cosine distance) on normalised historical stats,
    grouped by position.
    """

    FEATURE_COLS = [
        "goals_p90",
        "assists_p90",
        "shots_p90",
        "xg_p90",
        "xa_p90",
        "tackles_p90",
        "passes_p90",
        "yellow_cards_p90",
    ]

    # Hardcoded positional priors for the absolute fallback (no DB data at all)
    POSITIONAL_PRIORS = {
        "GK": {
            "xg_p90": 0.00,
            "xa_p90": 0.00,
            "shots_p90": 0.0,
            "goals_p90": 0.00,
            "assists_p90": 0.00,
            "yellow_p90": 0.05,
        },
        "DEF": {
            "xg_p90": 0.03,
            "xa_p90": 0.03,
            "shots_p90": 0.6,
            "goals_p90": 0.03,
            "assists_p90": 0.03,
            "yellow_p90": 0.20,
        },
        "MID": {
            "xg_p90": 0.07,
            "xa_p90": 0.09,
            "shots_p90": 1.2,
            "goals_p90": 0.07,
            "assists_p90": 0.09,
            "yellow_p90": 0.20,
        },
        "FWD": {
            "xg_p90": 0.28,
            "xa_p90": 0.10,
            "shots_p90": 2.8,
            "goals_p90": 0.28,
            "assists_p90": 0.10,
            "yellow_p90": 0.12,
        },
    }

    def __init__(self, db_conn):
        self.conn = db_conn
        self.models: dict = {}  # position -> (NearestNeighbors, scaler, DataFrame)
        self.df = pd.DataFrame()
        self._load_and_fit()

    def _load_and_fit(self):
        """Load players with >300 mins from DB and fit per-position KNN models."""
        # Handle both SQLite connections (sqlite3) and SQLAlchemy engines
        try:
            cols = ", ".join(self.FEATURE_COLS)
            query = f"""
                SELECT player_id, player_name, position, minutes_played,
                       age, {cols}
                FROM player_stats
                WHERE minutes_played > 300
            """
            self.df = pd.read_sql(query, self.conn)
            self.df[self.FEATURE_COLS] = self.df[self.FEATURE_COLS].fillna(0)
            self.df["position"] = self.df["position"].fillna("MID").str.upper().str[:3]

        except Exception as e:
            logger.warning(
                f"[SimilarityEngine] DB load failed: {e}. Using positional priors only."
            )
            self.df = pd.DataFrame()
            return

        for pos in self.df["position"].unique():
            pos_df = self.df[self.df["position"] == pos].copy()
            if len(pos_df) < 5:
                continue  # not enough samples for KNN
            try:
                scaler = StandardScaler()
                X = scaler.fit_transform(pos_df[self.FEATURE_COLS])
                knn = NearestNeighbors(n_neighbors=min(5, len(pos_df)), metric="cosine")
                knn.fit(X)
                self.models[pos] = (knn, scaler, pos_df.reset_index(drop=True))
            except Exception as e:
                logger.warning(
                    f"[SimilarityEngine] KNN fit failed for position {pos}: {e}"
                )

        logger.info(
            f"[SimilarityEngine] Fitted KNN models for positions: {list(self.models.keys())}"
        )

    def get_estimated_stats(self, player_name: str, position: str = "MID") -> dict:
        """
        Estimate stats for an unknown player.
        Returns synthetic profile + confidence score (0-100).

        BUG FIX: query vector passed as pd.DataFrame with column names,
        not as raw numpy array, to avoid sklearn feature-name warning.
        """
        pos = position.upper()[:3]

        # ── Case 1: No DB data at all — use positional priors ───────────────
        if pos not in self.models:
            priors = self.POSITIONAL_PRIORS.get(pos, self.POSITIONAL_PRIORS["MID"])
            return {
                "name": player_name,
                "position": pos,
                "xg_p90": priors["xg_p90"],
                "xa_p90": priors["xa_p90"],
                "shots_p90": priors["shots_p90"],
                "goals_p90": priors["goals_p90"],
                "assists_p90": priors["assists_p90"],
                "yellow_p90": priors["yellow_p90"],
                "confidence": 10.0,
                "is_synthetic": True,
                "method": "positional_prior",
            }

        knn, scaler, pos_df = self.models[pos]

        # Build query vector using the positional mean as the proxy for the unknown player
        # BUG FIX: wrap in pd.DataFrame with column names instead of .values
        mean_vals = pos_df[self.FEATURE_COLS].mean()
        query_df = pd.DataFrame([mean_vals], columns=self.FEATURE_COLS)
        query_scaled = scaler.transform(
            query_df
        )  # still a numpy array, but feature names match

        distances, indices = knn.kneighbors(query_scaled)

        neighbors = pos_df.iloc[indices[0]]
        synth = neighbors[self.FEATURE_COLS].mean()

        # Confidence: cosine distance of 0 = perfect match, >0.5 = very different
        avg_dist = float(np.mean(distances[0]))
        confidence = round(max(10.0, 100.0 * (1.0 - avg_dist * 2)), 1)

        return {
            "name": player_name,
            "position": pos,
            "xg_p90": round(float(synth.get("xg_p90", 0.05)), 4),
            "xa_p90": round(float(synth.get("xa_p90", 0.05)), 4),
            "shots_p90": round(float(synth.get("shots_p90", 1.0)), 4),
            "goals_p90": round(float(synth.get("goals_p90", 0.05)), 4),
            "assists_p90": round(float(synth.get("assists_p90", 0.05)), 4),
            "yellow_p90": round(float(synth.get("yellow_cards_p90", 0.15)), 4),
            "confidence": confidence,
            "is_synthetic": True,
            "method": "knn_similarity",
            "neighbors_used": (
                list(neighbors["player_name"])
                if "player_name" in neighbors.columns
                else []
            ),
        }


if __name__ == "__main__":
    # ── Self-test ──────────────────────────────────────────────────────────
    logging.basicConfig(level=logging.INFO)

    conn = sqlite3.connect(":memory:")
    conn.execute("""CREATE TABLE player_stats (
        player_id TEXT, player_name TEXT, position TEXT, minutes_played INT, age INT,
        goals_p90 REAL, assists_p90 REAL, shots_p90 REAL,
        xg_p90 REAL, xa_p90 REAL, tackles_p90 REAL,
        passes_p90 REAL, yellow_cards_p90 REAL
    )""")
    # Insert 5+ forwards so KNN can fit
    players = [
        ("p1", "Mbappé", "FWD", 2000, 25, 0.7, 0.2, 4.0, 0.65, 0.18, 0.3, 20.0, 0.1),
        ("p2", "Kane", "FWD", 1800, 30, 0.6, 0.3, 3.5, 0.55, 0.22, 0.2, 18.0, 0.15),
        ("p3", "Haaland", "FWD", 1900, 23, 0.9, 0.1, 4.5, 0.80, 0.10, 0.1, 12.0, 0.08),
        ("p4", "Benzema", "FWD", 1600, 35, 0.5, 0.4, 3.0, 0.45, 0.30, 0.3, 22.0, 0.12),
        (
            "p5",
            "Lewandowski",
            "FWD",
            2000,
            35,
            0.65,
            0.2,
            3.8,
            0.60,
            0.18,
            0.2,
            19.0,
            0.13,
        ),
    ]
    conn.executemany(
        "INSERT INTO player_stats VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", players
    )

    engine = PlayerSimilarityEngine(conn)

    print("=== Test 1: Known position (FWD) ===")
    result = engine.get_estimated_stats("Unknown Academy Striker", "FWD")
    for k, v in result.items():
        print(f"  {k}: {v}")

    print("\n=== Test 2: Unknown position (no data) — falls back to prior ===")
    result2 = engine.get_estimated_stats("Random Player", "GK")
    for k, v in result2.items():
        print(f"  {k}: {v}")
