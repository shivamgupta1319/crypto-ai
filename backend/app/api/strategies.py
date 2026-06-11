"""Strategy catalog + active-strategy promotion (backtest -> live config)."""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db.session import get_db
from app.models import ActiveStrategy
from app.schemas import ActiveStrategyOut, PromoteRequest, StrategyInfo
from app.strategies.base import all_strategies, get_strategy

router = APIRouter(prefix="/api/strategies", tags=["strategies"])


@router.get("", response_model=list[StrategyInfo])
def list_strategies() -> list[StrategyInfo]:
    return [
        StrategyInfo(
            name=s.name,
            description=s.description,
            default_params=s.default_params,
            suited_for=s.suited_for,
        )
        for s in all_strategies()
    ]


@router.get("/active", response_model=list[ActiveStrategyOut])
def list_active(db: Session = Depends(get_db)) -> list[ActiveStrategyOut]:
    rows = db.execute(select(ActiveStrategy)).scalars().all()
    return [
        ActiveStrategyOut(
            id=r.id,
            symbol=r.symbol,
            timeframe=r.timeframe,
            strategy=r.strategy,
            params=json.loads(r.params_json or "{}"),
            enabled=bool(r.enabled),
        )
        for r in rows
    ]


@router.post("/promote", response_model=ActiveStrategyOut)
def promote(req: PromoteRequest, db: Session = Depends(get_db)) -> ActiveStrategyOut:
    """Promote a {symbol, timeframe, strategy} combo to the live config.

    The live scanner and paper-trader (later phases) read this table.
    """
    if req.symbol not in settings.symbols:
        raise HTTPException(422, f"Unknown symbol. Allowed: {settings.symbols}")
    if req.timeframe not in settings.timeframes:
        raise HTTPException(422, f"Unknown timeframe. Allowed: {settings.timeframes}")
    try:
        get_strategy(req.strategy)
    except KeyError as exc:
        raise HTTPException(422, str(exc)) from exc

    existing = db.execute(
        select(ActiveStrategy).where(
            ActiveStrategy.symbol == req.symbol,
            ActiveStrategy.timeframe == req.timeframe,
            ActiveStrategy.strategy == req.strategy,
        )
    ).scalar_one_or_none()

    params_json = json.dumps(req.params or {})
    if existing:
        existing.params_json = params_json
        existing.enabled = 1
        row = existing
    else:
        row = ActiveStrategy(
            symbol=req.symbol,
            timeframe=req.timeframe,
            strategy=req.strategy,
            params_json=params_json,
            enabled=1,
        )
        db.add(row)
    db.commit()
    db.refresh(row)

    return ActiveStrategyOut(
        id=row.id,
        symbol=row.symbol,
        timeframe=row.timeframe,
        strategy=row.strategy,
        params=json.loads(row.params_json),
        enabled=bool(row.enabled),
    )


@router.delete("/active/{active_id}")
def delete_active(active_id: int, db: Session = Depends(get_db)) -> dict[str, bool]:
    row = db.get(ActiveStrategy, active_id)
    if not row:
        raise HTTPException(404, "Active strategy not found")
    db.delete(row)
    db.commit()
    return {"deleted": True}
