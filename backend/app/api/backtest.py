"""Backtesting API — run one or more strategies over a date range."""
from __future__ import annotations

import json
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.backtest import autoselect, robustness
from app.backtest.engine import BacktestConfig, run_backtest
from app.config import settings
from app.data.binance import load_candles
from app.db.session import get_db
from app.models import BacktestRun
from app.schemas import (
    BacktestRequest,
    BacktestResponse,
    BacktestRunSummary,
    RobustnessRequest,
    StrategyResult,
)
from app.strategies.base import get_strategy

router = APIRouter(prefix="/api/backtest", tags=["backtest"])


def _iso_to_ms(value: str) -> int:
    try:
        dt = datetime.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(422, f"Invalid date '{value}': {exc}") from exc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return int(dt.timestamp() * 1000)


@router.post("", response_model=BacktestResponse)
def backtest(req: BacktestRequest, db: Session = Depends(get_db)) -> BacktestResponse:
    if req.symbol not in settings.symbols:
        raise HTTPException(422, f"Unknown symbol. Allowed: {settings.symbols}")
    if req.timeframe not in settings.timeframes:
        raise HTTPException(422, f"Unknown timeframe. Allowed: {settings.timeframes}")

    start_ms = _iso_to_ms(req.start)
    end_ms = _iso_to_ms(req.end)
    if end_ms <= start_ms:
        raise HTTPException(422, "end must be after start")

    df = load_candles(req.symbol, req.timeframe, start_ms, end_ms)
    if df.empty or len(df) < 50:
        raise HTTPException(
            422, "Not enough candles for this window (need >= 50). Try a wider range."
        )

    cfg = BacktestConfig()
    if req.leverage is not None:
        cfg.leverage = min(req.leverage, settings.max_leverage)
    if req.risk_per_trade_pct is not None:
        cfg.risk_per_trade_pct = req.risk_per_trade_pct

    results: list[StrategyResult] = []
    for name in req.strategies:
        try:
            get_strategy(name)
        except KeyError as exc:
            raise HTTPException(422, str(exc)) from exc
        overrides = (req.params or {}).get(name)
        res = run_backtest(req.symbol, req.timeframe, df, name, overrides, cfg)
        results.append(
            StrategyResult(
                strategy=name,
                metrics=res.metrics,
                equity_curve=res.equity_curve,
                trades=res.trades,
                benchmark_curve=res.benchmark_curve,
            )
        )

    # Persist the run so it can be viewed later.
    summary = [
        {"strategy": r.strategy, "return_pct": r.metrics.get("return_pct"),
         "net_pnl": r.metrics.get("net_pnl"), "total_trades": r.metrics.get("total_trades"),
         "win_rate": r.metrics.get("win_rate"), "max_drawdown_pct": r.metrics.get("max_drawdown_pct"),
         "profit_factor": r.metrics.get("profit_factor")}
        for r in results
    ]
    results_payload = {"results": [r.model_dump() for r in results]}
    run = BacktestRun(
        symbol=req.symbol,
        timeframe=req.timeframe,
        start=req.start,
        end=req.end,
        leverage=cfg.leverage,
        risk_per_trade_pct=cfg.risk_per_trade_pct,
        candles=len(df),
        strategies_json=json.dumps(req.strategies),
        summary_json=json.dumps(summary),
        results_json=json.dumps(results_payload),
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    return BacktestResponse(
        run_id=run.id,
        symbol=req.symbol,
        timeframe=req.timeframe,
        start=req.start,
        end=req.end,
        candles=len(df),
        results=results,
    )


def _load_for_robustness(req: RobustnessRequest):
    """Validate a robustness request and return (df, cfg). Raises HTTPException."""
    if req.symbol not in settings.symbols:
        raise HTTPException(422, f"Unknown symbol. Allowed: {settings.symbols}")
    if req.timeframe not in settings.timeframes:
        raise HTTPException(422, f"Unknown timeframe. Allowed: {settings.timeframes}")
    try:
        get_strategy(req.strategy)
    except KeyError as exc:
        raise HTTPException(422, str(exc)) from exc
    start_ms, end_ms = _iso_to_ms(req.start), _iso_to_ms(req.end)
    if end_ms <= start_ms:
        raise HTTPException(422, "end must be after start")
    df = load_candles(req.symbol, req.timeframe, start_ms, end_ms)
    if df.empty or len(df) < 100:
        raise HTTPException(422, "Need >= 100 candles for robustness analysis. Widen the range.")
    cfg = BacktestConfig()
    if req.leverage is not None:
        cfg.leverage = min(req.leverage, settings.max_leverage)
    if req.risk_per_trade_pct is not None:
        cfg.risk_per_trade_pct = req.risk_per_trade_pct
    return df, cfg


@router.post("/sweep")
def sweep(req: RobustnessRequest) -> dict:
    df, cfg = _load_for_robustness(req)
    return robustness.parameter_sweep(
        req.symbol, req.timeframe, df, req.strategy, req.param_grid, cfg, req.metric
    )


@router.post("/oos")
def oos(req: RobustnessRequest) -> dict:
    df, cfg = _load_for_robustness(req)
    return robustness.out_of_sample(
        req.symbol, req.timeframe, df, req.strategy, req.param_grid, cfg, req.metric, req.train_frac
    )


@router.post("/walkforward")
def walkforward(req: RobustnessRequest) -> dict:
    df, cfg = _load_for_robustness(req)
    return robustness.walk_forward(
        req.symbol, req.timeframe, df, req.strategy, req.param_grid, cfg, req.metric, req.folds
    )


@router.post("/montecarlo")
def montecarlo(req: RobustnessRequest) -> dict:
    df, cfg = _load_for_robustness(req)
    res = run_backtest(req.symbol, req.timeframe, df, req.strategy, req.params, cfg)
    mc = robustness.monte_carlo(res.trades, cfg.initial_capital, req.n_iter)
    if mc is None:
        raise HTTPException(422, "Not enough trades (need >= 5) for Monte Carlo.")
    return {"trades": len(res.trades), **mc}


class AutoSelectRequest(BaseModel):
    start: str
    end: str
    symbols: list[str] | None = None
    timeframes: list[str] | None = None
    strategies: list[str] | None = None
    metric: str = "sharpe"
    min_trades: int = 15
    require_beat_buyhold: bool = False
    oos_check: bool = True
    top_n: int = 5
    promote: bool = False
    leverage: float | None = None
    risk_per_trade_pct: float | None = None


@router.post("/autoselect")
def autoselect_endpoint(req: AutoSelectRequest, db: Session = Depends(get_db)) -> dict:
    """Screen every coin × strategy × timeframe over a window, rank by performance
    with anti-overfit gates, and optionally auto-promote the recommended top N."""
    symbols = req.symbols or settings.symbols
    timeframes = req.timeframes or ["1h"]
    strategies = req.strategies or autoselect.all_strategy_names()

    bad_sym = [s for s in symbols if s not in settings.symbols]
    if bad_sym:
        raise HTTPException(422, f"Unknown symbols {bad_sym}. Allowed: {settings.symbols}")
    bad_tf = [t for t in timeframes if t not in settings.timeframes]
    if bad_tf:
        raise HTTPException(422, f"Unknown timeframes {bad_tf}. Allowed: {settings.timeframes}")
    for name in strategies:
        try:
            get_strategy(name)
        except KeyError as exc:
            raise HTTPException(422, str(exc)) from exc
    if _iso_to_ms(req.end) <= _iso_to_ms(req.start):
        raise HTTPException(422, "end must be after start")

    cfg = BacktestConfig()
    if req.leverage is not None:
        cfg.leverage = min(req.leverage, settings.max_leverage)
    if req.risk_per_trade_pct is not None:
        cfg.risk_per_trade_pct = req.risk_per_trade_pct

    return autoselect.auto_select(
        db, symbols, timeframes, strategies, req.start, req.end,
        metric=req.metric, min_trades=req.min_trades,
        require_beat_buyhold=req.require_beat_buyhold, oos_check=req.oos_check,
        cfg=cfg, top_n=req.top_n, promote=req.promote,
    )


@router.get("/runs", response_model=list[BacktestRunSummary])
def list_runs(limit: int = 50, db: Session = Depends(get_db)) -> list[BacktestRunSummary]:
    rows = db.execute(
        select(BacktestRun).order_by(BacktestRun.id.desc()).limit(min(limit, 200))
    ).scalars().all()
    return [
        BacktestRunSummary(
            id=r.id,
            created_at=r.created_at.isoformat(),
            symbol=r.symbol,
            timeframe=r.timeframe,
            start=r.start,
            end=r.end,
            leverage=r.leverage,
            risk_per_trade_pct=r.risk_per_trade_pct,
            candles=r.candles,
            strategies=json.loads(r.strategies_json or "[]"),
            summary=json.loads(r.summary_json or "[]"),
        )
        for r in rows
    ]


@router.get("/runs/{run_id}", response_model=BacktestResponse)
def get_run(run_id: int, db: Session = Depends(get_db)) -> BacktestResponse:
    run = db.get(BacktestRun, run_id)
    if run is None:
        raise HTTPException(404, "Backtest run not found")
    payload = json.loads(run.results_json or "{}")
    results = [StrategyResult(**r) for r in payload.get("results", [])]
    return BacktestResponse(
        run_id=run.id,
        symbol=run.symbol,
        timeframe=run.timeframe,
        start=run.start,
        end=run.end,
        candles=run.candles,
        results=results,
    )
