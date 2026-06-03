"""
Shadow Execution System

Paper betting system for simulating bet placement without real money.
Tracks bet lifecycle, line movement after prediction, and expected vs realized edge.
"""

from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum
import uuid
import logging

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import json

from database.models import Bet as PaperBet

logger = logging.getLogger(__name__)


class BetStatus(Enum):
    """Status of a paper bet."""
    PENDING = "pending"
    PLACED = "placed"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    PARTIALLY_FILLED = "partially_filled"
    SETTLED_WIN = "settled_win"
    SETTLED_LOSS = "settled_loss"
    SETTLED_PUSH = "settled_push"
    CANCELLED = "cancelled"


class BetType(Enum):
    """Type of bet."""
    SINGLE = "single"
    PARLAY = "parlay"
    TEASER = "teaser"
    ROUND_ROBIN = "round_robin"


@dataclass
class ShadowBet:
    """Represents a shadow/paper bet."""
    bet_id: str
    market_id: str
    sportsbook_id: str
    outcome: str
    stake: Decimal
    odds_decimal: Decimal
    odds_american: int
    predicted_probability: float
    ev_pct: float
    status: BetStatus = BetStatus.PENDING
    placed_at: Optional[datetime] = None
    settled_at: Optional[datetime] = None
    result: Optional[str] = None
    actual_odds: Optional[Decimal] = None
    slippage_pct: float = 0.0
    closing_odds: Optional[Decimal] = None
    clv_pct: float = 0.0
    profit_loss: Decimal = Decimal(0)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "bet_id": self.bet_id,
            "market_id": self.market_id,
            "sportsbook_id": self.sportsbook_id,
            "outcome": self.outcome,
            "stake": str(self.stake),
            "odds_decimal": float(self.odds_decimal),
            "odds_american": self.odds_american,
            "predicted_probability": self.predicted_probability,
            "ev_pct": self.ev_pct,
            "status": self.status.value,
            "placed_at": self.placed_at.isoformat() if self.placed_at else None,
            "settled_at": self.settled_at.isoformat() if self.settled_at else None,
            "result": self.result,
            "actual_odds": float(self.actual_odds) if self.actual_odds else None,
            "slippage_pct": self.slippage_pct,
            "closing_odds": float(self.closing_odds) if self.closing_odds else None,
            "clv_pct": self.clv_pct,
            "profit_loss": str(self.profit_loss),
            "metadata": self.metadata,
        }


class ShadowExecutionEngine:
    """
    Shadow betting execution engine.
    
    Simulates real betting without actual money placement.
    Tracks all aspects of bet lifecycle for analysis.
    """
    
    def __init__(self, db_session: AsyncSession):
        self.db_session = db_session
        self._active_bets: Dict[str, ShadowBet] = {}
        self._bet_history: List[ShadowBet] = []
    
    async def place_bet(
        self,
        market_id: str,
        sportsbook_id: str,
        outcome: str,
        stake: Decimal,
        odds_decimal: Decimal,
        predicted_probability: float,
        model_id: str = "default",
        metadata: Optional[Dict[str, Any]] = None
    ) -> ShadowBet:
        """
        Place a shadow/paper bet.
        
        Args:
            market_id: Market identifier
            sportsbook_id: Sportsbook identifier
            outcome: Selected outcome
            stake: Bet stake amount
            odds_decimal: Decimal odds at placement
            predicted_probability: Model's predicted probability
            model_id: ID of the prediction model
            metadata: Additional metadata
            
        Returns:
            ShadowBet object
        """
        # Calculate American odds
        odds_american = self._decimal_to_american(odds_decimal)
        
        # Calculate expected value
        ev_pct = (predicted_probability * float(odds_decimal) - 1) * 100
        
        # Create bet
        bet = ShadowBet(
            bet_id=str(uuid.uuid4()),
            market_id=market_id,
            sportsbook_id=sportsbook_id,
            outcome=outcome,
            stake=stake,
            odds_decimal=odds_decimal,
            odds_american=odds_american,
            predicted_probability=predicted_probability,
            ev_pct=ev_pct,
            status=BetStatus.PLACED,
            placed_at=datetime.utcnow(),
            metadata=metadata or {},
        )
        bet.metadata["model_id"] = model_id
        
        # Persist to database
        await self._persist_bet(bet)
        
        # Track in memory
        self._active_bets[bet.bet_id] = bet
        
        logger.info(
            f"Shadow bet placed: {bet.bet_id[:8]}... "
            f"{market_id} @ {odds_decimal} (${stake})"
        )
        
        return bet
    
    async def _persist_bet(self, bet: ShadowBet) -> None:
        """Persist bet to database."""
        paper_bet = PaperBet(
            id=bet.bet_id,
            market_id=bet.market_id,
            sportsbook_id=bet.sportsbook_id,
            outcome=bet.outcome,
            stake=bet.stake,
            odds_decimal=bet.odds_decimal,
            odds_american=bet.odds_american,
            implied_probability=Decimal(str(1 / float(bet.odds_decimal))),
            predicted_probability=Decimal(str(bet.predicted_probability)),
            ev_pct=Decimal(str(bet.ev_pct)),
            status=bet.status.value,
            placed_at=bet.placed_at,
            metadata=json.dumps(bet.metadata),
        )
        
        self.db_session.add(paper_bet)
        try:
            await self.db_session.commit()
            await self.db_session.refresh(paper_bet)
        except Exception as e:
            await self.db_session.rollback()
            logger.error(f"Failed to persist paper bet: {e}")
            raise
    
    async def update_bet_status(
        self,
        bet_id: str,
        status: BetStatus,
        actual_odds: Optional[Decimal] = None,
        result: Optional[str] = None
    ) -> Optional[ShadowBet]:
        """Update bet status."""
        bet = self._active_bets.get(bet_id)
        if not bet:
            # Try to load from DB
            bet = await self._load_bet(bet_id)
        
        if not bet:
            logger.warning(f"Bet {bet_id} not found")
            return None
        
        bet.status = status
        
        if actual_odds:
            bet.actual_odds = actual_odds
            # Calculate slippage
            if bet.odds_decimal > 0:
                bet.slippage_pct = (
                    (float(actual_odds) - float(bet.odds_decimal)) 
                    / float(bet.odds_decimal) * 100
                )
        
        if result:
            bet.result = result
        
        # Update database
        await self._update_bet_in_db(bet)
        
        if status in [BetStatus.SETTLED_WIN, BetStatus.SETTLED_LOSS, BetStatus.SETTLED_PUSH]:
            bet.settled_at = datetime.utcnow()
            await self._calculate_profit_loss(bet)
            
            # Move to history
            if bet_id in self._active_bets:
                del self._active_bets[bet_id]
            self._bet_history.append(bet)
        
        return bet
    
    async def _calculate_profit_loss(self, bet: ShadowBet) -> None:
        """Calculate profit/loss for settled bet."""
        if bet.result == "win":
            profit = bet.stake * (bet.actual_odds or bet.odds_decimal - 1)
            bet.profit_loss = profit
        elif bet.result == "loss":
            bet.profit_loss = -bet.stake
        elif bet.result == "push":
            bet.profit_loss = Decimal(0)
        else:
            bet.profit_loss = Decimal(0)
    
    async def settle_bet(
        self,
        bet_id: str,
        result: str,
        closing_odds: Optional[Decimal] = None
    ) -> Optional[ShadowBet]:
        """
        Settle a bet with final result.
        
        Args:
            bet_id: Bet identifier
            result: 'win', 'loss', or 'push'
            closing_odds: Closing line odds for CLV calculation
        """
        bet = self._active_bets.get(bet_id)
        if not bet:
            bet = await self._load_bet(bet_id)
        
        if not bet:
            return None
        
        # Determine status
        if result == "win":
            status = BetStatus.SETTLED_WIN
        elif result == "loss":
            status = BetStatus.SETTLED_LOSS
        else:
            status = BetStatus.SETTLED_PUSH
        
        bet.result = result
        bet.status = status
        bet.settled_at = datetime.utcnow()
        
        # Set closing odds and calculate CLV
        if closing_odds:
            bet.closing_odds = closing_odds
            if bet.odds_decimal > 0:
                bet.clv_pct = (
                    (float(closing_odds) - float(bet.odds_decimal))
                    / float(bet.odds_decimal) * 100
                )
        
        await self._calculate_profit_loss(bet)
        await self._update_bet_in_db(bet)
        
        # Move to history
        if bet_id in self._active_bets:
            del self._active_bets[bet_id]
        self._bet_history.append(bet)
        
        logger.info(
            f"Bet settled: {bet_id[:8]}... "
            f"result={result}, P/L={bet.profit_loss}, CLV={bet.clv_pct:.2f}%"
        )
        
        return bet
    
    async def _load_bet(self, bet_id: str) -> Optional[ShadowBet]:
        """Load bet from database."""
        stmt = select(PaperBet).where(PaperBet.id == bet_id)
        result = await self.db_session.execute(stmt)
        paper_bet = result.scalars().first()
        
        if not paper_bet:
            return None
        
        return ShadowBet(
            bet_id=paper_bet.id,
            market_id=paper_bet.market_id,
            sportsbook_id=paper_bet.sportsbook_id,
            outcome=paper_bet.outcome,
            stake=paper_bet.stake,
            odds_decimal=paper_bet.odds_decimal,
            odds_american=paper_bet.odds_american,
            predicted_probability=float(paper_bet.predicted_probability),
            ev_pct=float(paper_bet.ev_pct),
            status=BetStatus(paper_bet.status),
            placed_at=paper_bet.placed_at,
            settled_at=paper_bet.settled_at,
            result=paper_bet.result,
            actual_odds=paper_bet.actual_odds,
            slippage_pct=float(paper_bet.slippage_pct) if paper_bet.slippage_pct else 0.0,
            closing_odds=paper_bet.closing_odds,
            clv_pct=float(paper_bet.clv_pct) if paper_bet.clv_pct else 0.0,
            profit_loss=paper_bet.profit_loss,
            metadata=json.loads(paper_bet.metadata) if paper_bet.metadata else {},
        )
    
    async def _update_bet_in_db(self, bet: ShadowBet) -> None:
        """Update bet in database."""
        stmt = select(PaperBet).where(PaperBet.id == bet.bet_id)
        result = await self.db_session.execute(stmt)
        paper_bet = result.scalars().first()
        
        if not paper_bet:
            return
        
        paper_bet.status = bet.status.value
        paper_bet.settled_at = bet.settled_at
        paper_bet.result = bet.result
        paper_bet.actual_odds = bet.actual_odds
        paper_bet.slippage_pct = Decimal(str(bet.slippage_pct))
        paper_bet.closing_odds = bet.closing_odds
        paper_bet.clv_pct = Decimal(str(bet.clv_pct))
        paper_bet.profit_loss = bet.profit_loss
        
        try:
            await self.db_session.commit()
        except Exception as e:
            await self.db_session.rollback()
            logger.error(f"Failed to update paper bet: {e}")
    
    def get_active_bets(self) -> List[ShadowBet]:
        """Get all active bets."""
        return list(self._active_bets.values())
    
    def get_bet_history(self, limit: int = 100) -> List[ShadowBet]:
        """Get recent bet history."""
        return self._bet_history[-limit:]
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get shadow betting statistics."""
        if not self._bet_history:
            return {
                "total_bets": 0,
                "active_bets": len(self._active_bets),
                "win_rate": 0.0,
                "roi": 0.0,
                "total_pl": Decimal(0),
                "avg_clv": 0.0,
                "avg_ev": 0.0,
            }
        
        total_staked = sum(b.stake for b in self._bet_history)
        total_pl = sum(b.profit_loss for b in self._bet_history)
        wins = sum(1 for b in self._bet_history if b.result == "win")
        losses = sum(1 for b in self._bet_history if b.result == "loss")
        pushes = sum(1 for b in self._bet_history if b.result == "push")
        
        decisive_bets = wins + losses
        win_rate = (wins / decisive_bets * 100) if decisive_bets > 0 else 0.0
        roi = (float(total_pl) / float(total_staked) * 100) if total_staked > 0 else 0.0
        
        avg_clv = sum(b.clv_pct for b in self._bet_history) / len(self._bet_history)
        avg_ev = sum(b.ev_pct for b in self._bet_history) / len(self._bet_history)
        
        return {
            "total_bets": len(self._bet_history),
            "active_bets": len(self._active_bets),
            "wins": wins,
            "losses": losses,
            "pushes": pushes,
            "win_rate": round(win_rate, 2),
            "roi": round(roi, 2),
            "total_staked": str(total_staked),
            "total_pl": str(total_pl),
            "avg_clv": round(avg_clv, 2),
            "avg_ev": round(avg_ev, 2),
        }
    
    def _decimal_to_american(self, decimal: Decimal) -> int:
        """Convert decimal odds to American odds."""
        dec_float = float(decimal)
        if dec_float >= 2.0:
            return int((dec_float - 1) * 100)
        else:
            return int(-100 / (dec_float - 1))
