"""
daemon_orchestrator.py — DaemonOrchestrator
Thin coordinator that sequences all agents in one cycle.
Zero business logic: reads settings/bankroll, calls agents, returns summary.
"""
from __future__ import annotations

import datetime
import json
import math
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Dict, List

from .arena_monitor import ArenaMonitorAgent
from .bet_gatekeeper import BetGatekeeperAgent
from .fixture_scout import FixtureScoutAgent
from .predictor import PredictorAgent
from .settler import SettlerAgent
from .steam_detector import SteamDetectorAgent

BASE = Path(__file__).parent.parent.parent
DATA = BASE / "data"

_SETTINGS_DEFAULTS: Dict[str, Any] = {
    "ev_threshold": 0.05,
    "min_confidence": 0.50,
    "edge_cap_pct": 10.0,
    "kelly_multiplier": 0.25,
    "max_stake_pct": 0.05,
    "allowed_markets": ["1X2"],
    "exclude_draws": True,
    "steam_min_move_pct": 3.0,
    "require_steam_confirm": False,
    "steam_betting_enabled": True,
    "steam_flat_stake": 25.0,
    "market_blend_weight": 0.5,
}


class DaemonOrchestrator:
    """Coordinates all DeepFieldPro agents in a single prediction cycle."""

    def __init__(self) -> None:
        self.fixture_scout = FixtureScoutAgent()
        self.steam_detector = SteamDetectorAgent()
        self.predictor = PredictorAgent()
        self.bet_gatekeeper = BetGatekeeperAgent()
        self.settler = SettlerAgent()
        self.arena_monitor = ArenaMonitorAgent()

    # ------------------------------------------------------------------
    # Settings / bankroll helpers
    # ------------------------------------------------------------------

    def _load_settings(self) -> Dict[str, Any]:
        settings_path = DATA / "settings.json"
        if not settings_path.exists():
            return dict(_SETTINGS_DEFAULTS)
        try:
            with open(settings_path, "r", encoding="utf-8") as fh:
                loaded = json.load(fh)
            merged = {**_SETTINGS_DEFAULTS, **loaded}
            return merged
        except Exception:
            return dict(_SETTINGS_DEFAULTS)

    def _load_bankroll(self) -> float:
        db_path = DATA / "bankroll.db"
        if not db_path.exists():
            return 1000.0
        try:
            uri = f"file:{db_path}?mode=ro"
            conn = sqlite3.connect(uri, uri=True)
            try:
                row = conn.execute(
                    "SELECT current_balance FROM bankroll ORDER BY date DESC LIMIT 1"
                ).fetchone()
                return float(row[0]) if row else 1000.0
            finally:
                conn.close()
        except Exception:
            return 1000.0

    # ------------------------------------------------------------------
    # Main cycle
    # ------------------------------------------------------------------

    def run_cycle(self) -> Dict[str, Any]:
        ts = datetime.datetime.utcnow().isoformat()
        errors: List[str] = []
        predictions_out: List[dict] = []
        bets_placed: int = 0

        settings = self._load_settings()
        bankroll = self._load_bankroll()
        today = datetime.date.today().isoformat()

        # 1. Discover fixtures
        scout_result = self.fixture_scout._timed_run({"date": today, "limit": 50})
        if not scout_result.success:
            errors.append(f"FixtureScout: {scout_result.error}")
            fixtures = []
        else:
            fixtures = scout_result.data.get("fixtures", [])

        # 2. Per-fixture: SteamDetector + Predictor + BetGatekeeper
        for fixture in fixtures:
            fid = fixture.get("fixture_id")
            home = fixture.get("home_team", "")
            away = fixture.get("away_team", "")

            # Steam detection
            steam_result = self.steam_detector._timed_run(
                {"fixture_id": fid, "market_type": "1X2"}
            )
            steam_moves = {}
            if steam_result.success:
                steam_moves = steam_result.data.get("moves", {})
            else:
                errors.append(f"SteamDetector [{fid}]: {steam_result.error}")

            # Prediction
            pred_result = self.predictor._timed_run(
                {
                    "home": home,
                    "away": away,
                    "league": fixture.get("tournament_name", ""),
                    "fixture_id": fid,
                    "market_odds": {},   # market odds not available at scout stage
                }
            )
            if not pred_result.success:
                errors.append(f"Predictor [{fid}]: {pred_result.error}")
                continue

            preds = pred_result.data

            # Bet gating
            gate_result = self.bet_gatekeeper._timed_run(
                {
                    "match": fixture,
                    "predictions": preds,
                    "market_odds": {},
                    "bankroll": bankroll,
                    "settings": settings,
                }
            )
            gate_data = {}
            if not gate_result.success:
                errors.append(f"BetGatekeeper [{fid}]: {gate_result.error}")
            else:
                gate_data = gate_result.data
                if gate_data.get("recommended"):
                    bets_placed += 1

            # Build kickoff ISO string from scout fields
            kdate = fixture.get("kickoff_date", "")
            ktime = fixture.get("kickoff_time", "")
            if kdate and ktime:
                kickoff = f"{kdate}T{ktime}Z"
            elif kdate:
                kickoff = kdate
            else:
                kickoff = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

            predictions_out.append(
                {
                    "fixture_id": fid,
                    "home_team": home,
                    "away_team": away,
                    "league": fixture.get("tournament_name", ""),
                    "kickoff": kickoff,
                    "status_code": fixture.get("status", "NS"),
                    "predictions": preds,
                    "steam_moves": steam_moves,
                    "gate": gate_data,
                }
            )

        # 3. Settle yesterday's open bets
        yesterday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
        settle_result = self.settler._timed_run({"date": yesterday})
        settled_data = {"settled": 0, "wins": 0, "losses": 0, "voids": 0}
        if settle_result.success:
            settled_data = settle_result.data
        else:
            errors.append(f"Settler: {settle_result.error}")

        # 4. Arena monitor (always dry_run=True from orchestrator)
        arena_result = self.arena_monitor._timed_run(
            {"conf_min": 0.50, "edge_min": 0.02, "dry_run": True}
        )
        arena_data = {"candidates": [], "count": 0, "dry_run": True}
        if arena_result.success:
            arena_data = arena_result.data
        else:
            errors.append(f"ArenaMonitor: {arena_result.error}")

        return {
            "ts": ts,
            "fixtures_count": len(fixtures),
            "predictions": predictions_out,
            "bets_placed": bets_placed,
            "settled": settled_data,
            "arena": arena_data,
            "errors": errors,
        }

    # ------------------------------------------------------------------
    # Dashboard state formatting (A2A → JSON state file)
    # ------------------------------------------------------------------

    @staticmethod
    def _poisson_pmf(lam: float, k: int) -> float:
        return (lam ** k) * math.exp(-lam) / math.factorial(k)

    def _format_for_dashboard(self, cycle_result: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Convert run_cycle() output to todays_dashboard_state.json format."""
        out: List[Dict[str, Any]] = []
        for item in cycle_result.get("predictions", []):
            fid = item["fixture_id"]
            home = item["home_team"]
            away = item["away_team"]
            preds = item.get("predictions", {})
            gate = item.get("gate", {})
            steam = item.get("steam_moves", {})
            league = item.get("league", "")
            kickoff = item.get("kickoff", "")
            status_code = item.get("status_code", "NS")

            hw = preds.get("home_win", 0.33)
            dx = preds.get("draw", 0.33)
            aw = preds.get("away_win", 0.34)
            over25 = preds.get("over25", 0.5)
            btts = preds.get("btts", 0.4)
            lh = preds.get("lambda_h", 1.3)
            la = preds.get("lambda_a", 1.1)

            pred_label = max({"HOME": hw, "DRAW": dx, "AWAY": aw}, key=lambda k: {"HOME": hw, "DRAW": dx, "AWAY": aw}[k])

            score_h = max(0, round(lh))
            score_a = max(0, round(la))
            expected_score = f"{score_h} - {score_a}"

            ev = gate.get("ev", 0.0)
            confidence_raw = min(max(int(5 + ev * 50), 0), 10)

            total_lam = max(lh + la, 0.1)

            def goalscorers(team_name: str, lam: float, team_label: str) -> List[Dict[str, Any]]:
                base_gp = 1 - math.exp(-lam)
                return [
                    {
                        "name": f"{team_name} Gen {i + 1}",
                        "team": team_label,
                        "role": "FW" if i < 2 else "MF",
                        "anytime_goal_prob": round(max(0, base_gp * 100 * (0.35 - i * 0.05)), 1),
                        "first_goal_prob": round(max(0, base_gp * 100 * (0.15 - i * 0.02)), 1),
                        "exp_shots": round(max(0.1, lam * (0.8 - i * 0.1)), 1),
                        "exp_sot": round(max(0.1, lam * (0.35 - i * 0.05)), 1),
                        "yellow_prob": round(max(0.5, 10.0 - i * 0.5), 1),
                        "red_prob": 0.5,
                        "rating": round(max(5.0, 6.0 - i * 0.2), 2),
                    }
                    for i in range(3)
                ]

            over05 = round((1 - self._poisson_pmf(lh + la, 0)) * 100, 1)
            over15 = round((1 - self._poisson_pmf(lh + la, 0) - self._poisson_pmf(lh + la, 1)) * 100, 1)

            corners_h = max(3, round(lh * 2.5))
            corners_a = max(3, round(la * 2.5))
            fouls_h = max(5, min(15, int(7 + (la - lh))))
            fouls_a = max(5, min(15, int(7 + (lh - la))))
            cards_h = max(1, round(la * 0.9))
            cards_a = max(1, round(lh * 0.9))
            poss_h = max(35, min(65, int(lh / total_lam * 100)))

            ev_home = preds.get("ev_home", 0.0)
            ev_draw = preds.get("ev_draw", 0.0)
            ev_away = preds.get("ev_away", 0.0)

            detailed = {
                "home_prob": round(hw * 100, 1),
                "draw_prob": round(dx * 100, 1),
                "away_prob": round(aw * 100, 1),
                "predicted_score": expected_score,
                "confidence": confidence_raw,
                "home_xg": round(lh, 2),
                "away_xg": round(la, 2),
                "over_05": over05,
                "over_15": max(0.0, over15),
                "over_25": round(over25 * 100, 1),
                "over_35": round(max(0, over25 * 100 - 20), 1),
                "under_25": round((1 - over25) * 100, 1),
                "btts_yes": round(btts * 100, 1),
                "possession_home": poss_h,
                "possession_away": 100 - poss_h,
                "fouls_home": fouls_h,
                "fouls_away": fouls_a,
                "offsides_home": round(lh * 0.6, 1),
                "offsides_away": round(la * 0.6, 1),
                "saves_home": max(1, int(la * 2.5)),
                "saves_away": max(1, int(lh * 2.5)),
                "clean_sheet_home": round(math.exp(-la) * 100, 1),
                "clean_sheet_away": round(math.exp(-lh) * 100, 1),
                "corners_total": corners_h + corners_a,
                "corners_home": corners_h,
                "corners_away": corners_a,
                "corners_over_75": 90.0,
                "corners_over_85": 80.0,
                "corners_over_95": 70.0,
                "corners_over_105": 55.0,
                "cards_yellow_home": cards_h,
                "cards_yellow_away": cards_a,
                "cards_yellow_total": cards_h + cards_a,
                "cards_red_total": 0.0,
                "goalscorers": goalscorers(home, lh, "Home") + goalscorers(away, la, "Away"),
                "ev": round(ev * 100, 2),
                "recommendation": f"{gate.get('selection', pred_label)} (A2A)" if gate.get("recommended") else pred_label,
            }

            prediction_obj = {
                "fixture_id": fid,
                "match": f"{home} vs {away}",
                "league": league,
                "kickoff": kickoff,
                "prediction": pred_label,
                "expected_score": expected_score,
                "has_lineup": False,
                "team_impacts": f"Home: {lh:.2f} | Away: {la:.2f}",
                "corners": f"Home: {corners_h} | Away: {corners_a}",
                "fouls": f"Home: {fouls_h} | Away: {fouls_a}",
                "cards": f"Home Yellows: {cards_h} | Away Yellows: {cards_a}",
                "home_players": [
                    {"name": f"{home} Gen {i + 1}", "impact": round(max(0, lh * (0.2 - i * 0.01)), 2)}
                    for i in range(3)
                ],
                "away_players": [
                    {"name": f"{away} Gen {i + 1}", "impact": round(max(0, la * (0.2 - i * 0.01)), 2)}
                    for i in range(3)
                ],
                "detailed_prediction": detailed,
                "markets": {
                    "Match Result": [
                        {"side": "Home", "odds": 0.0, "prob": round(hw * 100, 1), "ev": round(ev_home * 100, 2)},
                        {"side": "Draw", "odds": 0.0, "prob": round(dx * 100, 1), "ev": round(ev_draw * 100, 2)},
                        {"side": "Away", "odds": 0.0, "prob": round(aw * 100, 1), "ev": round(ev_away * 100, 2)},
                    ]
                },
            }

            max_steam = max(steam.values()) if steam else 0.0

            out.append(
                {
                    "fixture_id": fid,
                    "match": f"{home} vs {away}",
                    "league": league,
                    "kickoff": kickoff,
                    "status_code": status_code,
                    "has_lineup": False,
                    "prediction": prediction_obj,
                    "recommended": gate.get("recommended", False),
                    "recommendation": gate.get("selection", ""),
                    "stake": gate.get("stake", 0.0),
                    "ev": round(ev * 100, 2),
                    "steam_move": round(max_steam, 2),
                    "bet_source": "A2A",
                }
            )

        return out

    def write_dashboard_state(self, formatted: List[Dict[str, Any]]) -> None:
        """Write formatted matches to todays_dashboard_state.json atomically."""
        state_path = DATA / "todays_dashboard_state.json"
        tmp_path = state_path.with_suffix(".tmp")
        with open(tmp_path, "w", encoding="utf-8") as fh:
            json.dump(formatted, fh, ensure_ascii=False, indent=2)
        tmp_path.replace(state_path)

    def run_loop(self, interval: int = 300, stop_event: threading.Event | None = None) -> None:
        """Run continuous prediction cycles, writing the dashboard state after each.

        Set DEEPFIELD_USE_AGENTS=1 to start this instead of the legacy daemon.
        interval: seconds between cycles (default 300 = 5 min).
        stop_event: optional threading.Event; loop exits when set.
        """
        import os
        print(f"[A2A] Orchestrator loop started (interval={interval}s)")
        while not (stop_event and stop_event.is_set()):
            try:
                cycle = self.run_cycle()
                formatted = self._format_for_dashboard(cycle)
                self.write_dashboard_state(formatted)
                n = len(formatted)
                errs = len(cycle.get("errors", []))
                print(f"[A2A] Cycle complete — {n} fixtures, {cycle['bets_placed']} bets, {errs} errors")
            except Exception as exc:
                print(f"[A2A] Cycle error: {exc}")
            if stop_event:
                stop_event.wait(timeout=interval)
            else:
                time.sleep(interval)
