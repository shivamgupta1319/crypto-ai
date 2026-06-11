"""FastAPI application entrypoint for crypto-ai.

Phase 0/1: serves config, market outlook, strategy catalog, and backtesting.
Later phases add the live scanner, paper-trading, news, and WebSocket push.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import agent, ai, backtest, dashboard, news, portfolio, signals, strategies
from app.api import settings as settings_api
from app.config import settings
from app.data.stream import start_price_stream, stop_price_stream
from app.db.session import init_db
from app.live.scheduler import start_scheduler, stop_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    # Importing the strategy package registers the full library.
    import app.strategies  # noqa: F401

    # Apply any user-saved settings overrides onto the live config.
    from app.db.session import SessionLocal
    from app.settings_store import load_overrides

    with SessionLocal() as db:
        load_overrides(db)

    start_price_stream()
    start_scheduler()
    try:
        yield
    finally:
        stop_scheduler()
        stop_price_stream()


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)

# Vite dev server default origins.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(dashboard.router)
app.include_router(strategies.router)
app.include_router(backtest.router)
app.include_router(signals.router)
app.include_router(portfolio.router)
app.include_router(news.router)
app.include_router(ai.router)
app.include_router(settings_api.router)
app.include_router(agent.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "app": settings.app_name}
