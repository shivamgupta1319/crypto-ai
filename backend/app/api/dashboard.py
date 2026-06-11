"""Dashboard API — market outlook and basic config exposure."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.config import settings
from app.data import derivatives
from app.market import build_outlook, correlation_matrix

router = APIRouter(prefix="/api", tags=["dashboard"])


@router.get("/config")
def get_config() -> dict:
    return {
        "symbols": settings.symbols,
        "timeframes": settings.timeframes,
        "initial_capital": settings.initial_capital,
        "display_currency": settings.display_currency,
        "default_leverage": settings.default_leverage,
        "max_leverage": settings.max_leverage,
        "risk_per_trade_pct": settings.risk_per_trade_pct,
    }


@router.get("/market/outlook")
def market_outlook() -> dict:
    return build_outlook()


@router.get("/market/derivatives")
def market_derivatives() -> dict[str, Any]:
    """Funding / open interest / long-short positioning per coin + global stats."""
    return {
        "coins": derivatives.derivatives_snapshot(),
        "global": derivatives.global_stats(),
    }


@router.get("/market/correlation")
def market_correlation(timeframe: str = "1h") -> dict[str, Any]:
    return correlation_matrix(timeframe)
