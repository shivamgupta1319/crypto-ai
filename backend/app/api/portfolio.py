"""Portfolio API — paper account summary, open positions, history, equity curve."""
from __future__ import annotations

import asyncio
import csv
import io
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.live.manager import manager
from app.portfolio import engine
from app.schemas import AccountSummary, ClosedTrade, OpenPosition

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


@router.get("/summary", response_model=AccountSummary)
def summary(db: Session = Depends(get_db)) -> AccountSummary:
    return AccountSummary(**engine.account_summary(db))


@router.get("/positions", response_model=list[OpenPosition])
def positions(db: Session = Depends(get_db)) -> list[OpenPosition]:
    return [OpenPosition(**p) for p in engine.open_positions_view(db)]


@router.get("/trades", response_model=list[ClosedTrade])
def trades(limit: int = 100, db: Session = Depends(get_db)) -> list[ClosedTrade]:
    return [ClosedTrade(**t) for t in engine.closed_trades_view(db, limit)]


@router.get("/equity-curve")
def equity_curve(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return engine.equity_curve(db)


@router.post("/positions/{position_id}/close")
async def close_position(position_id: int) -> dict[str, Any]:
    """Manually close an open position at the current market price."""
    ev = await asyncio.to_thread(engine.close_trade_by_id, position_id)
    if ev is None:
        raise HTTPException(404, "Open position not found")
    await manager.broadcast({"type": "trade_closed", "data": ev})
    return ev


@router.get("/attribution")
def attribution(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return engine.strategy_attribution(db)


@router.get("/risk")
def risk(db: Session = Depends(get_db)) -> dict[str, Any]:
    return engine.risk_view(db)


@router.post("/reset")
def reset(db: Session = Depends(get_db)) -> dict[str, Any]:
    """Wipe the paper account (delete all paper trades). Active strategies are kept."""
    deleted = engine.reset_account(db)
    return {"deleted": deleted}


@router.get("/export")
def export_csv(db: Session = Depends(get_db)) -> StreamingResponse:
    """Download closed trades as CSV."""
    rows = engine.closed_trades_view(db, limit=10000)
    buf = io.StringIO()
    cols = ["id", "symbol", "strategy", "direction", "qty", "entry_price",
            "exit_price", "pnl", "fees", "opened_at", "closed_at"]
    writer = csv.DictWriter(buf, fieldnames=cols)
    writer.writeheader()
    for r in rows:
        writer.writerow({k: r.get(k) for k in cols})
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]), media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=cryptoai_trades.csv"},
    )
