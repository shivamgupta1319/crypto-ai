"""Binance USDⓈ-M futures market data — public endpoints only (no API key).

Fetches klines (candles), caches them in SQLite, and returns pandas DataFrames.
The same cached candles feed both the backtester and the live scanner.
"""
from __future__ import annotations

import logging
import time

import httpx
import pandas as pd
from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.config import settings
from app.db.session import SessionLocal
from app.models import Candle

logger = logging.getLogger("cryptoai.binance")


def _get_json(url: str, params: dict, timeout: float = 20.0, retries: int = 3):
    """GET with retry + exponential backoff (handles transient errors / 429 / 5xx)."""
    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            resp = httpx.get(url, params=params, timeout=timeout)
            if resp.status_code in (418, 429) or resp.status_code >= 500:
                raise httpx.HTTPStatusError("retryable", request=resp.request, response=resp)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as exc:
            last_exc = exc
            if attempt < retries - 1:
                time.sleep(0.5 * (2 ** attempt))  # 0.5s, 1s, 2s
    assert last_exc is not None
    logger.warning("binance GET failed after %d attempts: %s", retries, url)
    raise last_exc

# Binance futures kline interval -> milliseconds (used for pagination).
_TF_MS: dict[str, int] = {
    "1m": 60_000,
    "5m": 5 * 60_000,
    "15m": 15 * 60_000,
    "30m": 30 * 60_000,
    "1h": 60 * 60_000,
    "4h": 4 * 60 * 60_000,
    "1d": 24 * 60 * 60_000,
}

_OHLCV_COLS = ["open_time", "open", "high", "low", "close", "volume"]


def tf_to_ms(timeframe: str) -> int:
    if timeframe not in _TF_MS:
        raise ValueError(f"Unsupported timeframe: {timeframe}")
    return _TF_MS[timeframe]


def _fetch_klines_page(
    symbol: str, timeframe: str, start_ms: int, end_ms: int, limit: int = 1500
) -> list[list]:
    """One page of raw klines from Binance futures REST."""
    url = f"{settings.binance_futures_base}/fapi/v1/klines"
    params = {
        "symbol": symbol,
        "interval": timeframe,
        "startTime": start_ms,
        "endTime": end_ms,
        "limit": limit,
    }
    return _get_json(url, params, timeout=20.0)


def fetch_candles(symbol: str, timeframe: str, start_ms: int, end_ms: int) -> int:
    """Fetch candles in [start_ms, end_ms], upsert into the cache.

    Returns the number of candles fetched from the API this call.
    """
    step = tf_to_ms(timeframe)
    cursor = start_ms
    fetched = 0
    with SessionLocal() as db:
        while cursor < end_ms:
            rows = _fetch_klines_page(symbol, timeframe, cursor, end_ms)
            if not rows:
                break
            payload = [
                {
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "open_time": int(r[0]),
                    "open": float(r[1]),
                    "high": float(r[2]),
                    "low": float(r[3]),
                    "close": float(r[4]),
                    "volume": float(r[5]),
                }
                for r in rows
            ]
            stmt = sqlite_insert(Candle).values(payload)
            stmt = stmt.on_conflict_do_nothing(
                index_elements=["symbol", "timeframe", "open_time"]
            )
            db.execute(stmt)
            db.commit()
            fetched += len(rows)

            last_open = int(rows[-1][0])
            next_cursor = last_open + step
            if next_cursor <= cursor:  # safety against stalls
                break
            cursor = next_cursor
            if len(rows) < 1500:  # reached the end of available data
                break
            time.sleep(0.15)  # be gentle with the public endpoint
    return fetched


def load_candles(
    symbol: str, timeframe: str, start_ms: int, end_ms: int, ensure: bool = True
) -> pd.DataFrame:
    """Return a candle DataFrame for the window, fetching gaps if ``ensure``.

    Columns: open_time (ms), open, high, low, close, volume, and a UTC
    ``time`` DatetimeIndex.
    """
    if ensure:
        fetch_candles(symbol, timeframe, start_ms, end_ms)

    with SessionLocal() as db:
        stmt = (
            select(
                Candle.open_time,
                Candle.open,
                Candle.high,
                Candle.low,
                Candle.close,
                Candle.volume,
            )
            .where(
                Candle.symbol == symbol,
                Candle.timeframe == timeframe,
                Candle.open_time >= start_ms,
                Candle.open_time <= end_ms,
            )
            .order_by(Candle.open_time.asc())
        )
        rows = db.execute(stmt).all()

    df = pd.DataFrame(rows, columns=_OHLCV_COLS)
    if not df.empty:
        df["time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
        df = df.set_index("time")
    return df


def latest_price(symbol: str) -> float:
    """Latest price for a symbol — prefers the live WS cache, falls back to REST."""
    from app.data import stream

    cached = stream.get_cached_price(symbol)
    if cached is not None:
        return cached
    url = f"{settings.binance_futures_base}/fapi/v1/ticker/price"
    return float(_get_json(url, {"symbol": symbol}, timeout=10.0)["price"])
