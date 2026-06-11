"""Market regime detection (N10 stage 2).

Rule-based first (transparent + no training data needed): classify each bar into
one of four regimes from ADX (trend strength), EMA slope (direction), and ATR%
(volatility). A GMM/HMM upgrade can later swap in behind the same interface.

Regimes:
  - ``trending_up``   : strong trend, fast EMA above slow
  - ``trending_down`` : strong trend, fast EMA below slow
  - ``high_vol``      : volatility spike without a clean trend (chop + big ranges)
  - ``ranging``       : low ADX, contained volatility
"""
from __future__ import annotations

import pandas as pd

from app import indicators as ind

REGIMES = ("trending_up", "trending_down", "ranging", "high_vol")


def regime_series(
    df: pd.DataFrame,
    adx_len: int = 14,
    ema_fast: int = 20,
    ema_slow: int = 50,
    adx_trend: float = 25.0,
    high_vol_atr_pct: float = 5.0,
) -> pd.Series:
    """Per-bar regime label for an OHLCV frame (vectorized)."""
    close, high, low = df["close"], df["high"], df["low"]
    adx = ind.adx(high, low, close, adx_len)
    fast = ind.ema(close, ema_fast)
    slow = ind.ema(close, ema_slow)
    atr_pct = ind.atr(high, low, close, adx_len) / close * 100

    trending = adx >= adx_trend
    up = fast > slow
    out = pd.Series("ranging", index=df.index, dtype=object)
    out = out.mask(atr_pct >= high_vol_atr_pct, "high_vol")
    out = out.mask(trending & up, "trending_up")
    out = out.mask(trending & ~up, "trending_down")
    return out


def current_regime(df: pd.DataFrame, **kwargs) -> str:
    """Regime of the latest bar (safe fallback to 'ranging' on short/empty data)."""
    if df is None or df.empty or len(df) < 60:
        return "ranging"
    try:
        return str(regime_series(df, **kwargs).iloc[-1])
    except Exception:
        return "ranging"


def regime_label(regime: str) -> str:
    """Human-friendly label for the UI."""
    return {
        "trending_up": "Trending ↑",
        "trending_down": "Trending ↓",
        "ranging": "Ranging",
        "high_vol": "High volatility",
    }.get(regime, regime)
