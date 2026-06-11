"""One scan+trade cycle: detect signals, then paper-trade them.

Shared by the scheduler (every 60s) and the manual /api/signals/scan endpoint
so both paths behave identically.
"""
from __future__ import annotations

from typing import Any

from app import alerts
from app.db.session import SessionLocal
from app.live.scanner import scan_active
from app.portfolio.engine import run_paper_cycle


def run_scan_cycle() -> dict[str, Any]:
    new_signals = scan_active()
    with SessionLocal() as db:
        trade_events = run_paper_cycle(db, new_signals)

    # Best-effort alerts (each call no-ops unless Telegram/Discord is configured).
    for s in new_signals:
        alerts.alert_signal(s)
    for ev in trade_events["opened"]:
        alerts.alert_trade_opened(ev)
    for ev in trade_events["closed"]:
        alerts.alert_trade_closed(ev)

    return {
        "signals": new_signals,
        "opened": trade_events["opened"],
        "closed": trade_events["closed"],
    }
