"""AsyncIO scheduler that periodically scans active strategies and broadcasts.

Runs inside FastAPI's event loop. The blocking scan (network + DB) is offloaded
to a threadpool so it never stalls the loop or WebSocket I/O.
"""
from __future__ import annotations

import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.config import settings
from app.live.cycle import run_scan_cycle
from app.live.manager import manager

logger = logging.getLogger("cryptoai.scanner")

SCAN_INTERVAL_SECONDS = settings.scan_interval_seconds

_scheduler: AsyncIOScheduler | None = None


async def _scan_job() -> None:
    try:
        result = await asyncio.to_thread(run_scan_cycle)
    except Exception:  # never let a bad cycle kill the scheduler
        logger.exception("scan cycle failed")
        return
    for sig in result["signals"]:
        await manager.broadcast({"type": "signal", "data": sig})
    for ev in result["opened"]:
        await manager.broadcast({"type": "trade_opened", "data": ev})
    for ev in result["closed"]:
        await manager.broadcast({"type": "trade_closed", "data": ev})
    if result["signals"] or result["opened"] or result["closed"]:
        logger.info(
            "cycle: %d signals, %d opened, %d closed",
            len(result["signals"]), len(result["opened"]), len(result["closed"]),
        )


def start_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        return
    _scheduler = AsyncIOScheduler()
    _scheduler.add_job(
        _scan_job,
        "interval",
        seconds=SCAN_INTERVAL_SECONDS,
        id="scan_active",
        max_instances=1,
        coalesce=True,
    )
    _scheduler.start()
    logger.info("scanner scheduler started (every %ss)", SCAN_INTERVAL_SECONDS)


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
