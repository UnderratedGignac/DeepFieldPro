"""
Closing Line Value (CLV) Engine

Calculates and tracks CLV metrics:
- Standard CLV
- Weighted CLV
- Market-adjusted CLV
- Bookmaker-specific CLV
- Prediction timing analysis
"""

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from collections import defaultdict
import logging
import statistics

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_

from database.models import (
    OddsTick,
    Bet as PaperBet,
)

logger = logging.getLogger(__name__)


@dataclass
class CLVResult:
    """Result of a single CLV calculation."""

    bet_id: str
    market_id: str
    sportsbook_id: str
    outcome: str
    bet_odds: Decimal
    closing_odds: Decimal
    clv_pct: float
    weighted_clv: float
    timestamp: datetime
    bet_timestamp: datetime
    closing_timestamp: datetime
    time_to_close_hours: float


@dataclass
class CLVSummary:
    """Aggregated CLV summary statistics."""

    total_bets: int = 0
    positive_clv_count: int = 0
    negative_clv_count: int = 0
    avg_clv_pct: float = 0.0
    median_clv_pct: float = 0.0
    std_clv_pct: float = 0.0
    weighted_avg_clv: float = 0.0
    min_clv_pct: float = 0.0
    max_clv_pct: float = 0.0

    # By sportsbook
    by_sportsbook: Dict[str, Dict[str, float]] = field(default_factory=dict)

    # By sport
    by_sport: Dict[str, Dict[str, float]] = field(default_factory=dict)

    # By market type
    by_market_type: Dict[str, Dict[str, float]] = field(default_factory=dict)

    # Time-based
    last_7_days_avg: float = 0.0
    last_30_days_avg: float = 0.0

    @property
    def positive_clv_rate(self) -> float:
        """Percentage of bets with positive CLV."""
        if self.total_bets == 0:
            return 0.0
        return (self.positive_clv_count / self.total_bets) * 100

    @property
    def clv_edge(self) -> float:
        """Average CLV edge (positive is good)."""
        return self.avg_clv_pct


class CLVEngine:
    """
    Closing Line Value calculation and tracking engine.

    CLV measures the difference between the odds at bet placement
    and the closing line (odds at market close). Positive CLV indicates
    you got better odds than the market ultimately determined.

    Core formula:
    CLV = (ClosingOdds - BetOdds) / BetOdds * 100

    For American odds, conversion to decimal is performed first.
    """

    def __init__(self, db_session: AsyncSession):
        self.db_session = db_session
        self._clv_cache: Dict[str, CLVResult] = {}
        self._summaries: Dict[str, CLVSummary] = {}
        self._cache_ttl_seconds = 300  # 5 minutes

    async def calculate_clv(
        self, bet: PaperBet, closing_odds: Optional[Decimal] = None
    ) -> Optional[CLVResult]:
        """
        Calculate CLV for a single bet.

        Args:
            bet: The paper bet record
            closing_odds: Optional pre-fetched closing odds

        Returns:
            CLVResult or None if closing odds not available
        """
        # Check cache first
        cache_key = str(bet.id)
        if cache_key in self._clv_cache:
            cached = self._clv_cache[cache_key]
            if (
                datetime.utcnow() - cached.timestamp
            ).total_seconds() < self._cache_ttl_seconds:
                return cached

        # Get closing odds if not provided
        if closing_odds is None:
            closing_odds = await self._get_closing_odds(
                bet.market_id, bet.outcome, bet.sportsbook_id, bet.placed_at
            )

        if closing_odds is None or closing_odds <= 0:
            logger.debug(f"No closing odds found for bet {bet.id}")
            return None

        # Calculate CLV
        bet_odds_decimal = bet.odds_decimal
        clv_raw = (float(closing_odds) - float(bet_odds_decimal)) / float(
            bet_odds_decimal
        )
        clv_pct = clv_raw * 100

        # Calculate weighted CLV (weight by stake and odds)
        weight = float(bet.stake) * float(bet_odds_decimal)
        weighted_clv = clv_pct * weight

        # Time to close
        time_to_close = (bet.closing_time - bet.placed_at).total_seconds() / 3600.0

        result = CLVResult(
            bet_id=str(bet.id),
            market_id=bet.market_id,
            sportsbook_id=bet.sportsbook_id,
            outcome=bet.outcome,
            bet_odds=bet_odds_decimal,
            closing_odds=closing_odds,
            clv_pct=clv_pct,
            weighted_clv=weighted_clv,
            timestamp=datetime.utcnow(),
            bet_timestamp=bet.placed_at,
            closing_timestamp=bet.closing_time,
            time_to_close_hours=time_to_close,
        )

        # Cache result
        self._clv_cache[cache_key] = result

        return result

    async def _get_closing_odds(
        self, market_id: str, outcome: str, sportsbook_id: str, bet_time: datetime
    ) -> Optional[Decimal]:
        """
        Get closing odds for a market.

        Closing odds are defined as the last odds before market close
        or event start.
        """
        # Query for the last odds tick before event start
        # Assuming market closes ~event start time
        stmt = (
            select(OddsTick)
            .where(
                and_(
                    OddsTick.market_id == market_id,
                    OddsTick.outcome == outcome,
                    OddsTick.sportsbook_id == sportsbook_id,
                    OddsTick.timestamp > bet_time,
                )
            )
            .order_by(OddsTick.timestamp.desc())
            .limit(1)
        )

        result = await self.db_session.execute(stmt)
        tick = result.scalars().first()

        if tick:
            return tick.odds_decimal

        # Fallback: get the last known odds even if before bet time
        stmt = (
            select(OddsTick)
            .where(
                and_(
                    OddsTick.market_id == market_id,
                    OddsTick.outcome == outcome,
                    OddsTick.sportsbook_id == sportsbook_id,
                )
            )
            .order_by(OddsTick.timestamp.desc())
            .limit(1)
        )

        result = await self.db_session.execute(stmt)
        tick = result.scalars().first()

        if tick:
            return tick.odds_decimal

        return None

    async def calculate_portfolio_clv(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        sportsbook_id: Optional[str] = None,
        sport: Optional[str] = None,
    ) -> CLVSummary:
        """
        Calculate aggregated CLV metrics for a portfolio of bets.

        Args:
            start_date: Filter bets after this date
            end_date: Filter bets before this date
            sportsbook_id: Filter by specific sportsbook
            sport: Filter by sport type

        Returns:
            CLVSummary with aggregated statistics
        """
        # Build query filters
        filters = [PaperBet.settled == True]  # Only settled bets have closing lines  # noqa: E712

        if start_date:
            filters.append(PaperBet.placed_at >= start_date)
        if end_date:
            filters.append(PaperBet.placed_at <= end_date)
        if sportsbook_id:
            filters.append(PaperBet.sportsbook_id == sportsbook_id)
        if sport:
            filters.append(PaperBet.sport == sport)

        # Query all relevant bets with their closing odds
        stmt = select(PaperBet).where(*filters).order_by(PaperBet.placed_at.desc())

        result = await self.db_session.execute(stmt)
        bets = result.scalars().all()

        if not bets:
            return CLVSummary()

        # Calculate CLV for each bet
        clv_values: List[float] = []
        weighted_clv_values: List[float] = []
        weights: List[float] = []

        by_sportsbook: Dict[str, List[float]] = defaultdict(list)
        by_sport: Dict[str, List[float]] = defaultdict(list)
        by_market_type: Dict[str, List[float]] = defaultdict(list)

        positive_count = 0
        negative_count = 0

        for bet in bets:
            clv_result = await self.calculate_clv(bet)

            if clv_result is None:
                continue

            clv_values.append(clv_result.clv_pct)

            weight = float(bet.stake) * float(bet.odds_decimal)
            weights.append(weight)
            weighted_clv_values.append(clv_result.weighted_clv)

            if clv_result.clv_pct > 0:
                positive_count += 1
            else:
                negative_count += 1

            by_sportsbook[clv_result.sportsbook_id].append(clv_result.clv_pct)
            by_sport[bet.sport or "unknown"].append(clv_result.clv_pct)
            by_market_type[bet.market_type or "unknown"].append(clv_result.clv_pct)

        if not clv_values:
            return CLVSummary()

        # Calculate statistics
        summary = CLVSummary(
            total_bets=len(clv_values),
            positive_clv_count=positive_count,
            negative_clv_count=negative_count,
            avg_clv_pct=statistics.mean(clv_values),
            median_clv_pct=statistics.median(clv_values),
            std_clv_pct=statistics.stdev(clv_values) if len(clv_values) > 1 else 0.0,
            weighted_avg_clv=(
                sum(weighted_clv_values) / sum(weights) if weights else 0.0
            ),
            min_clv_pct=min(clv_values),
            max_clv_pct=max(clv_values),
        )

        # Calculate by-category summaries
        for sb, values in by_sportsbook.items():
            summary.by_sportsbook[sb] = {
                "avg": statistics.mean(values),
                "count": len(values),
                "positive_rate": sum(1 for v in values if v > 0) / len(values) * 100,
            }

        for sp, values in by_sport.items():
            summary.by_sport[sp] = {
                "avg": statistics.mean(values),
                "count": len(values),
                "positive_rate": sum(1 for v in values if v > 0) / len(values) * 100,
            }

        for mt, values in by_market_type.items():
            summary.by_market_type[mt] = {
                "avg": statistics.mean(values),
                "count": len(values),
                "positive_rate": sum(1 for v in values if v > 0) / len(values) * 100,
            }

        # Time-based analysis (last 7/30 days)
        now = datetime.utcnow()
        seven_days_ago = now - timedelta(days=7)
        thirty_days_ago = now - timedelta(days=30)

        recent_7 = [
            clv for bet, clv in zip(bets, clv_values) if bet.placed_at >= seven_days_ago
        ]
        recent_30 = [
            clv
            for bet, clv in zip(bets, clv_values)
            if bet.placed_at >= thirty_days_ago
        ]

        if recent_7:
            summary.last_7_days_avg = statistics.mean(recent_7)
        if recent_30:
            summary.last_30_days_avg = statistics.mean(recent_30)

        self._summaries["portfolio"] = summary

        return summary

    async def get_market_adjusted_clv(self, bet: PaperBet) -> Optional[float]:
        """
        Calculate market-adjusted CLV.

        Adjusts raw CLV by the overall market movement to isolate
        skill from general line movements.
        """
        clv_result = await self.calculate_clv(bet)
        if not clv_result:
            return None

        # Get average market movement for same market/time
        # This requires comparing across multiple sportsbooks
        stmt = select(func.avg(OddsTick.odds_decimal)).where(
            and_(
                OddsTick.market_id == bet.market_id,
                OddsTick.outcome == bet.outcome,
                OddsTick.timestamp > bet.placed_at,
                OddsTick.sportsbook_id != bet.sportsbook_id,
            )
        )

        result = await self.db_session.execute(stmt)
        avg_market_odds = result.scalar()

        if avg_market_odds is None:
            return clv_result.clv_pct

        # Calculate what the market average CLV would be
        market_clv = (
            (float(avg_market_odds) - float(bet.odds_decimal))
            / float(bet.odds_decimal)
            * 100
        )

        # Adjusted CLV = Raw CLV - Market CLV
        # Positive means you beat the market average
        adjusted_clv = clv_result.clv_pct - market_clv

        return adjusted_clv

    async def generate_clv_report(
        self, start_date: datetime, end_date: datetime
    ) -> Dict[str, Any]:
        """
        Generate comprehensive CLV report.

        Includes:
        - Overall CLV statistics
        - By sportsbook breakdown
        - By sport breakdown
        - By market type breakdown
        - Time series analysis
        - Statistical significance tests
        """
        summary = await self.calculate_portfolio_clv(start_date, end_date)

        # Additional analysis
        report = {
            "period": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat(),
            },
            "summary": {
                "total_bets": summary.total_bets,
                "avg_clv_pct": round(summary.avg_clv_pct, 4),
                "median_clv_pct": round(summary.median_clv_pct, 4),
                "std_clv_pct": round(summary.std_clv_pct, 4),
                "weighted_avg_clv": round(summary.weighted_avg_clv, 4),
                "min_clv_pct": round(summary.min_clv_pct, 4),
                "max_clv_pct": round(summary.max_clv_pct, 4),
                "positive_clv_rate": round(summary.positive_clv_rate, 2),
                "clv_edge": round(summary.clv_edge, 4),
            },
            "by_sportsbook": {
                sb: {
                    k: round(v, 4) if isinstance(v, float) else v
                    for k, v in metrics.items()
                }
                for sb, metrics in summary.by_sportsbook.items()
            },
            "by_sport": {
                sp: {
                    k: round(v, 4) if isinstance(v, float) else v
                    for k, v in metrics.items()
                }
                for sp, metrics in summary.by_sport.items()
            },
            "by_market_type": {
                mt: {
                    k: round(v, 4) if isinstance(v, float) else v
                    for k, v in metrics.items()
                }
                for mt, metrics in summary.by_market_type.items()
            },
            "time_analysis": {
                "last_7_days_avg": round(summary.last_7_days_avg, 4),
                "last_30_days_avg": round(summary.last_30_days_avg, 4),
            },
            "statistical_significance": self._calculate_significance(summary),
        }

        return report

    def _calculate_significance(self, summary: CLVSummary) -> Dict[str, Any]:
        """
        Calculate statistical significance of CLV results.

        Uses t-test to determine if CLV is significantly different from zero.
        """
        if summary.total_bets < 2:
            return {"significant": False, "reason": "Insufficient sample size"}

        # Simple t-statistic calculation
        se = summary.std_clv_pct / (summary.total_bets**0.5)
        if se == 0:
            return {"significant": False, "reason": "Zero standard error"}

        t_stat = summary.avg_clv_pct / se

        # Approximate p-value (for large n, t ≈ normal)
        # Using rough approximation: |t| > 1.96 for p < 0.05
        significant = abs(t_stat) > 1.96

        return {
            "significant": significant,
            "t_statistic": round(t_stat, 4),
            "standard_error": round(se, 4),
            "confidence_level": "95%" if significant else "<95%",
            "interpretation": (
                "CLV is statistically significant"
                if significant
                else "CLV is not statistically significant"
            ),
        }

    def clear_cache(self) -> None:
        """Clear CLV calculation cache."""
        self._clv_cache.clear()
        logger.debug("CLV cache cleared")
