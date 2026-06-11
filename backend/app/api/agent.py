"""Adaptive Intelligence Layer API (N10).

Exposes the feature store, regime, meta-label model, walk-forward optimizer,
allocation analysis, and the agent's proposal queue. Everything is advisory:
proposals require explicit human approval to take effect.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.backtest.engine import BacktestConfig
from app.config import settings
from app.data.binance import load_candles
from app.db.session import get_db
from app.learning import agent as agent_brain
from app.learning import dataset, metalabel, optimizer
from app.regime import current_regime, regime_label
from app.strategies.base import get_strategy, merge_params

router = APIRouter(prefix="/api/agent", tags=["agent"])


def _iso_to_ms(value: str) -> int:
    try:
        dt = datetime.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(422, f"Invalid date '{value}': {exc}") from exc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return int(dt.timestamp() * 1000)


# ---- Stage 1: feature store --------------------------------------------------
class BuildRequest(BaseModel):
    strategy: str
    symbol: str
    timeframe: str = "1h"
    start: str
    end: str


@router.get("/dataset")
def dataset_view(db: Session = Depends(get_db)) -> dict[str, Any]:
    return dataset.dataset_stats(db)


@router.post("/dataset/build")
def dataset_build(req: BuildRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Cold-start: build labeled samples from a strategy over a candle window."""
    if req.symbol not in settings.symbols:
        raise HTTPException(422, f"Unknown symbol. Allowed: {settings.symbols}")
    start_ms, end_ms = _iso_to_ms(req.start), _iso_to_ms(req.end)
    if end_ms <= start_ms:
        raise HTTPException(422, "end must be after start")
    df = load_candles(req.symbol, req.timeframe, start_ms, end_ms)
    if df.empty or len(df) < 80:
        raise HTTPException(422, "Need >= 80 candles to build samples. Widen the range.")
    samples = dataset.build_samples(req.symbol, req.timeframe, df, req.strategy)
    inserted = dataset.persist_samples(db, samples)
    return {"built": len(samples), "inserted": inserted, "stats": dataset.dataset_stats(db)}


# ---- Stage 2: regime ---------------------------------------------------------
@router.get("/regime")
def regime_view() -> dict[str, Any]:
    """Current regime per symbol (1h)."""
    import time

    out = []
    now = int(time.time() * 1000)
    for sym in settings.symbols:
        try:
            df = load_candles(sym, "1h", now - 400 * 3_600_000, now)
            reg = current_regime(df)
        except Exception:
            reg = "ranging"
        out.append({"symbol": sym, "regime": reg, "label": regime_label(reg)})
    return {"regimes": out}


# ---- Stage 3: meta-labeling --------------------------------------------------
class TrainRequest(BaseModel):
    strategy: str | None = None  # None -> global model across all strategies


class EvaluateRequest(BaseModel):
    strategy: str
    symbol: str
    timeframe: str = "1h"
    start: str
    end: str
    threshold: float = 0.55


@router.get("/model")
def model_view() -> dict[str, Any]:
    return metalabel.model_status()


@router.post("/model/train")
def model_train(req: TrainRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        return metalabel.train(db, strategy=req.strategy)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/model/evaluate")
def model_evaluate(req: EvaluateRequest) -> dict[str, Any]:
    """Backtest with vs without the meta-label filter over a window."""
    if req.symbol not in settings.symbols:
        raise HTTPException(422, f"Unknown symbol. Allowed: {settings.symbols}")
    start_ms, end_ms = _iso_to_ms(req.start), _iso_to_ms(req.end)
    if end_ms <= start_ms:
        raise HTTPException(422, "end must be after start")
    df = load_candles(req.symbol, req.timeframe, start_ms, end_ms)
    if df.empty or len(df) < 80:
        raise HTTPException(422, "Need >= 80 candles. Widen the range.")
    return metalabel.evaluate_filter(
        req.symbol, req.timeframe, df, req.strategy, None, BacktestConfig(), req.threshold
    )


# ---- Stage 4: walk-forward optimizer ----------------------------------------
class OptimizeRequest(BaseModel):
    strategy: str
    symbol: str
    timeframe: str = "1h"
    start: str
    end: str


@router.post("/optimize")
def optimize(req: OptimizeRequest) -> dict[str, Any]:
    if req.symbol not in settings.symbols:
        raise HTTPException(422, f"Unknown symbol. Allowed: {settings.symbols}")
    try:
        get_strategy(req.strategy)
    except KeyError as exc:
        raise HTTPException(422, str(exc)) from exc
    start_ms, end_ms = _iso_to_ms(req.start), _iso_to_ms(req.end)
    if end_ms <= start_ms:
        raise HTTPException(422, "end must be after start")
    df = load_candles(req.symbol, req.timeframe, start_ms, end_ms)
    current = merge_params(req.strategy, None)
    return optimizer.propose_params(
        req.symbol, req.timeframe, df, req.strategy, current, BacktestConfig()
    )


# ---- Stage 6: agent orchestrator + proposals --------------------------------
@router.get("/overview")
def overview(db: Session = Depends(get_db)) -> dict[str, Any]:
    return agent_brain.overview(db)


@router.post("/review")
def review(db: Session = Depends(get_db)) -> dict[str, Any]:
    """Run a review cycle: regenerate proposals + refresh the narrative."""
    return agent_brain.review_cycle(db)


@router.get("/proposals")
def proposals(status: str | None = None, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return agent_brain.list_proposals(db, status=status)


@router.post("/proposals/{proposal_id}/approve")
def approve(proposal_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    p = agent_brain.approve(db, proposal_id)
    if p is None:
        raise HTTPException(404, "Pending proposal not found")
    return agent_brain.proposal_dict(p)


@router.post("/proposals/{proposal_id}/reject")
def reject(proposal_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    p = agent_brain.reject(db, proposal_id)
    if p is None:
        raise HTTPException(404, "Pending proposal not found")
    return agent_brain.proposal_dict(p)


@router.post("/proposals/{proposal_id}/revert")
def revert(proposal_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    p = agent_brain.revert(db, proposal_id)
    if p is None:
        raise HTTPException(404, "Approved proposal not found")
    return agent_brain.proposal_dict(p)
