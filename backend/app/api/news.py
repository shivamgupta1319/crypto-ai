"""News API — aggregated free RSS, optionally filtered by coin."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.config import settings
from app.news import get_news
from app.schemas import NewsItem

router = APIRouter(prefix="/api/news", tags=["news"])


@router.get("", response_model=list[NewsItem])
def news(coin: str | None = None, limit: int = 40) -> list[NewsItem]:
    if coin and coin not in settings.symbols:
        raise HTTPException(422, f"Unknown coin. Allowed: {settings.symbols}")
    return [NewsItem(**i) for i in get_news(coin, limit)]
