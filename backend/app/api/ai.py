"""AI API — advisory market commentary, portfolio Q&A, and backtest explainer.

Strictly advisory: every endpoint only returns text. Nothing here sizes, opens,
or closes a position. When no provider key is configured the endpoints return
``enabled: false`` with a hint instead of failing.
"""
from __future__ import annotations

import json
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.ai import AIError, AIRateLimited, ai_status, complete
from app.ai import context as ctx
from app.config import settings
from app.db.session import get_db
from app.market import build_outlook
from app.models import BacktestRun
from app.news import get_news
from app.portfolio import engine

router = APIRouter(prefix="/api/ai", tags=["ai"])

# Daily commentary is expensive (LLM call + market/news fetch); cache briefly.
_COMMENTARY_TTL = 600.0  # seconds
_commentary_cache: dict[str, Any] = {}


def _disabled_payload() -> dict[str, Any]:
    st = ai_status()
    return {
        **st,
        "text": None,
        "hint": "AI is not configured. Add CRYPTOAI_GEMINI_API_KEY or "
        "CRYPTOAI_OPENROUTER_API_KEY to backend/.env (both have free tiers).",
    }


def _complete_or_http(prompt: str) -> str:
    """Run a completion, mapping provider failures to clean HTTP errors:
    429 for rate limits (so the UI says 'wait a minute'), 502 otherwise."""
    try:
        text = complete(prompt)
    except AIRateLimited as exc:
        raise HTTPException(429, str(exc)) from exc
    except AIError as exc:
        raise HTTPException(502, str(exc)) from exc
    if text is None:
        raise HTTPException(502, "AI provider returned no response. Try again shortly.")
    return text


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)


class ExplainRequest(BaseModel):
    run_id: int


@router.get("/status")
def status() -> dict[str, Any]:
    return ai_status()


@router.post("/commentary")
def commentary(refresh: bool = False, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Plain-English read of the market + your paper book. Cached ~10 min."""
    if not settings.ai_enabled:
        return _disabled_payload()

    now = time.time()
    cached = _commentary_cache.get("payload")
    if cached and not refresh and (now - _commentary_cache.get("at", 0)) < _COMMENTARY_TTL:
        return {**cached, "cached": True}

    outlook = build_outlook()
    summary = engine.account_summary(db)
    positions = engine.open_positions_view(db)
    attribution = engine.strategy_attribution(db)
    news = get_news(limit=15)

    prompt = (
        "Write a short daily market commentary (<= 180 words) for my crypto "
        "futures paper account. Cover: overall market tone, anything notable "
        "per coin, what the news sentiment suggests, and one or two risks to "
        "watch given my open positions. Do not tell me to place specific "
        "trades.\n\n"
        f"=== MARKET ===\n{ctx.format_outlook(outlook)}\n\n"
        f"=== MY ACCOUNT ===\n{ctx.format_account(summary, attribution)}\n\n"
        f"=== MY POSITIONS ===\n{ctx.format_positions(positions)}\n\n"
        f"=== NEWS ===\n{ctx.format_news(news)}\n"
    )
    text = _complete_or_http(prompt)

    payload = {**ai_status(), "text": text, "generated_at": now, "cached": False}
    _commentary_cache["payload"] = payload
    _commentary_cache["at"] = now
    return payload


@router.post("/ask")
def ask(req: AskRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Natural-language Q&A grounded in your paper account state."""
    if not settings.ai_enabled:
        return _disabled_payload()

    summary = engine.account_summary(db)
    positions = engine.open_positions_view(db)
    attribution = engine.strategy_attribution(db)
    recent = engine.closed_trades_view(db, limit=20)
    recent_lines = "\n".join(
        f"- {t['symbol']} {t['direction']} pnl {t['pnl']} [{t['strategy']}]" for t in recent
    ) or "No closed trades yet."

    prompt = (
        "Answer the user's question about their paper trading account using only "
        "the data below. Be concise and factual; if the data can't answer it, say "
        "so. Never recommend placing a specific real-money trade.\n\n"
        f"=== ACCOUNT ===\n{ctx.format_account(summary, attribution)}\n\n"
        f"=== OPEN POSITIONS ===\n{ctx.format_positions(positions)}\n\n"
        f"=== RECENT CLOSED TRADES ===\n{recent_lines}\n\n"
        f"=== QUESTION ===\n{req.question.strip()}\n"
    )
    text = _complete_or_http(prompt)
    return {**ai_status(), "text": text, "question": req.question.strip()}


@router.post("/backtest-explain")
def backtest_explain(req: ExplainRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Plain-English summary of a stored backtest run + overfitting caution flags."""
    if not settings.ai_enabled:
        return _disabled_payload()

    run = db.get(BacktestRun, req.run_id)
    if run is None:
        raise HTTPException(404, "Backtest run not found")
    run_dict = {
        "symbol": run.symbol,
        "timeframe": run.timeframe,
        "start": run.start,
        "end": run.end,
        "leverage": run.leverage,
        "risk_per_trade_pct": run.risk_per_trade_pct,
        "candles": run.candles,
        "summary": json.loads(run.summary_json or "[]"),
    }

    prompt = (
        "Explain this backtest in plain English (<= 160 words) for someone "
        "deciding whether to trust it. Summarise how each strategy did, then list "
        "any OVERFITTING / red-flag concerns you notice (e.g. win rate > 80%, "
        "profit factor > 4, suspiciously low drawdown, very few trades, short "
        "window). End with one sentence on what to validate next (out-of-sample / "
        "walk-forward). Be skeptical, not promotional.\n\n"
        f"{ctx.format_backtest_run(run_dict)}\n"
    )
    text = _complete_or_http(prompt)
    return {**ai_status(), "text": text, "run_id": req.run_id}
