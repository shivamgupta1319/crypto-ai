"""Pydantic request/response schemas for the API."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class StrategyInfo(BaseModel):
    name: str
    description: str
    default_params: dict[str, Any]
    suited_for: list[str]


class BacktestRequest(BaseModel):
    symbol: str = "BTCUSDT"
    timeframe: str = "1h"
    start: str = Field(..., description="ISO date, e.g. 2024-01-01")
    end: str = Field(..., description="ISO date, e.g. 2024-06-01")
    strategies: list[str] = Field(..., description="One or more strategy names")
    params: dict[str, dict[str, Any]] | None = None  # per-strategy overrides
    leverage: float | None = None
    risk_per_trade_pct: float | None = None


class StrategyResult(BaseModel):
    strategy: str
    metrics: dict[str, Any]
    equity_curve: list[dict[str, Any]]
    trades: list[dict[str, Any]]
    benchmark_curve: list[dict[str, Any]] = []  # buy-&-hold over the same window


class BacktestResponse(BaseModel):
    run_id: int | None = None
    symbol: str
    timeframe: str
    start: str
    end: str
    candles: int
    results: list[StrategyResult]


class BacktestRunSummary(BaseModel):
    id: int
    created_at: str
    symbol: str
    timeframe: str
    start: str
    end: str
    leverage: float
    risk_per_trade_pct: float
    candles: int
    strategies: list[str]
    summary: list[dict[str, Any]]  # per-strategy headline metrics


class RobustnessRequest(BaseModel):
    symbol: str = "BTCUSDT"
    timeframe: str = "1h"
    start: str
    end: str
    strategy: str
    param_grid: dict[str, list[Any]] = {}  # {param: [values]}
    metric: str = "sharpe"
    leverage: float | None = None
    risk_per_trade_pct: float | None = None
    # method-specific knobs
    train_frac: float = 0.7   # out-of-sample
    folds: int = 5            # walk-forward
    n_iter: int = 1000        # monte carlo
    params: dict[str, Any] | None = None  # monte carlo: params for the single run


class PromoteRequest(BaseModel):
    symbol: str
    timeframe: str
    strategy: str
    params: dict[str, Any] | None = None


class ActiveStrategyOut(BaseModel):
    id: int
    symbol: str
    timeframe: str
    strategy: str
    params: dict[str, Any]
    enabled: bool


class SignalOut(BaseModel):
    id: int
    symbol: str
    timeframe: str
    strategy: str
    direction: str
    entry: float
    stop: float
    target: float
    confidence: float
    bar_time: int
    created_at: str


class AccountSummary(BaseModel):
    initial_capital: float
    balance: float
    equity: float
    unrealized_pnl: float
    realized_pnl: float
    return_pct: float
    open_positions: int
    closed_trades: int
    win_rate: float
    kill_switch: bool
    display_currency: str


class OpenPosition(BaseModel):
    id: int
    symbol: str
    strategy: str
    direction: str
    qty: float
    leverage: float
    entry_price: float
    stop: float
    target: float
    current_price: float
    unrealized_pnl: float
    opened_at: str


class ClosedTrade(BaseModel):
    id: int
    symbol: str
    strategy: str
    direction: str
    qty: float
    entry_price: float
    exit_price: float | None
    pnl: float
    fees: float
    opened_at: str
    closed_at: str | None


class NewsItem(BaseModel):
    source: str
    title: str
    link: str
    summary: str
    published: str
    published_ts: int | None
    coins: list[str]
    sentiment: str
