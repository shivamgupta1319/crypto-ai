"""Event-driven backtest engine.

Consumes a candle DataFrame annotated by a strategy (``signal`` + ``atr``) and
simulates a single-position-per-symbol paper account with risk-based sizing,
leverage, and taker fees. No look-ahead: a signal on bar i is acted on at the
open of bar i+1; stops/targets are checked intrabar via high/low.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from app.config import settings
from app.strategies.base import enrich_df, merge_params, run_strategy, stop_target


@dataclass
class BacktestConfig:
    initial_capital: float = settings.initial_capital
    risk_per_trade_pct: float = settings.risk_per_trade_pct
    leverage: float = settings.default_leverage
    max_position_pct: float = settings.max_position_pct
    taker_fee_pct: float = settings.taker_fee_pct
    reverse_on_opposite: bool = True
    # Realism: slippage per fill + a funding carry cost proportional to hold time.
    slippage_pct: float = 0.02
    funding_rate_pct_per_8h: float = settings.funding_rate_pct_per_8h
    apply_funding: bool = True


def _fill_with_slippage(direction: int, price: float, is_entry: bool, slip_pct: float) -> float:
    """Worsen the fill by slippage: pay up to enter/cover, receive less to exit/sell."""
    slip = slip_pct / 100.0
    # Entry long or exit short = a buy (pay more); entry short or exit long = a sell (get less).
    is_buy = (direction == 1 and is_entry) or (direction == -1 and not is_entry)
    return price * (1 + slip) if is_buy else price * (1 - slip)


@dataclass
class _Position:
    direction: int  # 1 long / -1 short
    entry: float
    qty: float
    stop: float
    target: float
    risk_amount: float
    entry_fee: float
    bar_time: int


@dataclass
class BacktestResult:
    metrics: dict[str, Any]
    equity_curve: list[dict[str, Any]] = field(default_factory=list)
    trades: list[dict[str, Any]] = field(default_factory=list)
    benchmark_curve: list[dict[str, Any]] = field(default_factory=list)  # buy-&-hold


def _size_position(
    equity: float, entry: float, stop: float, cfg: BacktestConfig
) -> tuple[float, float]:
    """Return (qty, risk_amount) sized to risk_per_trade_pct, capped by leverage."""
    risk_amount = equity * cfg.risk_per_trade_pct / 100.0
    stop_dist = abs(entry - stop)
    if stop_dist <= 0:
        return 0.0, 0.0
    qty = risk_amount / stop_dist
    max_notional = equity * (cfg.max_position_pct / 100.0) * cfg.leverage
    if qty * entry > max_notional:
        qty = max_notional / entry
    return qty, risk_amount


def run_backtest(
    symbol: str,
    timeframe: str,
    df: pd.DataFrame,
    strategy: str,
    params: dict[str, Any] | None = None,
    cfg: BacktestConfig | None = None,
    entry_mask: np.ndarray | None = None,
) -> BacktestResult:
    """Event-driven backtest. If ``entry_mask`` (bool array, one per bar) is given,
    a new position only opens when the mask is True at the decision bar — used by
    the meta-labeling filter (N10) to suppress low-quality entries."""
    cfg = cfg or BacktestConfig()
    df = enrich_df(strategy, df, symbol)  # attach funding/etc. for perp strategies
    annotated = run_strategy(strategy, df, params)
    run_params = merge_params(strategy, params)  # defaults + overrides for stop/target

    o = annotated["open"].to_numpy()
    h = annotated["high"].to_numpy()
    low = annotated["low"].to_numpy()
    c = annotated["close"].to_numpy()
    atr = annotated["atr"].to_numpy()
    sig = annotated["signal"].to_numpy()
    times = annotated["open_time"].to_numpy()

    equity = cfg.initial_capital
    pos: _Position | None = None
    pending: int = 0  # signal from previous bar to act on at this open
    pending_bar: int = -1  # the bar that produced ``pending`` (for entry_mask)
    trades: list[dict[str, Any]] = []
    curve: list[dict[str, Any]] = []
    n = len(annotated)

    def open_position(direction: int, price: float, atr_val: float, bar_time: int) -> None:
        nonlocal pos, equity
        if not math.isfinite(atr_val) or atr_val <= 0:
            return
        entry = _fill_with_slippage(direction, price, True, cfg.slippage_pct)
        stop, target = stop_target(direction, entry, atr_val, run_params)
        qty, risk_amount = _size_position(equity, entry, stop, cfg)
        if qty <= 0:
            return
        entry_fee = qty * entry * cfg.taker_fee_pct / 100.0
        equity -= entry_fee
        pos = _Position(direction, entry, qty, stop, target, risk_amount, entry_fee, bar_time)

    def close_position(price: float, reason: str, bar_time: int) -> None:
        nonlocal pos, equity
        assert pos is not None
        exit_price = _fill_with_slippage(pos.direction, price, False, cfg.slippage_pct)
        gross = (exit_price - pos.entry) * pos.qty * pos.direction
        exit_fee = pos.qty * exit_price * cfg.taker_fee_pct / 100.0
        # Funding: a carry cost proportional to notional and hold time (approximation —
        # real perp funding oscillates; modeled as a conservative drag here).
        funding = 0.0
        if cfg.apply_funding:
            hold_hours = max(0.0, (bar_time - pos.bar_time) / 3_600_000)
            funding = pos.qty * pos.entry * (cfg.funding_rate_pct_per_8h / 100.0) * (hold_hours / 8.0)
        pnl = gross - exit_fee - funding  # entry_fee already deducted at open
        equity += pnl
        r_multiple = pnl / pos.risk_amount if pos.risk_amount else 0.0
        trades.append({
            "direction": "LONG" if pos.direction == 1 else "SHORT",
            "entry": round(float(pos.entry), 4),
            "exit": round(float(exit_price), 4),
            "qty": round(float(pos.qty), 6),
            "pnl": round(float(pnl), 2),
            "r": round(float(r_multiple), 3),
            "funding": round(float(funding), 2),
            "reason": reason,
            "entry_time": int(pos.bar_time),
            "exit_time": int(bar_time),
        })
        pos = None

    for i in range(n):
        bar_time = int(times[i])

        # A. Act on the previous bar's signal at this bar's open.
        if pending != 0:
            allowed = entry_mask is None or (0 <= pending_bar < n and bool(entry_mask[pending_bar]))
            if pos is None:
                if allowed:
                    open_position(pending, o[i], atr[i], bar_time)
            elif pending == -pos.direction:
                close_position(o[i], "signal", bar_time)
                if cfg.reverse_on_opposite and allowed:
                    open_position(pending, o[i], atr[i], bar_time)
        pending = 0

        # B. Check stop/target intrabar for an open position (stop assumed first).
        if pos is not None:
            if pos.direction == 1:
                if low[i] <= pos.stop:
                    close_position(pos.stop, "stop", bar_time)
                elif h[i] >= pos.target:
                    close_position(pos.target, "target", bar_time)
            else:  # short
                if h[i] >= pos.stop:
                    close_position(pos.stop, "stop", bar_time)
                elif low[i] <= pos.target:
                    close_position(pos.target, "target", bar_time)

        # C. Mark-to-market equity for the curve.
        mtm = equity
        if pos is not None:
            mtm += (c[i] - pos.entry) * pos.qty * pos.direction
        curve.append({"time": bar_time, "equity": round(float(mtm), 2)})

        # D. Latch this bar's signal for next bar's open.
        if i < n - 1:
            pending = int(sig[i])
            pending_bar = i

    # Close any dangling position at the last close.
    if pos is not None:
        close_position(c[-1], "eod", int(times[-1]))
        curve[-1]["equity"] = round(float(equity), 2)

    # Buy-&-hold benchmark over the same window (same starting capital).
    benchmark_curve: list[dict[str, Any]] = []
    bh_return_pct = 0.0
    if n > 0 and c[0] > 0:
        for i in range(n):
            benchmark_curve.append(
                {"time": int(times[i]), "equity": round(float(cfg.initial_capital * c[i] / c[0]), 2)}
            )
        bh_return_pct = float((c[-1] / c[0] - 1) * 100)

    tf_ms = int(times[1] - times[0]) if n > 1 else 0
    duration_ms = int(times[-1] - times[0]) if n > 1 else 0
    metrics = _compute_metrics(
        equity, cfg.initial_capital, trades, curve, tf_ms, duration_ms, bh_return_pct
    )
    return BacktestResult(
        metrics=metrics, equity_curve=curve, trades=trades, benchmark_curve=benchmark_curve
    )


def _max_consecutive_losses(trades: list[dict[str, Any]]) -> int:
    worst = run = 0
    for t in trades:
        if t["pnl"] < 0:
            run += 1
            worst = max(worst, run)
        else:
            run = 0
    return worst


def _compute_metrics(
    final_equity: float,
    initial: float,
    trades: list[dict[str, Any]],
    curve: list[dict[str, Any]],
    tf_ms: int,
    duration_ms: int,
    buy_hold_return_pct: float,
) -> dict[str, Any]:
    n = len(trades)
    wins = [t for t in trades if t["pnl"] > 0]
    losses = [t for t in trades if t["pnl"] < 0]
    gross_profit = sum(t["pnl"] for t in wins)
    gross_loss = abs(sum(t["pnl"] for t in losses))
    net = final_equity - initial

    eq = np.array([p["equity"] for p in curve], dtype=float) if curve else np.array([initial])
    running_max = np.maximum.accumulate(eq)
    drawdowns = (eq - running_max) / running_max
    max_dd = float(drawdowns.min() * 100) if len(drawdowns) else 0.0

    # Per-bar returns → annualized Sharpe/Sortino using the bar cadence.
    rets = np.diff(eq) / eq[:-1] if len(eq) > 1 else np.array([0.0])
    year_ms = 365.25 * 24 * 3600 * 1000
    bars_per_year = (year_ms / tf_ms) if tf_ms > 0 else 0.0
    ann = math.sqrt(bars_per_year) if bars_per_year > 0 else 0.0
    sharpe_bar = float(rets.mean() / rets.std()) if rets.std() > 0 else 0.0
    downside = rets[rets < 0]
    dstd = float(downside.std()) if downside.size > 1 else 0.0
    sortino_bar = float(rets.mean() / dstd) if dstd > 0 else 0.0

    years = duration_ms / year_ms if duration_ms > 0 else 0.0
    cagr = ((final_equity / initial) ** (1 / years) - 1) * 100 if years > 0 and final_equity > 0 else 0.0
    calmar = (cagr / abs(max_dd)) if max_dd < 0 else None

    hold_hours = [(t["exit_time"] - t["entry_time"]) / 3_600_000 for t in trades]
    avg_hold_h = float(np.mean(hold_hours)) if hold_hours else 0.0
    exposure = (sum(hold_hours) * 3_600_000 / duration_ms * 100) if duration_ms > 0 else 0.0

    pf = gross_profit / gross_loss if gross_loss else None
    return {
        "initial_capital": round(float(initial), 2),
        "final_equity": round(float(final_equity), 2),
        "net_pnl": round(float(net), 2),
        "return_pct": round(float(net / initial * 100), 2) if initial else 0.0,
        "buy_hold_return_pct": round(float(buy_hold_return_pct), 2),
        "cagr_pct": round(float(cagr), 2),
        "total_trades": int(n),
        "win_rate": round(len(wins) / n * 100, 2) if n else 0.0,
        "profit_factor": round(float(pf), 2) if pf is not None else None,
        "expectancy_r": round(float(np.mean([t["r"] for t in trades])), 3) if n else 0.0,
        "avg_r": round(float(np.mean([t["r"] for t in trades])), 3) if n else 0.0,
        "max_drawdown_pct": round(float(max_dd), 2),
        "max_consecutive_losses": _max_consecutive_losses(trades),
        "avg_hold_hours": round(avg_hold_h, 1),
        "exposure_pct": round(float(min(exposure, 100.0)), 1),
        "sharpe": round(float(sharpe_bar * ann), 3),
        "sortino": round(float(sortino_bar * ann), 3),
        "calmar": round(float(calmar), 3) if calmar is not None else None,
        "sharpe_per_bar": round(float(sharpe_bar), 3),
    }
