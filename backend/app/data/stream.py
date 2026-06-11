"""Live mark-price stream from Binance futures (free, no key).

Maintains an in-memory {symbol: price} cache fed by a WebSocket so the paper
trader and scanner get fresh prices without hammering the REST API. Fully
optional: if the socket can't connect, the cache stays empty and callers fall
back to REST (see app.data.binance.latest_price).
"""
from __future__ import annotations

import asyncio
import json
import logging
import time

from app.config import settings

logger = logging.getLogger("cryptoai.stream")

# symbol -> (price, epoch_seconds)
_prices: dict[str, tuple[float, float]] = {}
_task: asyncio.Task | None = None
_STALE_SECONDS = 30  # ignore cache entries older than this


def set_price(symbol: str, price: float) -> None:
    _prices[symbol] = (price, time.time())


def get_cached_price(symbol: str) -> float | None:
    entry = _prices.get(symbol)
    if entry is None:
        return None
    price, ts = entry
    if time.time() - ts > _STALE_SECONDS:
        return None
    return price


def _stream_url() -> str:
    streams = "/".join(f"{s.lower()}@markPrice@1s" for s in settings.symbols)
    return f"wss://fstream.binance.com/stream?streams={streams}"


async def _run() -> None:
    import websockets  # bundled with uvicorn[standard]

    url = _stream_url()
    while True:
        try:
            async with websockets.connect(url, ping_interval=20, close_timeout=5) as ws:
                logger.info("price stream connected")
                async for raw in ws:
                    try:
                        data = json.loads(raw).get("data", {})
                        sym = data.get("s")
                        price = data.get("p")
                        if sym and price is not None:
                            set_price(sym, float(price))
                    except (ValueError, KeyError):
                        continue
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning("price stream dropped; retrying in 5s", exc_info=True)
            await asyncio.sleep(5)


def start_price_stream() -> None:
    global _task
    if _task is not None or not settings.price_stream_enabled:
        return
    _task = asyncio.create_task(_run())


def stop_price_stream() -> None:
    global _task
    if _task is not None:
        _task.cancel()
        _task = None
