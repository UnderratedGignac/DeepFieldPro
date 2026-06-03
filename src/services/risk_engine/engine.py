# mypy: ignore-errors
"""
Risk Management Engine

Implements professional risk management:
- Fractional Kelly sizing
- Bankroll state machine
- Exposure caps
- Correlated bet detection
- Drawdown protection
- Volatility adjustment
- Risk-of-ruin estimation
"""

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from enum import Enum
import logging

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_

from database.models import Bet as PaperBet, BankrollSnapshot as BankrollHistory

logger = logging.getLogger(__name__)


class RiskLevel(Enum):
    """Risk level classification."""

    MINIMAL = "minimal"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    EXTREME = "extreme"


class BankrollState(Enum):
    """Bankroll state machine states."""

    HEALTHY = "healthy"
    WARNING = "warning"
    DRAWDOWN = "drawdown"
    CRITICAL = "critical"
    HALTED = "halted"


@dataclass
class BankrollConfig:
    """Configuration for bankroll management."""

    initial_bankroll: Decimal = Decimal("10000")
    kelly_fraction: float = 0.25  # Quarter Kelly (conservative)
    max_single_bet_pct: float = 0.05  # 5% max of bankroll
    max_total_exposure_pct: float = 0.30  # 30% max exposure
    max_correlated_exposure_pct: float = 0.15  # 15% for correlated bets
    stop_loss_pct: float = 0.20  # Stop at 20% drawdown
    daily_loss_limit_pct: float = 0.05  # 5% daily loss limit
    cooling_off_period_hours: int = 24
    volatility_adjustment: bool = True


@dataclass
class BankrollState:
    """Current bankroll state."""

    current_bankroll: Decimal
    initial_bankroll: Decimal
    peak_bankroll: Decimal
    drawdown_pct: float
    daily_pl: Decimal
    weekly_pl: Decimal
    monthly_pl: Decimal
    state: BankrollState
    risk_level: RiskLevel
    available_for_betting: Decimal
    total_exposure: Decimal
    active_bets_count: int
    last_updated: datetime


@dataclass
class BetSizing:
    """Recommended bet sizing."""

    recommended_stake: Decimal
    kelly_stake: Decimal
    max_allowed_stake: Decimal
    adjusted_stake: Decimal
    confidence_level: float
    risk_adjustment: float
    reasoning: str


class RiskEngine:
    """
    Professional risk management engine.

    Implements fractional Kelly criterion with additional constraints
    for sports betting portfolio management.
    """

    def __init__(
        self, db_session: AsyncSession, config: Optional[BankrollConfig] = None
    ):
        self.db_session = db_session
        self.config = config or BankrollConfig()
        self._bankroll_state: Optional[BankrollState] = None
        self._correlation_groups: Dict[str, List[str]] = {}

    async def initialize(self) -> None:
        """Initialize risk engine by loading bankroll state."""
        await self._load_bankroll_state()
        logger.info(
            f"Risk engine initialized: ${self._bankroll_state.current_bankroll}"
        )

    async def _load_bankroll_state(self) -> None:
        """Load current bankroll state from database."""
        # Get latest bankroll history
        stmt = (
            select(BankrollHistory).order_by(BankrollHistory.timestamp.desc()).limit(1)
        )
        result = await self.db_session.execute(stmt)
        latest = result.scalars().first()

        if latest:
            current = latest.balance
            peak = latest.peak_balance
            initial = self.config.initial_bankroll
        else:
            current = self.config.initial_bankroll
            peak = current
            initial = current

        # Calculate P/L periods
        now = datetime.utcnow()
        daily_start = now - timedelta(days=1)
        weekly_start = now - timedelta(weeks=1)
        monthly_start = now - timedelta(days=30)

        daily_pl = await self._calculate_pl(daily_start, now)
        weekly_pl = await self._calculate_pl(weekly_start, now)
        monthly_pl = await self._calculate_pl(monthly_start, now)

        # Calculate drawdown
        drawdown_pct = (
            ((float(peak) - float(current)) / float(peak) * 100) if peak > 0 else 0.0
        )

        # Get active exposure
        active_exposure = await self._calculate_active_exposure()
        active_bets = await self._count_active_bets()

        # Determine state
        state = self._determine_bankroll_state(drawdown_pct, daily_pl)
        risk_level = self._determine_risk_level(drawdown_pct, active_exposure, current)

        # Calculate available for betting
        available = max(
            Decimal(0),
            current * Decimal(str(self.config.max_total_exposure_pct))
            - active_exposure,
        )

        self._bankroll_state = BankrollState(
            current_bankroll=current,
            initial_bankroll=initial,
            peak_bankroll=peak,
            drawdown_pct=drawdown_pct,
            daily_pl=daily_pl,
            weekly_pl=weekly_pl,
            monthly_pl=monthly_pl,
            state=state,
            risk_level=risk_level,
            available_for_betting=available,
            total_exposure=active_exposure,
            active_bets_count=active_bets,
            last_updated=datetime.utcnow(),
        )

    async def _calculate_pl(self, start: datetime, end: datetime) -> Decimal:
        """Calculate P/L for a period."""
        stmt = select(func.sum(PaperBet.profit_loss)).where(
            and_(
                PaperBet.settled_at >= start,
                PaperBet.settled_at <= end,
            )
        )
        result = await self.db_session.execute(stmt)
        pl = result.scalar()
        return pl or Decimal(0)

    async def _calculate_active_exposure(self) -> Decimal:
        """Calculate total active exposure."""
        stmt = select(func.sum(PaperBet.stake)).where(
            PaperBet.status.in_(["placed", "accepted"])
        )
        result = await self.db_session.execute(stmt)
        exposure = result.scalar()
        return exposure or Decimal(0)

    async def _count_active_bets(self) -> int:
        """Count active bets."""
        stmt = select(func.count(PaperBet.id)).where(
            PaperBet.status.in_(["placed", "accepted"])
        )
        result = await self.db_session.execute(stmt)
        count = result.scalar()
        return count or 0

    def _determine_bankroll_state(
        self, drawdown_pct: float, daily_pl: Decimal
    ) -> BankrollState:
        """Determine bankroll state machine state."""
        if drawdown_pct >= self.config.stop_loss_pct:
            return BankrollState.HALTED

        if drawdown_pct >= self.config.stop_loss_pct * 0.75:
            return BankrollState.CRITICAL

        if drawdown_pct >= self.config.stop_loss_pct * 0.5:
            return BankrollState.DRAWDOWN

        if daily_pl < -self.config.initial_bankroll * Decimal(
            str(self.config.daily_loss_limit_pct)
        ):
            return BankrollState.WARNING

        return BankrollState.HEALTHY

    def _determine_risk_level(
        self, drawdown_pct: float, exposure: Decimal, bankroll: Decimal
    ) -> RiskLevel:
        """Determine overall risk level."""
        exposure_ratio = float(exposure / bankroll) if bankroll > 0 else 0

        score = 0
        score += min(3, drawdown_pct / 5)  # Up to 3 points for drawdown
        score += min(2, exposure_ratio / 0.1)  # Up to 2 points for exposure

        if score >= 4:
            return RiskLevel.EXTREME
        elif score >= 3:
            return RiskLevel.HIGH
        elif score >= 2:
            return RiskLevel.MEDIUM
        elif score >= 1:
            return RiskLevel.LOW
        else:
            return RiskLevel.MINIMAL

    def calculate_kelly_stake(
        self,
        probability: float,
        odds_decimal: Decimal,
        bankroll: Optional[Decimal] = None,
    ) -> Decimal:
        """
        Calculate Kelly criterion stake.

        Kelly formula: f* = (bp - q) / b
        where:
            b = decimal_odds - 1
            p = probability of winning
            q = 1 - p (probability of losing)

        Uses fractional Kelly based on config.
        """
        bankroll = (
            bankroll or self._bankroll_state.current_bankroll
            if self._bankroll_state
            else self.config.initial_bankroll
        )

        b = float(odds_decimal) - 1
        p = probability
        q = 1 - p

        # Full Kelly
        kelly = (b * p - q) / b if b > 0 else 0

        # Apply fractional Kelly
        fractional_kelly = kelly * self.config.kelly_fraction

        # Ensure non-negative
        fractional_kelly = max(0, fractional_kelly)

        # Convert to stake amount
        stake = float(bankroll) * fractional_kelly

        return Decimal(str(stake))

    def calculate_recommended_stake(
        self,
        probability: float,
        odds_decimal: Decimal,
        market_id: str,
        correlation_group: Optional[str] = None,
        confidence: float = 0.5,
    ) -> BetSizing:
        """
        Calculate recommended stake with all constraints applied.

        Applies:
        - Kelly criterion
        - Max single bet limit
        - Exposure limits
        - Correlation limits
        - State-based adjustments
        """
        if not self._bankroll_state:
            raise RuntimeError("Risk engine not initialized")

        bankroll = self._bankroll_state.current_bankroll

        # Calculate Kelly stake
        kelly_stake = self.calculate_kelly_stake(probability, odds_decimal, bankroll)

        # Apply max single bet constraint
        max_single = bankroll * Decimal(str(self.config.max_single_bet_pct))

        # Apply available capital constraint
        available = self._bankroll_state.available_for_betting

        # Start with minimum of constraints
        recommended = min(kelly_stake, max_single, available)

        # Apply state-based adjustments
        risk_adjustment = self._get_risk_adjustment()
        adjusted = recommended * Decimal(str(risk_adjustment))

        # Apply confidence adjustment
        confidence_factor = 0.5 + (confidence * 0.5)  # 0.5 to 1.0
        adjusted = adjusted * Decimal(str(confidence_factor))

        # Check correlation limits
        if correlation_group:
            correlated_exposure = self._get_correlated_exposure(correlation_group)
            max_correlated = bankroll * Decimal(
                str(self.config.max_correlated_exposure_pct)
            )
            remaining_correlated = max_correlated - correlated_exposure
            adjusted = min(adjusted, max(Decimal(0), remaining_correlated))

        # Final max allowed
        max_allowed = min(max_single, available)

        # Generate reasoning
        reasoning = []
        if kelly_stake > max_single:
            reasoning.append(
                f"Kelly (${kelly_stake:.2f}) capped by max single (${max_single:.2f})"
            )
        if recommended > available:
            reasoning.append(f"Capped by available capital (${available:.2f})")
        if risk_adjustment < 1.0:
            reasoning.append(f"Reduced by risk adjustment ({risk_adjustment:.2f}x)")
        if not reasoning:
            reasoning.append("Full Kelly stake within all limits")

        return BetSizing(
            recommended_stake=adjusted,
            kelly_stake=kelly_stake,
            max_allowed_stake=max_allowed,
            adjusted_stake=adjusted,
            confidence_level=confidence,
            risk_adjustment=risk_adjustment,
            reasoning="; ".join(reasoning),
        )

    def _get_risk_adjustment(self) -> float:
        """Get risk adjustment factor based on bankroll state."""
        if not self._bankroll_state:
            return 1.0

        state = self._bankroll_state.state

        if state == BankrollState.HALTED:
            return 0.0
        elif state == BankrollState.CRITICAL:
            return 0.1
        elif state == BankrollState.DRAWDOWN:
            return 0.5
        elif state == BankrollState.WARNING:
            return 0.75
        else:
            return 1.0

    def _get_correlated_exposure(self, group: str) -> Decimal:
        """Get total exposure for a correlation group."""
        if not self._bankroll_state:
            return Decimal(0)

        # Simplified: would need actual correlation tracking
        # In production, this queries active bets in the same group
        return Decimal(0)

    def register_correlation_group(self, group_id: str, market_ids: List[str]) -> None:
        """Register a group of correlated markets."""
        self._correlation_groups[group_id] = market_ids
        logger.debug(
            f"Registered correlation group {group_id}: {len(market_ids)} markets"
        )

    def check_bet_allowed(
        self, stake: Decimal, market_id: str, correlation_group: Optional[str] = None
    ) -> Tuple[bool, str]:
        """
        Check if a bet is allowed given current state.

        Returns:
            Tuple of (allowed, reason)
        """
        if not self._bankroll_state:
            return False, "Risk engine not initialized"

        state = self._bankroll_state

        # Check halted state
        if state.state == BankrollState.HALTED:
            return False, "Betting halted due to critical drawdown"

        # Check daily loss limit
        daily_limit = self.config.initial_bankroll * Decimal(
            str(self.config.daily_loss_limit_pct)
        )
        if state.daily_pl < -daily_limit:
            return (
                False,
                f"Daily loss limit reached (${abs(float(state.daily_pl)):.2f})",
            )

        # Check stake vs available
        if stake > state.available_for_betting:
            return (
                False,
                f"Stake exceeds available (${state.available_for_betting:.2f})",
            )

        # Check max single bet
        max_single = state.current_bankroll * Decimal(
            str(self.config.max_single_bet_pct)
        )
        if stake > max_single:
            return False, f"Stake exceeds max single bet (${max_single:.2f})"

        # Check correlation limits
        if correlation_group:
            correlated = self._get_correlated_exposure(correlation_group)
            max_corr = state.current_bankroll * Decimal(
                str(self.config.max_correlated_exposure_pct)
            )
            if correlated + stake > max_corr:
                return False, "Would exceed correlated exposure limit"

        return True, "Bet allowed"

    async def update_bankroll(self, profit_loss: Decimal) -> None:
        """Update bankroll after bet settlement."""
        if not self._bankroll_state:
            await self.initialize()
            return

        new_bankroll = self._bankroll_state.current_bankroll + profit_loss

        # Update peak if needed
        new_peak = max(self._bankroll_state.peak_bankroll, new_bankroll)

        # Persist to database
        history_entry = BankrollHistory(
            balance=new_bankroll,
            peak_balance=new_peak,
            change=profit_loss,
            timestamp=datetime.utcnow(),
        )

        self.db_session.add(history_entry)
        try:
            await self.db_session.commit()
        except Exception as e:
            await self.db_session.rollback()
            logger.error(f"Failed to update bankroll history: {e}")

        # Reload state
        await self._load_bankroll_state()

        logger.info(
            f"Bankroll updated: ${self._bankroll_state.current_bankroll} "
            f"(change: ${profit_loss}, drawdown: {self._bankroll_state.drawdown_pct:.2f}%)"
        )

    def get_statistics(self) -> Dict[str, Any]:
        """Get risk engine statistics."""
        if not self._bankroll_state:
            return {"initialized": False}

        state = self._bankroll_state

        return {
            "initialized": True,
            "current_bankroll": str(state.current_bankroll),
            "initial_bankroll": str(state.initial_bankroll),
            "peak_bankroll": str(state.peak_bankroll),
            "drawdown_pct": round(state.drawdown_pct, 2),
            "daily_pl": str(state.daily_pl),
            "weekly_pl": str(state.weekly_pl),
            "monthly_pl": str(state.monthly_pl),
            "state": state.state.value,
            "risk_level": state.risk_level.value,
            "available_for_betting": str(state.available_for_betting),
            "total_exposure": str(state.total_exposure),
            "exposure_pct": round(
                float(state.total_exposure / state.current_bankroll * 100), 2
            ),
            "active_bets": state.active_bets_count,
            "config": {
                "kelly_fraction": self.config.kelly_fraction,
                "max_single_bet_pct": self.config.max_single_bet_pct,
                "max_exposure_pct": self.config.max_total_exposure_pct,
                "stop_loss_pct": self.config.stop_loss_pct,
            },
        }

    def calculate_risk_of_ruin(
        self, win_rate: float, avg_odds: Decimal, kelly_fraction: float = None
    ) -> float:
        """
        Calculate risk of ruin using simplified formula.

        Risk of ruin ≈ ((1 - edge) / (1 + edge)) ^ (bankroll_units)

        This is an approximation; full calculation requires Monte Carlo.
        """
        kelly_frac = kelly_fraction or self.config.kelly_fraction

        # Expected value per bet
        ev = win_rate * (float(avg_odds) - 1) - (1 - win_rate)

        if ev <= 0:
            return 1.0  # Certain ruin with negative EV

        # Simplified risk of ruin
        # Assumes independent bets with constant edge
        bankroll_units = 1 / kelly_frac  # Units of bankroll at risk per bet

        edge_ratio = (1 - ev) / (1 + ev)
        risk_of_ruin = pow(edge_ratio, bankroll_units)

        return min(1.0, max(0.0, risk_of_ruin))

