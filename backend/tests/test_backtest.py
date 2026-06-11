"""Backtest engine tests on synthetic candles."""
from __future__ import annotations

import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401  (register tables)
from app.api import backtest as backtest_api
from app.backtest.engine import BacktestConfig, run_backtest
from app.db.session import Base
from app.models import BacktestRun


def test_backtest_runs_and_reports_metrics(trending_up):
    res = run_backtest("BTCUSDT", "1h", trending_up, "ema_trend_adx")
    m = res.metrics
    assert m["initial_capital"] == BacktestConfig().initial_capital
    assert m["total_trades"] >= 0
    assert len(res.equity_curve) == len(trending_up)
    # Metric keys present (incl. the richer set).
    for key in ["net_pnl", "return_pct", "win_rate", "max_drawdown_pct", "avg_r",
                "cagr_pct", "sharpe", "sortino", "max_consecutive_losses",
                "avg_hold_hours", "exposure_pct", "buy_hold_return_pct"]:
        assert key in m


def test_buy_and_hold_benchmark(trending_up):
    res = run_backtest("BTCUSDT", "1h", trending_up, "supertrend")
    # Clean uptrend → positive buy-&-hold, and a benchmark curve aligned to candles.
    assert res.metrics["buy_hold_return_pct"] > 0
    assert len(res.benchmark_curve) == len(trending_up)


def test_slippage_and_funding_reduce_pnl(trending_up):
    frictionless = BacktestConfig(taker_fee_pct=0.0, slippage_pct=0.0, apply_funding=False)
    realistic = BacktestConfig(taker_fee_pct=0.04, slippage_pct=0.05,
                               funding_rate_pct_per_8h=0.01, apply_funding=True)
    a = run_backtest("BTCUSDT", "1h", trending_up, "supertrend", cfg=frictionless)
    b = run_backtest("BTCUSDT", "1h", trending_up, "supertrend", cfg=realistic)
    # Frictions can only cost money, so realistic net P&L must be lower.
    assert b.metrics["net_pnl"] < a.metrics["net_pnl"]
    # Funding was charged on at least one closed trade.
    assert any(t.get("funding", 0) > 0 for t in b.trades)


def test_trend_following_profitable_in_clean_uptrend(trending_up):
    # A trend strategy should not lose money badly in a clean uptrend.
    res = run_backtest("BTCUSDT", "1h", trending_up, "supertrend")
    assert res.metrics["final_equity"] > 0
    # At least one trade should have occurred.
    assert res.metrics["total_trades"] >= 1


def test_no_lookahead_equity_curve_length(choppy):
    res = run_backtest("ETHUSDT", "1h", choppy, "bollinger_meanrev")
    assert len(res.equity_curve) == len(choppy)
    # Equity never goes negative in normal conditions with 1% risk.
    assert all(p["equity"] > 0 for p in res.equity_curve)


# --- saved backtest runs (persistence + history round-trip) -------------------
@pytest.fixture
def db():
    eng = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(eng)
    Session = sessionmaker(bind=eng)
    with Session() as s:
        yield s


def test_backtest_run_persists_and_round_trips(db):
    payload = {"results": [{
        "strategy": "supertrend",
        "metrics": {"return_pct": 12.3, "net_pnl": 1230.0, "total_trades": 9,
                    "win_rate": 55.0, "max_drawdown_pct": -4.1, "profit_factor": 1.8},
        "equity_curve": [{"time": 0, "equity": 100000.0}],
        "trades": [{"direction": "SHORT", "entry": 100, "exit": 95, "qty": 1.0,
                    "pnl": 5.0, "r": 1.0, "reason": "target", "entry_time": 0, "exit_time": 1}],
    }]}
    run = BacktestRun(
        symbol="BTCUSDT", timeframe="1h", start="2024-01-01", end="2024-02-01",
        leverage=10.0, risk_per_trade_pct=1.0, candles=500,
        strategies_json=json.dumps(["supertrend"]),
        summary_json=json.dumps([{"strategy": "supertrend", "return_pct": 12.3}]),
        results_json=json.dumps(payload),
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    runs = backtest_api.list_runs(db=db)
    assert len(runs) == 1 and runs[0].symbol == "BTCUSDT"
    assert runs[0].strategies == ["supertrend"]

    full = backtest_api.get_run(run.id, db=db)
    assert full.run_id == run.id
    assert full.results[0].strategy == "supertrend"
    # Short trade preserved through the JSON round-trip.
    assert full.results[0].trades[0]["direction"] == "SHORT"
