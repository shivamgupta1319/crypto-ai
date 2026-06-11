"""PaperBroker — simulated execution against live Binance prices.

Pure execution: it opens/closes trades and records realized P&L. All risk
checks and sizing live in the PortfolioEngine, exactly as they will for live.
"""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.broker.base import BrokerInterface
from app.data.binance import latest_price
from app.models import PaperTrade


class PaperBroker(BrokerInterface):
    def get_price(self, symbol: str) -> float:
        return latest_price(symbol)

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
        trade = PaperTrade(
            symbol=symbol,
            strategy=strategy,
            direction=direction,
            qty=qty,
            leverage=leverage,
            entry_price=entry,
            stop=stop,
            target=target,
            fees=entry_fee,
            status="OPEN",
        )
        db.add(trade)
        db.commit()
        db.refresh(trade)
        return trade

    def close_position(
        self, db: Session, trade: PaperTrade, exit_price: float, exit_fee: float
    ) -> PaperTrade:
        sign = 1 if trade.direction == "LONG" else -1
        gross = (exit_price - trade.entry_price) * trade.qty * sign
        total_fees = trade.fees + exit_fee
        trade.exit_price = exit_price
        trade.fees = total_fees
        trade.pnl = gross - total_fees  # entry_fee was already in trade.fees
        trade.status = "CLOSED"
        trade.closed_at = datetime.now(UTC)
        db.commit()
        db.refresh(trade)
        return trade
