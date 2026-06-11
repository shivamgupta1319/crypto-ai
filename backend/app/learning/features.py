"""Feature extraction for meta-labeling (N10 stage 1).

Computes a fixed, ordered set of context features at each bar — the inputs a
secondary model uses to score P(win) for a base-strategy signal. Pure functions:
given an OHLCV frame, return a feature frame / per-bar dict.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from app import indicators as ind
from app.regime import regime_series

# The model's feature vector, in a fixed order (so training/inference agree).
FEATURE_NAMES: tuple[str, ...] = (
    "rsi",
    "adx",
    "macd_hist",
    "ema_ratio",      # fast/slow - 1
    "atr_pct",        # atr / close * 100
    "bb_pct",         # position within Bollinger bands
    "vol_ratio",      # volume / 20-bar avg
    "ret_5",          # 5-bar return %
    "ret_20",         # 20-bar return %
    "dist_ema50_pct", # (close/ema50 - 1) * 100
)

# Regime is categorical — one-hot appended after the numeric features.
REGIME_FEATURES: tuple[str, ...] = (
    "regime_trending_up",
    "regime_trending_down",
    "regime_ranging",
    "regime_high_vol",
)

ALL_FEATURES: tuple[str, ...] = FEATURE_NAMES + REGIME_FEATURES


def compute_feature_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Return a DataFrame (same index as df) with the numeric feature columns +
    a ``regime`` column. NaNs in the warmup region are left as-is; callers should
    drop or guard rows where features aren't ready."""
    close, high, low, vol = df["close"], df["high"], df["low"], df["volume"]
    macd = ind.macd(close)
    bb = ind.bollinger(close, 20, 2.0)
    ema_fast = ind.ema(close, 20)
    ema_slow = ind.ema(close, 50)
    atr = ind.atr(high, low, close, 14)
    band_width = (bb["upper"] - bb["lower"]).replace(0, np.nan)
    vol_ma = vol.rolling(20).mean()

    f = pd.DataFrame(index=df.index)
    f["rsi"] = ind.rsi(close, 14)
    f["adx"] = ind.adx(high, low, close, 14)
    f["macd_hist"] = macd["hist"]
    f["ema_ratio"] = ema_fast / ema_slow - 1.0
    f["atr_pct"] = atr / close * 100
    f["bb_pct"] = (close - bb["lower"]) / band_width
    f["vol_ratio"] = vol / vol_ma
    f["ret_5"] = close.pct_change(5) * 100
    f["ret_20"] = close.pct_change(20) * 100
    f["dist_ema50_pct"] = (close / ema_slow - 1.0) * 100
    f["regime"] = regime_series(df)
    return f


def row_to_vector(row: pd.Series) -> dict[str, float]:
    """Turn one feature-frame row into the full numeric vector dict (incl. one-hot
    regime). Non-finite values become 0.0 so the model never sees NaN/inf."""
    out: dict[str, float] = {}
    for name in FEATURE_NAMES:
        val = row.get(name)
        out[name] = float(val) if val is not None and np.isfinite(val) else 0.0
    regime = row.get("regime", "ranging")
    for rf in REGIME_FEATURES:
        out[rf] = 1.0 if rf == f"regime_{regime}" else 0.0
    return out


def vector_list(features: dict[str, float]) -> list[float]:
    """Ordered feature list for model input (matches ALL_FEATURES order)."""
    return [features.get(name, 0.0) for name in ALL_FEATURES]
