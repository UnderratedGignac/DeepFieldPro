# mypy: ignore-errors
"""
Execution Simulator

Realistic sportsbook execution simulation modeling:
- Line movement during delay
- Sportsbook rejection
- Max stake limits
- Stale odds
- Slippage
- Market liquidity
- Execution latency
"""

import asyncio
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Dict, Optional, Any
from dataclasses import dataclass, field
import random
import logging

logger = logging.getLogger(__name__)


class ExecutionStatus(Enum):
    """Status of a bet execution."""

    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    PARTIAL_FILL = "partial_fill"
    STALE_ODDS = "stale_odds"
    LINE_MOVED = "line_moved"
    LIMIT_EXCEEDED = "limit_exceeded"
    MARKET_SUSPENDED = "market_suspended"
    TIMEOUT = "timeout"


class RejectionReason(Enum):
    """Reasons for bet rejection."""

    STALE_ODDS = "stale_odds"
    LINE_MOVED = "line_moved"
    LIMIT_EXCEEDED = "limit_exceeded"
    MARKET_SUSPENDED = "market_suspended"
    ACCOUNT_RESTRICTED = "account_restricted"
    BET_SIZE_INVALID = "bet_size_invalid"
    DUPLICATE_BET = "duplicate_bet"
    GEOGRAPHIC_BLOCK = "geographic_block"
    TECHNICAL_ERROR = "technical_error"


@dataclass
class ExecutionRequest:
    """Request to execute a bet."""

    request_id: str
    market_id: str
    sportsbook_id: str
    outcome: str
    stake: Decimal
    expected_odds: Decimal
    timestamp: datetime
    max_slippage: float = 0.05  # 5% max slippage tolerance
    timeout_seconds: float = 5.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionResult:
    """Result of a bet execution."""

    request_id: str
    status: ExecutionStatus
    executed_odds: Optional[Decimal] = None
    executed_stake: Optional[Decimal] = None
    rejection_reason: Optional[RejectionReason] = None
    latency_ms: float = 0.0
    slippage_pct: float = 0.0
    timestamp: datetime = field(default_factory=datetime.utcnow)
    message: str = ""


@dataclass
class SportsbookProfile:
    """Profile of a sportsbook's execution characteristics."""

    sportsbook_id: str
    avg_latency_ms: float = 500.0
    latency_std_ms: float = 200.0
    rejection_rate: float = 0.05  # 5% default rejection
    stale_odds_threshold_sec: float = 30.0
    max_stake_limits: Dict[str, Decimal] = field(default_factory=dict)
    accepts_line_movement: bool = True
    partial_fill_allowed: bool = False


class ExecutionSimulator:
    """
    Realistic sportsbook execution simulator.

    Models real-world execution conditions including latency,
    rejections, line movements, and stake limits.
    """

    def __init__(self):
        self._sportsbook_profiles: Dict[str, SportsbookProfile] = {}
        self._market_states: Dict[str, Dict[str, Any]] = {}
        self._execution_queue: asyncio.Queue = asyncio.Queue()
        self._processing = False

        # Initialize default profiles
        self._init_default_profiles()

    def _init_default_profiles(self) -> None:
        """Initialize default sportsbook profiles."""
        # Sharp books (lower limits, faster moves)
        self._sportsbook_profiles["pinnacle"] = SportsbookProfile(
            sportsbook_id="pinnacle",
            avg_latency_ms=300.0,
            latency_std_ms=100.0,
            rejection_rate=0.02,
            stale_odds_threshold_sec=15.0,
            max_stake_limits={"default": Decimal("5000")},
            accepts_line_movement=True,
        )

        # Recreational books (higher limits, slower moves)
        self._sportsbook_profiles["draftkings"] = SportsbookProfile(
            sportsbook_id="draftkings",
            avg_latency_ms=800.0,
            latency_std_ms=400.0,
            rejection_rate=0.08,
            stale_odds_threshold_sec=45.0,
            max_stake_limits={"default": Decimal("25000")},
            accepts_line_movement=False,
        )

        self._sportsbook_profiles["fanduel"] = SportsbookProfile(
            sportsbook_id="fanduel",
            avg_latency_ms=700.0,
            latency_std_ms=350.0,
            rejection_rate=0.07,
            stale_odds_threshold_sec=40.0,
            max_stake_limits={"default": Decimal("20000")},
            accepts_line_movement=False,
        )

        # European sharp books
        self._sportsbook_profiles["betfair"] = SportsbookProfile(
            sportsbook_id="betfair",
            avg_latency_ms=400.0,
            latency_std_ms=150.0,
            rejection_rate=0.03,
            stale_odds_threshold_sec=20.0,
            max_stake_limits={"default": Decimal("10000")},
            accepts_line_movement=True,
            partial_fill_allowed=True,
        )

    def register_sportsbook_profile(self, profile: SportsbookProfile) -> None:
        """Register or update a sportsbook profile."""
        self._sportsbook_profiles[profile.sportsbook_id] = profile
        logger.info(f"Registered profile for {profile.sportsbook_id}")

    def update_market_state(
        self,
        market_id: str,
        sportsbook_id: str,
        current_odds: Dict[str, Decimal],
        last_update: datetime,
        suspended: bool = False,
        liquidity: float = 1.0,
    ) -> None:
        """Update the current state of a market."""
        key = f"{market_id}:{sportsbook_id}"
        self._market_states[key] = {
            "market_id": market_id,
            "sportsbook_id": sportsbook_id,
            "current_odds": current_odds,
            "last_update": last_update,
            "suspended": suspended,
            "liquidity": max(0.0, min(1.0, liquidity)),
            "update_count": self._market_states.get(key, {}).get("update_count", 0) + 1,
        }

    async def execute(
        self, request: ExecutionRequest, simulate_delay: bool = True
    ) -> ExecutionResult:
        """
        Execute a bet request with realistic simulation.

        Args:
            request: The execution request
            simulate_delay: Whether to simulate network latency

        Returns:
            ExecutionResult with status and details
        """
        start_time = datetime.utcnow()

        # Get sportsbook profile
        profile = self._sportsbook_profiles.get(request.sportsbook_id)
        if not profile:
            logger.warning(
                f"Unknown sportsbook: {request.sportsbook_id}, using defaults"
            )
            profile = SportsbookProfile(sportsbook_id=request.sportsbook_id)

        # Simulate network latency
        if simulate_delay:
            latency_ms = random.gauss(profile.avg_latency_ms, profile.latency_std_ms)
            latency_ms = max(50.0, latency_ms)  # Minimum 50ms
            await asyncio.sleep(latency_ms / 1000.0)
        else:
            latency_ms = 0.0

        # Check market state
        market_key = f"{request.market_id}:{request.sportsbook_id}"
        market_state = self._market_states.get(market_key)

        if not market_state:
            return ExecutionResult(
                request_id=request.request_id,
                status=ExecutionStatus.REJECTED,
                rejection_reason=RejectionReason.TECHNICAL_ERROR,
                latency_ms=latency_ms,
                message="Market state not found",
            )

        # Check if market is suspended
        if market_state.get("suspended", False):
            return ExecutionResult(
                request_id=request.request_id,
                status=ExecutionStatus.MARKET_SUSPENDED,
                rejection_reason=RejectionReason.MARKET_SUSPENDED,
                latency_ms=latency_ms,
                message="Market is suspended",
            )

        # Check stake limits
        max_stake = profile.max_stake_limits.get(
            request.market_id.split(":")[0] if ":" in request.market_id else "default",
            profile.max_stake_limits.get("default", Decimal("10000")),
        )

        if request.stake > max_stake:
            if profile.partial_fill_allowed:
                # Partial fill
                return ExecutionResult(
                    request_id=request.request_id,
                    status=ExecutionStatus.PARTIAL_FILL,
                    executed_odds=request.expected_odds,
                    executed_stake=max_stake,
                    latency_ms=latency_ms,
                    message=f"Partial fill: {max_stake} of {request.stake}",
                )
            else:
                return ExecutionResult(
                    request_id=request.request_id,
                    status=ExecutionStatus.LIMIT_EXCEEDED,
                    rejection_reason=RejectionReason.LIMIT_EXCEEDED,
                    latency_ms=latency_ms,
                    message=f"Stake {request.stake} exceeds limit {max_stake}",
                )

        # Check for stale odds
        odds_age = (datetime.utcnow() - market_state["last_update"]).total_seconds()
        if odds_age > profile.stale_odds_threshold_sec:
            return ExecutionResult(
                request_id=request.request_id,
                status=ExecutionStatus.STALE_ODDS,
                rejection_reason=RejectionReason.STALE_ODDS,
                latency_ms=latency_ms,
                message=f"Odds stale: {odds_age:.1f}s old (threshold: {profile.stale_odds_threshold_sec}s)",
            )

        # Check for line movement
        current_odds = market_state.get("current_odds", {})
        current_outcome_odds = current_odds.get(request.outcome)

        if current_outcome_odds is None:
            return ExecutionResult(
                request_id=request.request_id,
                status=ExecutionStatus.REJECTED,
                rejection_reason=RejectionReason.TECHNICAL_ERROR,
                latency_ms=latency_ms,
                message="Outcome not found in market",
            )

        # Calculate slippage
        odds_change = abs(float(current_outcome_odds) - float(request.expected_odds))
        slippage_pct = (
            odds_change / float(request.expected_odds)
            if request.expected_odds > 0
            else 0.0
        )

        # Check if line moved against us beyond tolerance
        if slippage_pct > request.max_slippage:
            if not profile.accepts_line_movement:
                return ExecutionResult(
                    request_id=request.request_id,
                    status=ExecutionStatus.LINE_MOVED,
                    rejection_reason=RejectionReason.LINE_MOVED,
                    latency_ms=latency_ms,
                    slippage_pct=slippage_pct * 100,
                    message=f"Line moved: {slippage_pct*100:.2f}% slippage (max: {request.max_slippage*100:.2f}%)",
                )
            # Accept but warn
            logger.warning(
                f"Line moved on {request.market_id}: "
                f"{request.expected_odds} -> {current_outcome_odds} "
                f"({slippage_pct*100:.2f}% slippage)"
            )

        # Simulate random rejections based on profile
        if random.random() < profile.rejection_rate:
            rejection_reasons = [
                RejectionReason.ACCOUNT_RESTRICTED,
                RejectionReason.BET_SIZE_INVALID,
                RejectionReason.DUPLICATE_BET,
                RejectionReason.TECHNICAL_ERROR,
            ]
            return ExecutionResult(
                request_id=request.request_id,
                status=ExecutionStatus.REJECTED,
                rejection_reason=random.choice(rejection_reasons),
                latency_ms=latency_ms,
                message="Random rejection (simulated)",
            )

        # Successful execution
        execution_time = datetime.utcnow()
        total_latency = (execution_time - start_time).total_seconds() * 1000

        return ExecutionResult(
            request_id=request.request_id,
            status=ExecutionStatus.ACCEPTED,
            executed_odds=current_outcome_odds,
            executed_stake=request.stake,
            latency_ms=total_latency,
            slippage_pct=slippage_pct * 100,
            message="Bet accepted",
        )

    def estimate_execution_probability(
        self, market_id: str, sportsbook_id: str, stake: Decimal, odds: Decimal
    ) -> float:
        """
        Estimate probability of successful execution.

        Based on historical rejection rates, stake size relative to limits,
        and market liquidity.
        """
        profile = self._sportsbook_profiles.get(sportsbook_id)
        if not profile:
            return 0.5  # Unknown book, 50% estimate

        # Base probability from rejection rate
        base_prob = 1.0 - profile.rejection_rate

        # Adjust for stake size
        max_stake = profile.max_stake_limits.get("default", Decimal("10000"))
        stake_ratio = float(stake) / float(max_stake)

        if stake_ratio > 1.0:
            stake_adjustment = -0.3  # Over limit
        elif stake_ratio > 0.8:
            stake_adjustment = -0.1  # Near limit
        else:
            stake_adjustment = 0.0

        # Adjust for market state
        market_key = f"{market_id}:{sportsbook_id}"
        market_state = self._market_states.get(market_key)

        if market_state:
            liquidity_adj = (market_state.get("liquidity", 1.0) - 1.0) * 0.2
            if market_state.get("suspended", False):
                return 0.0
        else:
            liquidity_adj = -0.1  # Unknown market

        probability = base_prob + stake_adjustment + liquidity_adj
        return max(0.0, min(1.0, probability))

    def get_statistics(self) -> Dict[str, Any]:
        """Get execution simulator statistics."""
        return {
            "sportsbooks_registered": len(self._sportsbook_profiles),
            "markets_tracked": len(self._market_states),
            "queue_size": self._execution_queue.qsize(),
            "profiles": {
                sb_id: {
                    "avg_latency_ms": p.avg_latency_ms,
                    "rejection_rate": p.rejection_rate,
                    "stale_threshold_sec": p.stale_odds_threshold_sec,
                }
                for sb_id, p in self._sportsbook_profiles.items()
            },
        }


@dataclass
class ExecutionMetrics:
    """Aggregated execution metrics."""

    total_requests: int = 0
    accepted: int = 0
    rejected: int = 0
    partial_fills: int = 0
    stale_odds: int = 0
    line_moved: int = 0
    avg_latency_ms: float = 0.0
    avg_slippage_pct: float = 0.0

    def add_result(self, result: ExecutionResult) -> None:
        """Add an execution result to metrics."""
        self.total_requests += 1

        if result.status == ExecutionStatus.ACCEPTED:
            self.accepted += 1
        elif result.status == ExecutionStatus.REJECTED:
            self.rejected += 1
        elif result.status == ExecutionStatus.PARTIAL_FILL:
            self.partial_fills += 1
        elif result.status == ExecutionStatus.STALE_ODDS:
            self.stale_odds += 1
        elif result.status == ExecutionStatus.LINE_MOVED:
            self.line_moved += 1

        # Update running averages
        n = self.total_requests
        self.avg_latency_ms = ((n - 1) * self.avg_latency_ms + result.latency_ms) / n

        if result.slippage_pct > 0:
            slippage_count = self.accepted + self.partial_fills + self.line_moved
            if slippage_count > 0:
                self.avg_slippage_pct = (
                    (slippage_count - 1) * self.avg_slippage_pct + result.slippage_pct
                ) / slippage_count

    @property
    def acceptance_rate(self) -> float:
        """Get acceptance rate as percentage."""
        if self.total_requests == 0:
            return 0.0
        return (self.accepted / self.total_requests) * 100

    @property
    def rejection_rate(self) -> float:
        """Get rejection rate as percentage."""
        if self.total_requests == 0:
            return 0.0
        return (self.rejected / self.total_requests) * 100

