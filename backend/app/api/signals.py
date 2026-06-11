"""Live signals API — recent signals, manual scan trigger, and WebSocket feed."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.live.cycle import run_scan_cycle
from app.live.manager import manager
from app.live.scanner import current_setups, get_scan_status
from app.models import Signal
from app.schemas import SignalOut

router = APIRouter(prefix="/api/signals", tags=["signals"])


@router.get("", response_model=list[SignalOut])
def recent_signals(limit: int = 50, db: Session = Depends(get_db)) -> list[SignalOut]:
    rows = db.execute(
        select(Signal).order_by(Signal.id.desc()).limit(min(limit, 200))
    ).scalars().all()
    return [
        SignalOut(
            id=r.id,
            symbol=r.symbol,
            timeframe=r.timeframe,
            strategy=r.strategy,
            direction=r.direction,
            entry=r.entry,
            stop=r.stop,
            target=r.target,
            confidence=r.confidence,
            bar_time=r.bar_time,
            created_at=r.created_at.isoformat(),
        )
        for r in rows
    ]


@router.get("/status")
def scan_status() -> dict:
    """Scanner liveness: last scan time, # monitored strategies, interval."""
    return get_scan_status()


@router.get("/current")
async def current(scope: str = "active") -> dict:
    """Live state of monitored strategies (always populated, unlike the feed).

    scope=active → promoted strategies; scope=all → whole library preview.
    """
    if scope not in ("active", "all"):
        scope = "active"
    setups = await asyncio.to_thread(current_setups, scope)
    return {"scope": scope, "setups": setups, "count": len(setups)}


@router.post("/scan")
async def scan_now() -> dict:
    """Manually trigger one scan+trade cycle and broadcast the results."""
    result = await asyncio.to_thread(run_scan_cycle)
    for sig in result["signals"]:
        await manager.broadcast({"type": "signal", "data": sig})
    for ev in result["opened"]:
        await manager.broadcast({"type": "trade_opened", "data": ev})
    for ev in result["closed"]:
        await manager.broadcast({"type": "trade_closed", "data": ev})
    return {
        "new_signals": result["signals"],
        "count": len(result["signals"]),
        "opened": len(result["opened"]),
        "closed": len(result["closed"]),
    }


@router.websocket("/ws")
async def signals_ws(ws: WebSocket) -> None:
    await manager.connect(ws)
    try:
        # Keep the socket open; we only push. Read loop detects disconnects.
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        await manager.disconnect(ws)
    except Exception:
        await manager.disconnect(ws)
