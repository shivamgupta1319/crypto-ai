"""ORM models for candles cache, signals, paper trades, and active strategies.

Kept in one module so Base.metadata sees them all at create_all() time.
"""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    DateTime,
    Float,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Candle(Base):
    """Cached OHLCV candle for a (symbol, timeframe). open_time is ms epoch."""

    __tablename__ = "candles"
    __table_args__ = (
        UniqueConstraint("symbol", "timeframe", "open_time", name="uq_candle"),
        Index("ix_candle_lookup", "symbol", "timeframe", "open_time"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(8), nullable=False)
    open_time: Mapped[int] = mapped_column(Integer, nullable=False)  # ms epoch
    open: Mapped[float] = mapped_column(Float, nullable=False)
    high: Mapped[float] = mapped_column(Float, nullable=False)
    low: Mapped[float] = mapped_column(Float, nullable=False)
    close: Mapped[float] = mapped_column(Float, nullable=False)
    volume: Mapped[float] = mapped_column(Float, nullable=False)


class ActiveStrategy(Base):
    """A {symbol, timeframe, strategy, params} combo promoted from a backtest.

    Both the live scanner and the paper-trader read this table.
    """

    __tablename__ = "active_strategies"
    __table_args__ = (
        UniqueConstraint("symbol", "timeframe", "strategy", name="uq_active"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(8), nullable=False)
    strategy: Mapped[str] = mapped_column(String(40), nullable=False)
    params_json: Mapped[str] = mapped_column(String, default="{}")
    enabled: Mapped[bool] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class Signal(Base):
    """A trade signal emitted by a strategy (used by scanner + paper trading)."""

    __tablename__ = "signals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(8), nullable=False)
    strategy: Mapped[str] = mapped_column(String(40), nullable=False)
    direction: Mapped[str] = mapped_column(String(5), nullable=False)  # LONG / SHORT
    entry: Mapped[float] = mapped_column(Float, nullable=False)
    stop: Mapped[float] = mapped_column(Float, nullable=False)
    target: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    bar_time: Mapped[int] = mapped_column(Integer, nullable=False)  # candle open_time ms
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class BacktestRun(Base):
    """A saved backtest run so results are viewable later.

    Full results (metrics + equity curve + trades per strategy) are stored as
    compact JSON; ``summary_json`` holds just the headline metrics for listing.
    """

    __tablename__ = "backtest_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(8), nullable=False)
    start: Mapped[str] = mapped_column(String(32), nullable=False)
    end: Mapped[str] = mapped_column(String(32), nullable=False)
    leverage: Mapped[float] = mapped_column(Float, nullable=False)
    risk_per_trade_pct: Mapped[float] = mapped_column(Float, nullable=False)
    candles: Mapped[int] = mapped_column(Integer, default=0)
    strategies_json: Mapped[str] = mapped_column(String, default="[]")
    summary_json: Mapped[str] = mapped_column(String, default="[]")  # per-strategy headline metrics
    results_json: Mapped[str] = mapped_column(String, default="{}")  # full results payload


class TrainingSample(Base):
    """A labeled signal-context sample for meta-labeling (N10 stage 1).

    Features (indicators + regime one-hot) are stored as JSON; the triple-barrier
    outcome (``label`` 1=win/0=loss, ``realized_r``) is the training target.
    ``source`` is 'backtest' (cold-start) or 'live'.
    """

    __tablename__ = "training_samples"
    __table_args__ = (
        UniqueConstraint("symbol", "timeframe", "strategy", "bar_time", "source",
                         name="uq_training_sample"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(8), nullable=False)
    strategy: Mapped[str] = mapped_column(String(40), nullable=False)
    direction: Mapped[int] = mapped_column(Integer, nullable=False)  # 1 long / -1 short
    regime: Mapped[str] = mapped_column(String(20), default="ranging")
    features_json: Mapped[str] = mapped_column(String, default="{}")
    label: Mapped[int] = mapped_column(Integer, nullable=False)       # 1 win / 0 loss
    realized_r: Mapped[float] = mapped_column(Float, default=0.0)
    bars_held: Mapped[int] = mapped_column(Integer, default=0)
    source: Mapped[str] = mapped_column(String(10), default="backtest")
    bar_time: Mapped[int] = mapped_column(Integer, nullable=False)


class AgentProposal(Base):
    """A change the adaptive agent proposes for human approval (N10 stage 6).

    ``kind`` selects the lever (e.g. disable_strategy / set_size_multiplier /
    update_params / set_meta_threshold). ``payload_json`` holds the specifics and
    ``prev_json`` the prior state so an approved change can be reverted.
    """

    __tablename__ = "agent_proposals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    rationale: Mapped[str] = mapped_column(String, default="")
    payload_json: Mapped[str] = mapped_column(String, default="{}")
    prev_json: Mapped[str] = mapped_column(String, default="{}")
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    status: Mapped[str] = mapped_column(String(12), default="pending")  # pending/approved/rejected/reverted
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Setting(Base):
    """Runtime-editable settings overrides (key -> JSON value).

    Defaults live in ``config.py``; rows here override them and are applied onto
    the live ``settings`` object at startup and whenever the Settings page saves.
    """

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value_json: Mapped[str] = mapped_column(String, default="null")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)


class PortfolioSnapshot(Base):
    """A point-in-time paper-account snapshot recorded each scan cycle.

    Unlike the closed-trade-derived ``equity_curve``, this captures *unrealized*
    P&L too, so the equity time-series reflects open-position swings between fills
    and is auditable later without re-deriving it.
    """

    __tablename__ = "portfolio_snapshots"
    __table_args__ = (Index("ix_snapshot_time", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    realized_balance: Mapped[float] = mapped_column(Float, nullable=False)
    unrealized_pnl: Mapped[float] = mapped_column(Float, default=0.0)
    equity: Mapped[float] = mapped_column(Float, nullable=False)
    open_positions: Mapped[int] = mapped_column(Integer, default=0)
    kill_switch: Mapped[bool] = mapped_column(Integer, default=0)


class PaperTrade(Base):
    """A paper trade lifecycle row (open -> closed). P&L stored on close."""

    __tablename__ = "paper_trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    strategy: Mapped[str] = mapped_column(String(40), nullable=False)
    direction: Mapped[str] = mapped_column(String(5), nullable=False)
    qty: Mapped[float] = mapped_column(Float, nullable=False)
    leverage: Mapped[float] = mapped_column(Float, nullable=False)
    entry_price: Mapped[float] = mapped_column(Float, nullable=False)
    stop: Mapped[float] = mapped_column(Float, nullable=False)
    target: Mapped[float] = mapped_column(Float, nullable=False)
    exit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    fees: Mapped[float] = mapped_column(Float, default=0.0)
    pnl: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(10), default="OPEN")  # OPEN / CLOSED
    opened_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
