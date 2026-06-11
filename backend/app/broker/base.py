"""Broker interface shared by paper and (future) live trading.

The PortfolioEngine talks only to this interface, so swapping PaperBroker for a
real LiveBroker in Phase 5 requires no changes to risk logic or accounting.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from sqlalchemy.orm import Session

from app.models import PaperTrade


class BrokerInterface(ABC):
    @abstractmethod
    def get_price(self, symbol: str) -> float:
        """Latest traded price for a symbol."""

    @abstractmethod
    def open_position(
        self,
        db: Session,
        *,
        symbol: str,
        strategy: str,
        direction: str,
        qty: float,
        leverage: float,
        entry: float,
        stop: float,
        target: float,
        entry_fee: float,
    ) -> PaperTrade:
        """Open a position and persist it as an OPEN trade."""

    @abstractmethod
    def close_position(
        self, db: Session, trade: PaperTrade, exit_price: float, exit_fee: float
    ) -> PaperTrade:
        """Close an open trade at exit_price, recording realized P&L."""
