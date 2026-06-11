"""Free Binance futures derivatives data + CoinGecko global stats.

All endpoints are public (no API key, no card):
  - Funding rate     : /fapi/v1/premiumIndex            (current) + /fapi/v1/fundingRate (history)
  - Open interest    : /fapi/v1/openInterest            (current)
  - Long/short ratio : /futures/data/globalLongShortAccountRatio (recent, period-based)
  - Global mcap/dom  : CoinGecko /api/v3/global

Every fetch is best-effort: on any error it returns ``None``/empty and is cached
briefly, so the dashboard degrades gracefully (some sandboxes block these).
"""
from __future__ import annotations

import logging
import time
from typing import Any

import pandas as pd

from app.config import settings
from app.data.binance import _get_json

logger = logging.getLogger("cryptoai.derivatives")

COINGECKO_GLOBAL = "https://api.coingecko.com/api/v3/global"

# Simple in-process TTL cache (derivatives move slowly; funding updates every 8h).
_CACHE_TTL = 120.0
_cache: dict[str, tuple[float, Any]] = {}


def _cached(key: str, ttl: float, producer):
    now = time.time()
    hit = _cache.get(key)
    if hit and (now - hit[0]) < ttl:
        return hit[1]
    try:
        value = producer()
    except Exception as exc:  # noqa: BLE001 — best-effort intelligence layer
        logger.warning("derivatives fetch failed (%s): %s", key, exc)
        value = None
    _cache[key] = (now, value)
    return value


def funding_now(symbol: str) -> dict[str, Any] | None:
    """Current funding rate + mark price + next funding time for a symbol."""
    def _producer():
        url = f"{settings.binance_futures_base}/fapi/v1/premiumIndex"
        data = _get_json(url, {"symbol": symbol}, timeout=10.0)
        rate = float(data.get("lastFundingRate", 0.0))
        return {
            "symbol": symbol,
            "funding_rate_pct": round(rate * 100, 4),  # per 8h, as a percentage
            "funding_apr_pct": round(rate * 3 * 365 * 100, 2),  # annualized (3x/day)
            "mark_price": round(float(data.get("markPrice", 0.0)), 4),
            "next_funding_time": int(data.get("nextFundingTime", 0)),
        }

    return _cached(f"funding:{symbol}", _CACHE_TTL, _producer)


def open_interest_now(symbol: str) -> dict[str, Any] | None:
    """Current open interest (in contracts/base units) for a symbol."""
    def _producer():
        url = f"{settings.binance_futures_base}/fapi/v1/openInterest"
        data = _get_json(url, {"symbol": symbol}, timeout=10.0)
        return {"symbol": symbol, "open_interest": round(float(data.get("openInterest", 0.0)), 2)}

    return _cached(f"oi:{symbol}", _CACHE_TTL, _producer)


def long_short_ratio(symbol: str, period: str = "5m") -> dict[str, Any] | None:
    """Latest global long/short *account* ratio (crowd positioning)."""
    def _producer():
        url = f"{settings.binance_futures_base}/futures/data/globalLongShortAccountRatio"
        rows = _get_json(url, {"symbol": symbol, "period": period, "limit": 1}, timeout=10.0)
        if not rows:
            return None
        r = rows[-1]
        return {
            "symbol": symbol,
            "long_short_ratio": round(float(r.get("longShortRatio", 0.0)), 3),
            "long_pct": round(float(r.get("longAccount", 0.0)) * 100, 2),
            "short_pct": round(float(r.get("shortAccount", 0.0)) * 100, 2),
        }

    return _cached(f"ls:{symbol}", _CACHE_TTL, _producer)


def derivatives_snapshot(symbols: list[str] | None = None) -> list[dict[str, Any]]:
    """Per-symbol funding / OI / long-short snapshot for the dashboard."""
    syms = symbols or settings.symbols
    out = []
    for s in syms:
        funding = funding_now(s) or {}
        oi = open_interest_now(s) or {}
        ls = long_short_ratio(s) or {}
        available = bool(funding or oi or ls)
        out.append({
            "symbol": s,
            "available": available,
            "funding_rate_pct": funding.get("funding_rate_pct"),
            "funding_apr_pct": funding.get("funding_apr_pct"),
            "next_funding_time": funding.get("next_funding_time"),
            "open_interest": oi.get("open_interest"),
            "long_short_ratio": ls.get("long_short_ratio"),
            "long_pct": ls.get("long_pct"),
            "short_pct": ls.get("short_pct"),
        })
    return out


def global_stats() -> dict[str, Any] | None:
    """BTC dominance + total crypto market cap from CoinGecko (free, no key)."""
    def _producer():
        data = _get_json(COINGECKO_GLOBAL, {}, timeout=10.0).get("data", {})
        mcap = data.get("total_market_cap", {}).get("usd")
        dom = data.get("market_cap_percentage", {})
        return {
            "total_market_cap_usd": round(float(mcap), 0) if mcap else None,
            "btc_dominance_pct": round(float(dom.get("btc", 0.0)), 2),
            "eth_dominance_pct": round(float(dom.get("eth", 0.0)), 2),
            "market_cap_change_24h_pct": round(
                float(data.get("market_cap_change_percentage_24h_usd", 0.0)), 2
            ),
        }

    return _cached("global", 300.0, _producer)


def funding_history(symbol: str, start_ms: int, end_ms: int) -> pd.DataFrame:
    """Historical funding rates (every 8h) for backtesting funding strategies.

    Returns a DataFrame with columns ``funding_time`` (ms) and ``funding_rate``
    (fraction per 8h), ascending. Empty on failure.
    """
    url = f"{settings.binance_futures_base}/fapi/v1/fundingRate"
    rows: list[dict[str, Any]] = []
    cursor = start_ms
    try:
        while cursor < end_ms:
            page = _get_json(
                url,
                {"symbol": symbol, "startTime": cursor, "endTime": end_ms, "limit": 1000},
                timeout=15.0,
            )
            if not page:
                break
            rows.extend(page)
            last = int(page[-1]["fundingTime"])
            nxt = last + 1
            if nxt <= cursor or len(page) < 1000:
                break
            cursor = nxt
            time.sleep(0.1)
    except Exception as exc:  # noqa: BLE001
        logger.warning("funding history failed (%s): %s", symbol, exc)
        if not rows:
            return pd.DataFrame(columns=["funding_time", "funding_rate"])

    df = pd.DataFrame(
        [{"funding_time": int(r["fundingTime"]), "funding_rate": float(r["fundingRate"])}
         for r in rows]
    )
    if not df.empty:
        df = df.drop_duplicates("funding_time").sort_values("funding_time").reset_index(drop=True)
    return df


def attach_funding(df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """Merge historical funding onto a candle frame as a forward-filled ``funding``
    column (fraction per 8h). No-op-safe: on failure the column is all zeros so
    funding strategies simply stay flat rather than crashing.
    """
    out = df.copy()
    if out.empty or "open_time" not in out:
        out["funding"] = 0.0
        return out
    start_ms = int(out["open_time"].iloc[0])
    end_ms = int(out["open_time"].iloc[-1])
    fh = funding_history(symbol, start_ms, end_ms)
    if fh.empty:
        out["funding"] = 0.0
        return out
    merged = pd.merge_asof(
        out.sort_values("open_time"),
        fh.rename(columns={"funding_time": "open_time", "funding_rate": "funding"}),
        on="open_time",
        direction="backward",
    )
    merged["funding"] = merged["funding"].fillna(0.0)
    merged.index = out.index
    return merged
