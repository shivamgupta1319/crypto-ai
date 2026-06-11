"""Market outlook — per-coin snapshot + Fear&Greed for the dashboard."""
from __future__ import annotations

import time

import pandas as pd

from app import indicators as ind
from app.config import settings
from app.data.binance import load_candles
from app.data.fng import get_fear_greed


def _coin_snapshot(symbol: str, timeframe: str = "1h", lookback_bars: int = 300) -> dict:
    end_ms = int(time.time() * 1000)
    start_ms = end_ms - lookback_bars * 60 * 60 * 1000  # ~lookback hours
    df = load_candles(symbol, timeframe, start_ms, end_ms)
    if df.empty or len(df) < 60:
        return {"symbol": symbol, "available": False}

    close = df["close"]
    ema_fast = ind.ema(close, 20)
    ema_slow = ind.ema(close, 50)
    rsi = ind.rsi(close, 14)
    adx = ind.adx(df["high"], df["low"], close, 14)
    macd = ind.macd(close)
    bb = ind.bollinger(close, 20, 2.0)
    atr = ind.atr(df["high"], df["low"], close, 14)

    last = close.iloc[-1]
    prev_24 = close.iloc[-25] if len(close) > 25 else close.iloc[0]
    change_24h = (last / prev_24 - 1) * 100

    trending = adx.iloc[-1] >= 20
    if trending and ema_fast.iloc[-1] > ema_slow.iloc[-1]:
        regime = "uptrend"
    elif trending and ema_fast.iloc[-1] < ema_slow.iloc[-1]:
        regime = "downtrend"
    else:
        regime = "ranging"

    # Bollinger %B: position within the bands (0 = lower, 1 = upper).
    band_width = float(bb["upper"].iloc[-1] - bb["lower"].iloc[-1])
    pct_b = (float(last) - float(bb["lower"].iloc[-1])) / band_width if band_width else 0.5

    # Volume trend: latest bar vs its 20-bar average.
    vol_ma = df["volume"].rolling(20).mean().iloc[-1]
    vol_ratio = float(df["volume"].iloc[-1] / vol_ma) if vol_ma and vol_ma > 0 else 1.0

    from app.regime import current_regime, regime_label

    regime_class = current_regime(df)
    macd_hist = float(macd["hist"].iloc[-1])
    return {
        "symbol": symbol,
        "available": True,
        "regime_class": regime_class,
        "regime_label": regime_label(regime_class),
        "price": round(float(last), 4),
        "change_24h_pct": round(float(change_24h), 2),
        "regime": regime,
        "rsi": round(float(rsi.iloc[-1]), 1),
        "adx": round(float(adx.iloc[-1]), 1),
        "ema_fast": round(float(ema_fast.iloc[-1]), 4),
        "ema_slow": round(float(ema_slow.iloc[-1]), 4),
        "macd_hist": round(macd_hist, 4),
        "macd_state": "bullish" if macd_hist > 0 else "bearish",
        "bb_pct": round(float(pct_b), 2),
        "atr": round(float(atr.iloc[-1]), 4),
        "atr_pct": round(float(atr.iloc[-1] / last * 100), 2),
        "vol_ratio": round(vol_ratio, 2),
    }


def correlation_matrix(timeframe: str = "1h", lookback_bars: int = 200) -> dict:
    """Pearson correlation of hourly returns across the configured symbols.

    Highlights that BTC/ETH/SOL tend to move together (concentration risk).
    """
    end_ms = int(time.time() * 1000)
    tf_ms = {"1h": 3_600_000, "4h": 4 * 3_600_000, "1d": 24 * 3_600_000}.get(timeframe, 3_600_000)
    start_ms = end_ms - lookback_bars * tf_ms

    returns: dict[str, pd.Series] = {}
    for sym in settings.symbols:
        df = load_candles(sym, timeframe, start_ms, end_ms)
        if df.empty or len(df) < 30:
            continue
        returns[sym] = df["close"].pct_change().dropna()
    if len(returns) < 2:
        return {"symbols": list(returns), "matrix": [], "available": False}

    frame = pd.DataFrame(returns).dropna()
    corr = frame.corr()
    syms = list(corr.columns)
    matrix = [[round(float(corr.loc[a, b]), 2) for b in syms] for a in syms]
    # Average off-diagonal correlation as a single "how correlated is the book" number.
    off = [corr.loc[a, b] for i, a in enumerate(syms) for j, b in enumerate(syms) if i < j]
    avg_corr = round(float(sum(off) / len(off)), 2) if off else None
    return {"symbols": syms, "matrix": matrix, "avg_correlation": avg_corr, "available": True}


def build_outlook() -> dict:
    fng = get_fear_greed()
    coins = [_coin_snapshot(sym) for sym in settings.symbols]
    available = [c for c in coins if c.get("available")]
    up = sum(1 for c in available if c["regime"] == "uptrend")
    down = sum(1 for c in available if c["regime"] == "downtrend")
    if up > down:
        breadth = "bullish"
    elif down > up:
        breadth = "bearish"
    else:
        breadth = "mixed"

    return {
        "fear_greed": fng,
        "market_breadth": breadth,
        "direction_support": "Long & Short",
        "coins": coins,
    }
