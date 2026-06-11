"""Technical indicators implemented in pure pandas/numpy.

Hand-rolled to avoid pandas-ta (which currently breaks against NumPy 2.x) and
to keep dependencies minimal. Each function takes/returns pandas Series aligned
to the candle DataFrame index.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def ema(series: pd.Series, length: int) -> pd.Series:
    return series.ewm(span=length, adjust=False).mean()


def sma(series: pd.Series, length: int) -> pd.Series:
    return series.rolling(length).mean()


def rsi(close: pd.Series, length: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    # Wilder's smoothing.
    avg_gain = gain.ewm(alpha=1 / length, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / length, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    out = 100.0 - (100.0 / (1.0 + rs))
    return out.fillna(50.0)


def macd(
    close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9
) -> pd.DataFrame:
    macd_line = ema(close, fast) - ema(close, slow)
    signal_line = ema(macd_line, signal)
    hist = macd_line - signal_line
    return pd.DataFrame({"macd": macd_line, "signal": signal_line, "hist": hist})


def true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat(
        [(high - low), (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)
    return tr


def atr(high: pd.Series, low: pd.Series, close: pd.Series, length: int = 14) -> pd.Series:
    tr = true_range(high, low, close)
    return tr.ewm(alpha=1 / length, adjust=False).mean()


def adx(
    high: pd.Series, low: pd.Series, close: pd.Series, length: int = 14
) -> pd.Series:
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
    tr = true_range(high, low, close)
    atr_ = tr.ewm(alpha=1 / length, adjust=False).mean()
    plus_di = 100 * pd.Series(plus_dm, index=high.index).ewm(
        alpha=1 / length, adjust=False
    ).mean() / atr_.replace(0.0, np.nan)
    minus_di = 100 * pd.Series(minus_dm, index=high.index).ewm(
        alpha=1 / length, adjust=False
    ).mean() / atr_.replace(0.0, np.nan)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0.0, np.nan)
    return dx.ewm(alpha=1 / length, adjust=False).mean().fillna(0.0)


def bollinger(
    close: pd.Series, length: int = 20, mult: float = 2.0
) -> pd.DataFrame:
    mid = sma(close, length)
    std = close.rolling(length).std(ddof=0)
    upper = mid + mult * std
    lower = mid - mult * std
    return pd.DataFrame({"mid": mid, "upper": upper, "lower": lower})


def supertrend(
    high: pd.Series, low: pd.Series, close: pd.Series, length: int = 10, mult: float = 3.0
) -> pd.DataFrame:
    """Return columns: ``supertrend`` (line) and ``dir`` (1 long / -1 short)."""
    atr_ = atr(high, low, close, length)
    hl2 = (high + low) / 2
    upper = hl2 + mult * atr_
    lower = hl2 - mult * atr_

    final_upper = upper.copy()
    final_lower = lower.copy()
    n = len(close)
    st = pd.Series(index=close.index, dtype=float)
    direction = pd.Series(index=close.index, dtype=float)

    close_v = close.to_numpy()
    fu = final_upper.to_numpy()
    fl = final_lower.to_numpy()
    st_v = np.full(n, np.nan)
    dir_v = np.full(n, 1.0)

    for i in range(1, n):
        fu[i] = fu[i] if (fu[i] < fu[i - 1] or close_v[i - 1] > fu[i - 1]) else fu[i - 1]
        fl[i] = fl[i] if (fl[i] > fl[i - 1] or close_v[i - 1] < fl[i - 1]) else fl[i - 1]
        if close_v[i] > fu[i - 1]:
            dir_v[i] = 1.0
        elif close_v[i] < fl[i - 1]:
            dir_v[i] = -1.0
        else:
            dir_v[i] = dir_v[i - 1]
        st_v[i] = fl[i] if dir_v[i] == 1.0 else fu[i]

    st[:] = st_v
    direction[:] = dir_v
    return pd.DataFrame({"supertrend": st, "dir": direction})


def donchian(high: pd.Series, low: pd.Series, length: int = 20) -> pd.DataFrame:
    upper = high.rolling(length).max()
    lower = low.rolling(length).min()
    return pd.DataFrame({"upper": upper, "lower": lower})


def vwap(
    high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series
) -> pd.Series:
    """Rolling cumulative VWAP over the provided window (session-agnostic)."""
    typical = (high + low + close) / 3
    cum_vol = volume.cumsum().replace(0.0, np.nan)
    return (typical * volume).cumsum() / cum_vol


def stochrsi(
    close: pd.Series, length: int = 14, k: int = 3, d: int = 3
) -> pd.DataFrame:
    """Stochastic RSI → %K and %D in [0, 100]."""
    r = rsi(close, length)
    lo = r.rolling(length).min()
    hi = r.rolling(length).max()
    rng = (hi - lo).replace(0.0, np.nan)
    stoch = ((r - lo) / rng * 100).fillna(50.0)
    k_line = stoch.rolling(k).mean()
    d_line = k_line.rolling(d).mean()
    return pd.DataFrame({"k": k_line, "d": d_line})


def keltner(
    high: pd.Series, low: pd.Series, close: pd.Series, length: int = 20, mult: float = 2.0
) -> pd.DataFrame:
    """Keltner channel: EMA mid ± mult × ATR."""
    mid = ema(close, length)
    rng = atr(high, low, close, length)
    return pd.DataFrame({"mid": mid, "upper": mid + mult * rng, "lower": mid - mult * rng})


def ichimoku(
    high: pd.Series, low: pd.Series, close: pd.Series,
    tenkan: int = 9, kijun: int = 26, senkou_b: int = 52,
) -> pd.DataFrame:
    """Ichimoku lines. Senkou spans are shifted FORWARD (computed from past data,
    so reading them at bar t uses only information available by t — no look-ahead)."""
    def midpoint(n: int) -> pd.Series:
        return (high.rolling(n).max() + low.rolling(n).min()) / 2

    tenkan_line = midpoint(tenkan)
    kijun_line = midpoint(kijun)
    span_a = ((tenkan_line + kijun_line) / 2).shift(kijun)
    span_b = midpoint(senkou_b).shift(kijun)
    return pd.DataFrame(
        {"tenkan": tenkan_line, "kijun": kijun_line, "span_a": span_a, "span_b": span_b}
    )


def psar(
    high: pd.Series, low: pd.Series, step: float = 0.02, max_step: float = 0.2
) -> pd.DataFrame:
    """Parabolic SAR → ``sar`` line and ``dir`` (1 long / -1 short)."""
    h = high.to_numpy()
    low_v = low.to_numpy()
    n = len(h)
    sar = np.zeros(n)
    direction = np.ones(n)
    if n == 0:
        return pd.DataFrame({"sar": sar, "dir": direction}, index=high.index)

    bull = True
    af = step
    ep = h[0]
    sar[0] = low_v[0]
    for i in range(1, n):
        prev = sar[i - 1]
        sar[i] = prev + af * (ep - prev)
        if bull:
            # SAR can't exceed the prior two lows (never the current bar's low).
            sar[i] = min(sar[i], low_v[i - 1], low_v[i - 2] if i >= 2 else low_v[i - 1])
            if h[i] > ep:
                ep = h[i]
                af = min(af + step, max_step)
            if low_v[i] < sar[i]:  # flip to bear
                bull = False
                sar[i] = ep
                ep = low_v[i]
                af = step
        else:
            sar[i] = max(sar[i], h[i - 1], h[i - 2] if i >= 2 else h[i - 1])
            if low_v[i] < ep:
                ep = low_v[i]
                af = min(af + step, max_step)
            if h[i] > sar[i]:  # flip to bull
                bull = True
                sar[i] = ep
                ep = h[i]
                af = step
        direction[i] = 1.0 if bull else -1.0
    return pd.DataFrame({"sar": sar, "dir": direction}, index=high.index)
