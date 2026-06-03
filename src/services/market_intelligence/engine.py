# mypy: ignore-errors
"""
Market Intelligence Engine

Generates advanced market microstructure features:
- Line velocity and acceleration
- Reverse line movement
- Steam moves
- Cross-book disagreement
- Sharp consensus signals
- Market pressure indicators
- Liquidity imbalance
- Volatility regimes
"""

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from collections import defaultdict
import statistics
import logging

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from database.models import OddsTick

logger = logging.getLogger(__name__)


@dataclass
class LineMetrics:
    """Metrics for a single line/outcome."""

    market_id: str
    outcome: str
    current_odds: Decimal
    odds_1h_ago: Optional[Decimal]
    odds_6h_ago: Optional[Decimal]
    odds_24h_ago: Optional[Decimal]
    opening_odds: Optional[Decimal]

    # Velocity (change per hour)
    velocity_1h: float = 0.0
    velocity_6h: float = 0.0
    velocity_24h: float = 0.0

    # Acceleration
    acceleration: float = 0.0

    # Movement direction
    direction: str = "neutral"  # up, down, neutral
    movement_pct: float = 0.0

    # Volatility
    volatility: float = 0.0
    tick_count: int = 0


@dataclass
class SteamMove:
    """Represents a significant steam move."""

    market_id: str
    outcome: str
    sportsbook_id: str
    start_time: datetime
    end_time: datetime
    start_odds: Decimal
    end_odds: Decimal
    change_pct: float
    duration_seconds: float
    velocity: float
    severity: str  # minor, moderate, major, extreme


@dataclass
class CrossBookDisagreement:
    """Measures disagreement across sportsbooks."""

    market_id: str
    outcome: str
    timestamp: datetime
    best_odds: Decimal
    worst_odds: Decimal
    avg_odds: Decimal
    median_odds: Decimal
    spread_pct: float
    std_dev: float
    arbitrage_opportunity: bool
    arb_profit_pct: float


@dataclass
class MarketPressure:
    """Market pressure indicator."""

    market_id: str
    outcome: str
    pressure_score: float  # -1.0 to 1.0 (negative = money on opposite side)
    confidence: float
    signal_strength: str  # weak, moderate, strong
    sharp_side: Optional[str]  # which side sharps are on
    public_side: Optional[str]  # which side public is on
    reverse_line_move: bool


class MarketIntelligenceEngine:
    """
    Advanced market microstructure analysis engine.

    Analyzes odds movements to detect:
    - Sharp money patterns
    - Steam moves
    - Market inefficiencies
    - Consensus signals
    """

    def __init__(self, db_session: AsyncSession):
        self.db_session = db_session
        self._line_metrics_cache: Dict[str, LineMetrics] = {}
        self._steam_moves: List[SteamMove] = []
        self._pressure_indicators: Dict[str, MarketPressure] = {}

    async def analyze_market(
        self, market_id: str, lookback_hours: int = 24
    ) -> Dict[str, Any]:
        """
        Perform comprehensive market analysis.

        Returns complete market intelligence report.
        """
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(hours=lookback_hours)

        # Get all odds ticks for this market
        ticks = await self._get_market_ticks(market_id, start_time, end_time)

        if not ticks:
            return {"error": "No data available"}

        # Group by outcome and sportsbook
        by_outcome = defaultdict(list)
        for tick in ticks:
            by_outcome[tick.outcome].append(tick)

        analysis = {
            "market_id": market_id,
            "analysis_time": end_time.isoformat(),
            "lookback_hours": lookback_hours,
            "outcomes": {},
            "steam_moves": [],
            "cross_book_disagreement": [],
            "pressure_indicators": [],
        }

        # Analyze each outcome
        for outcome, outcome_ticks in by_outcome.items():
            # Line metrics
            metrics = await self._calculate_line_metrics(
                market_id, outcome, outcome_ticks
            )
            analysis["outcomes"][outcome] = self._metrics_to_dict(metrics)

            # Detect steam moves
            steam_moves = await self._detect_steam_moves(
                market_id, outcome, outcome_ticks
            )
            for move in steam_moves:
                analysis["steam_moves"].append(self._steam_to_dict(move))

            # Cross-book disagreement
            disagreement = await self._calculate_cross_book_disagreement(
                market_id, outcome, outcome_ticks
            )
            if disagreement:
                analysis["cross_book_disagreement"].append(
                    self._disagreement_to_dict(disagreement)
                )

            # Market pressure
            pressure = await self._calculate_market_pressure(
                market_id, outcome, outcome_ticks
            )
            if pressure:
                analysis["pressure_indicators"].append(self._pressure_to_dict(pressure))

        # Add summary signals
        analysis["summary"] = self._generate_summary_signals(analysis)

        return analysis

    async def _get_market_ticks(
        self, market_id: str, start_time: datetime, end_time: datetime
    ) -> List[OddsTick]:
        """Get all odds ticks for a market in time range."""
        stmt = (
            select(OddsTick)
            .where(
                and_(
                    OddsTick.market_id == market_id,
                    OddsTick.timestamp >= start_time,
                    OddsTick.timestamp <= end_time,
                )
            )
            .order_by(OddsTick.timestamp)
        )

        result = await self.db_session.execute(stmt)
        return list(result.scalars().all())

    async def _calculate_line_metrics(
        self, market_id: str, outcome: str, ticks: List[OddsTick]
    ) -> LineMetrics:
        """Calculate line movement metrics."""
        if not ticks:
            return LineMetrics(
                market_id=market_id,
                outcome=outcome,
                current_odds=Decimal(0),
                odds_1h_ago=None,
                odds_6h_ago=None,
                odds_24h_ago=None,
                opening_odds=None,
            )

        now = datetime.utcnow()
        hour_ago = now - timedelta(hours=1)
        six_hours_ago = now - timedelta(hours=6)
        twenty_four_hours_ago = now - timedelta(hours=24)

        # Find odds at different time points
        current_odds = ticks[-1].odds_decimal if ticks else Decimal(0)
        opening_odds = ticks[0].odds_decimal if ticks else None

        odds_1h = self._find_nearest_odds(ticks, hour_ago)
        odds_6h = self._find_nearest_odds(ticks, six_hours_ago)
        odds_24h = self._find_nearest_odds(ticks, twenty_four_hours_ago)

        # Calculate velocities (percentage change per hour)
        velocity_1h = self._calculate_velocity(current_odds, odds_1h, 1)
        velocity_6h = self._calculate_velocity(current_odds, odds_6h, 6)
        velocity_24h = self._calculate_velocity(current_odds, odds_24h, 24)

        # Calculate acceleration (change in velocity)
        acceleration = velocity_1h - velocity_6h if velocity_6h != 0 else 0

        # Determine direction
        if odds_24h:
            movement_pct = (
                (float(current_odds) - float(odds_24h)) / float(odds_24h) * 100
            )
            direction = (
                "up"
                if movement_pct > 1
                else ("down" if movement_pct < -1 else "neutral")
            )
        else:
            movement_pct = 0
            direction = "neutral"

        # Calculate volatility (std dev of returns)
        if len(ticks) > 1:
            returns = []
            for i in range(1, len(ticks)):
                if ticks[i - 1].odds_decimal > 0:
                    ret = (
                        float(ticks[i].odds_decimal) - float(ticks[i - 1].odds_decimal)
                    ) / float(ticks[i - 1].odds_decimal)
                    returns.append(ret)
            volatility = statistics.stdev(returns) * 100 if len(returns) > 1 else 0
        else:
            volatility = 0

        metrics = LineMetrics(
            market_id=market_id,
            outcome=outcome,
            current_odds=current_odds,
            odds_1h_ago=odds_1h,
            odds_6h_ago=odds_6h,
            odds_24h_ago=odds_24h,
            opening_odds=opening_odds,
            velocity_1h=velocity_1h,
            velocity_6h=velocity_6h,
            velocity_24h=velocity_24h,
            acceleration=acceleration,
            direction=direction,
            movement_pct=movement_pct,
            volatility=volatility,
            tick_count=len(ticks),
        )

        self._line_metrics_cache[f"{market_id}:{outcome}"] = metrics

        return metrics

    def _find_nearest_odds(
        self, ticks: List[OddsTick], target_time: datetime
    ) -> Optional[Decimal]:
        """Find odds closest to target time."""
        if not ticks:
            return None

        # Binary search would be better for large datasets
        for tick in reversed(ticks):
            if tick.timestamp <= target_time:
                return tick.odds_decimal

        return None

    def _calculate_velocity(
        self, current: Decimal, previous: Optional[Decimal], hours: float
    ) -> float:
        """Calculate velocity (percentage change per hour)."""
        if not previous or previous <= 0 or hours <= 0:
            return 0.0

        pct_change = (float(current) - float(previous)) / float(previous)
        return (pct_change / hours) * 100  # Percentage points per hour

    async def _detect_steam_moves(
        self, market_id: str, outcome: str, ticks: List[OddsTick]
    ) -> List[SteamMove]:
        """Detect significant steam moves."""
        if len(ticks) < 3:
            return []

        steam_moves = []

        # Look for rapid movements (>5% in <30 minutes)
        window_minutes = 30
        threshold_pct = 0.05

        i = 0
        while i < len(ticks) - 1:
            start_tick = ticks[i]

            # Find end of potential steam move
            j = i + 1
            while j < len(ticks):
                time_diff = (ticks[j].timestamp - start_tick.timestamp).total_seconds()

                if time_diff > window_minutes * 60:
                    break

                odds_change = abs(
                    float(ticks[j].odds_decimal) - float(start_tick.odds_decimal)
                )
                pct_change = (
                    odds_change / float(start_tick.odds_decimal)
                    if start_tick.odds_decimal > 0
                    else 0
                )

                if pct_change >= threshold_pct:
                    # Steam move detected
                    duration = time_diff
                    velocity = (
                        (pct_change * 100) / (duration / 3600) if duration > 0 else 0
                    )

                    # Determine severity
                    if pct_change >= 0.15:
                        severity = "extreme"
                    elif pct_change >= 0.10:
                        severity = "major"
                    elif pct_change >= 0.07:
                        severity = "moderate"
                    else:
                        severity = "minor"

                    move = SteamMove(
                        market_id=market_id,
                        outcome=outcome,
                        sportsbook_id=start_tick.sportsbook_id,
                        start_time=start_tick.timestamp,
                        end_time=ticks[j].timestamp,
                        start_odds=start_tick.odds_decimal,
                        end_odds=ticks[j].odds_decimal,
                        change_pct=pct_change * 100,
                        duration_seconds=duration,
                        velocity=velocity,
                        severity=severity,
                    )
                    steam_moves.append(move)

                    # Skip past this move
                    i = j
                    break

                j += 1

            i += 1

        self._steam_moves.extend(steam_moves)

        return steam_moves

    async def _calculate_cross_book_disagreement(
        self, market_id: str, outcome: str, ticks: List[OddsTick]
    ) -> Optional[CrossBookDisagreement]:
        """Calculate disagreement across sportsbooks."""
        if not ticks:
            return None

        # Get latest odds from each sportsbook
        latest_by_book: Dict[str, OddsTick] = {}
        for tick in ticks:
            book = tick.sportsbook_id
            if (
                book not in latest_by_book
                or tick.timestamp > latest_by_book[book].timestamp
            ):
                latest_by_book[book] = tick

        if len(latest_by_book) < 2:
            return None

        odds_values = [float(t.odds_decimal) for t in latest_by_book.values()]

        best = max(odds_values)
        worst = min(odds_values)
        avg = statistics.mean(odds_values)
        median = statistics.median(odds_values)
        std_dev = statistics.stdev(odds_values) if len(odds_values) > 1 else 0

        spread_pct = ((best - worst) / worst) * 100

        # Check for arbitrage opportunity
        # Simple 2-way market arbitrage check
        if len(latest_by_book) >= 2:
            # Would need both sides of market for true arb check
            arbitrage = spread_pct > 2.0  # Simplified
            arb_profit = spread_pct / 2 if arbitrage else 0
        else:
            arbitrage = False
            arb_profit = 0

        return CrossBookDisagreement(
            market_id=market_id,
            outcome=outcome,
            timestamp=datetime.utcnow(),
            best_odds=Decimal(str(best)),
            worst_odds=Decimal(str(worst)),
            avg_odds=Decimal(str(avg)),
            median_odds=Decimal(str(median)),
            spread_pct=spread_pct,
            std_dev=std_dev,
            arbitrage_opportunity=arbitrage,
            arb_profit_pct=arb_profit,
        )

    async def _calculate_market_pressure(
        self, market_id: str, outcome: str, ticks: List[OddsTick]
    ) -> Optional[MarketPressure]:
        """
        Calculate market pressure indicator.

        Uses line movement patterns to infer sharp vs public money.
        """
        if len(ticks) < 5:
            return None

        # Analyze movement pattern
        recent_ticks = ticks[-10:] if len(ticks) >= 10 else ticks

        # Count upward vs downward movements
        up_moves = 0
        down_moves = 0

        for i in range(1, len(recent_ticks)):
            if recent_ticks[i].odds_decimal > recent_ticks[i - 1].odds_decimal:
                up_moves += 1
            elif recent_ticks[i].odds_decimal < recent_ticks[i - 1].odds_decimal:
                down_moves += 1

        total_moves = up_moves + down_moves
        if total_moves == 0:
            return None

        # Pressure score: positive = upward pressure (money on outcome)
        # Negative = downward pressure (money against outcome)
        pressure = (up_moves - down_moves) / total_moves

        # Detect reverse line movement
        # RLM: line moves opposite to betting percentage
        # (Would need actual bet % data for true RLM)
        # Here we use velocity vs overall trend as proxy
        overall_trend = (
            (float(recent_ticks[-1].odds_decimal) - float(recent_ticks[0].odds_decimal))
            / float(recent_ticks[0].odds_decimal)
            if recent_ticks[0].odds_decimal > 0
            else 0
        )

        recent_velocity = pressure
        rlm = (overall_trend > 0 and recent_velocity < 0) or (
            overall_trend < 0 and recent_velocity > 0
        )

        # Determine signal strength
        abs_pressure = abs(pressure)
        if abs_pressure >= 0.7:
            strength = "strong"
        elif abs_pressure >= 0.4:
            strength = "moderate"
        else:
            strength = "weak"

        # Infer sharp side (simplified: assume late money is sharper)
        if pressure > 0.3:
            sharp_side = outcome
            public_side = f"not_{outcome}"
        elif pressure < -0.3:
            sharp_side = f"not_{outcome}"
            public_side = outcome
        else:
            sharp_side = None
            public_side = None

        return MarketPressure(
            market_id=market_id,
            outcome=outcome,
            pressure_score=pressure,
            confidence=min(1.0, len(recent_ticks) / 10),
            signal_strength=strength,
            sharp_side=sharp_side,
            public_side=public_side,
            reverse_line_move=rlm,
        )

    def _generate_summary_signals(self, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Generate summary trading signals."""
        outcomes = analysis.get("outcomes", {})
        steam_moves = analysis.get("steam_moves", [])
        pressure = analysis.get("pressure_indicators", [])

        signals = {
            "strong_steam_detected": len(
                [m for m in steam_moves if m.get("severity") in ["major", "extreme"]]
            )
            > 0,
            "high_disagreement": any(
                d.get("spread_pct", 0) > 3.0
                for d in analysis.get("cross_book_disagreement", [])
            ),
            "reverse_line_moves": sum(
                1 for p in pressure if p.get("reverse_line_move")
            ),
            "consensus_direction": self._determine_consensus(outcomes),
            "volatility_regime": self._classify_volatility(outcomes),
            "actionable_signals": [],
        }

        # Generate actionable signals
        if signals["strong_steam_detected"]:
            signals["actionable_signals"].append(
                {
                    "type": "steam_follow",
                    "description": "Strong steam move detected - consider following",
                    "confidence": "high",
                }
            )

        if signals["high_disagreement"]:
            signals["actionable_signals"].append(
                {
                    "type": "shop_arb",
                    "description": "High cross-book disagreement - shop for best price",
                    "confidence": "medium",
                }
            )

        if signals["reverse_line_moves"] > 0:
            signals["actionable_signals"].append(
                {
                    "type": "rlm_contrarian",
                    "description": "Reverse line movement detected - contrarian opportunity",
                    "confidence": "medium",
                }
            )

        return signals

    def _determine_consensus(self, outcomes: Dict[str, Any]) -> Optional[str]:
        """Determine consensus direction across outcomes."""
        if not outcomes:
            return None

        # Simple heuristic: which outcome has most upward pressure
        pressures = {}
        for outcome, data in outcomes.items():
            pressures[outcome] = data.get("velocity_1h", 0)

        if not pressures:
            return None

        max_outcome = max(pressures, key=pressures.get)
        if pressures[max_outcome] > 1.0:  # Significant upward movement
            return max_outcome

        return None

    def _classify_volatility(self, outcomes: Dict[str, Any]) -> str:
        """Classify volatility regime."""
        if not outcomes:
            return "unknown"

        volatilities = [o.get("volatility", 0) for o in outcomes.values()]

        if not volatilities:
            return "unknown"

        avg_vol = statistics.mean(volatilities)

        if avg_vol >= 5.0:
            return "extreme"
        elif avg_vol >= 3.0:
            return "high"
        elif avg_vol >= 1.5:
            return "moderate"
        else:
            return "low"

    def _metrics_to_dict(self, metrics: LineMetrics) -> Dict[str, Any]:
        """Convert LineMetrics to dictionary."""
        return {
            "current_odds": float(metrics.current_odds),
            "odds_1h_ago": float(metrics.odds_1h_ago) if metrics.odds_1h_ago else None,
            "odds_6h_ago": float(metrics.odds_6h_ago) if metrics.odds_6h_ago else None,
            "odds_24h_ago": (
                float(metrics.odds_24h_ago) if metrics.odds_24h_ago else None
            ),
            "opening_odds": (
                float(metrics.opening_odds) if metrics.opening_odds else None
            ),
            "velocity_1h": round(metrics.velocity_1h, 4),
            "velocity_6h": round(metrics.velocity_6h, 4),
            "velocity_24h": round(metrics.velocity_24h, 4),
            "acceleration": round(metrics.acceleration, 4),
            "direction": metrics.direction,
            "movement_pct": round(metrics.movement_pct, 2),
            "volatility": round(metrics.volatility, 4),
            "tick_count": metrics.tick_count,
        }

    def _steam_to_dict(self, move: SteamMove) -> Dict[str, Any]:
        """Convert SteamMove to dictionary."""
        return {
            "outcome": move.outcome,
            "sportsbook_id": move.sportsbook_id,
            "start_time": move.start_time.isoformat(),
            "end_time": move.end_time.isoformat(),
            "start_odds": float(move.start_odds),
            "end_odds": float(move.end_odds),
            "change_pct": round(move.change_pct, 2),
            "duration_seconds": round(move.duration_seconds, 1),
            "velocity": round(move.velocity, 2),
            "severity": move.severity,
        }

    def _disagreement_to_dict(self, d: CrossBookDisagreement) -> Dict[str, Any]:
        """Convert CrossBookDisagreement to dictionary."""
        return {
            "outcome": d.outcome,
            "timestamp": d.timestamp.isoformat(),
            "best_odds": float(d.best_odds),
            "worst_odds": float(d.worst_odds),
            "avg_odds": float(d.avg_odds),
            "median_odds": float(d.median_odds),
            "spread_pct": round(d.spread_pct, 2),
            "std_dev": round(d.std_dev, 4),
            "arbitrage_opportunity": d.arbitrage_opportunity,
            "arb_profit_pct": round(d.arb_profit_pct, 2),
        }

    def _pressure_to_dict(self, p: MarketPressure) -> Dict[str, Any]:
        """Convert MarketPressure to dictionary."""
        return {
            "outcome": p.outcome,
            "pressure_score": round(p.pressure_score, 4),
            "confidence": round(p.confidence, 2),
            "signal_strength": p.signal_strength,
            "sharp_side": p.sharp_side,
            "public_side": p.public_side,
            "reverse_line_move": p.reverse_line_move,
        }
