"""The strategy library — 6 trader-designed strategies as pure signal functions.

Each ``generate`` returns the input df with ``signal`` (target position: 1/-1/0)
and ``atr`` columns. Stops/targets are derived from ATR by base.stop_target().
Importing this module registers every strategy.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from app import indicators as ind
from app.strategies.base import StrategyDef, register


def _finish(df: pd.DataFrame, signal: pd.Series, atr: pd.Series) -> pd.DataFrame:
    df["signal"] = signal
    df["atr"] = atr
    return df


# --- 1. EMA Trend + ADX filter -------------------------------------------------
def ema_trend_adx(df: pd.DataFrame, p: dict[str, Any]) -> pd.DataFrame:
    fast = ind.ema(df["close"], p["ema_fast"])
    slow = ind.ema(df["close"], p["ema_slow"])
    adx = ind.adx(df["high"], df["low"], df["close"], p["adx_length"])
    trending = adx >= p["adx_min"]
    long_ = (fast > slow) & trending
    short_ = (fast < slow) & trending
    signal = np.where(long_, 1, np.where(short_, -1, 0))
    return _finish(df, pd.Series(signal, index=df.index),
                   ind.atr(df["high"], df["low"], df["close"], p["atr_length"]))


register(StrategyDef(
    name="ema_trend_adx",
    description="EMA(fast/slow) crossover, only when ADX confirms a trend.",
    generate=ema_trend_adx,
    default_params={"ema_fast": 20, "ema_slow": 50, "adx_length": 14,
                    "adx_min": 20, "atr_length": 14, "atr_stop_mult": 2.0, "rr": 2.0},
    suited_for=["BTCUSDT", "ETHUSDT"],
))


# --- 2. MACD + RSI Momentum ----------------------------------------------------
def macd_rsi(df: pd.DataFrame, p: dict[str, Any]) -> pd.DataFrame:
    m = ind.macd(df["close"], p["macd_fast"], p["macd_slow"], p["macd_signal"])
    rsi = ind.rsi(df["close"], p["rsi_length"])
    long_ = (m["macd"] > m["signal"]) & (rsi > 50) & (rsi < p["rsi_overbought"])
    short_ = (m["macd"] < m["signal"]) & (rsi < 50) & (rsi > p["rsi_oversold"])
    signal = np.where(long_, 1, np.where(short_, -1, 0))
    return _finish(df, pd.Series(signal, index=df.index),
                   ind.atr(df["high"], df["low"], df["close"], p["atr_length"]))


register(StrategyDef(
    name="macd_rsi",
    description="MACD signal-line cross confirmed by RSI momentum.",
    generate=macd_rsi,
    default_params={"macd_fast": 12, "macd_slow": 26, "macd_signal": 9,
                    "rsi_length": 14, "rsi_overbought": 75, "rsi_oversold": 25,
                    "atr_length": 14, "atr_stop_mult": 2.0, "rr": 2.0},
    suited_for=["BTCUSDT", "ETHUSDT", "SOLUSDT"],
))


# --- 3. Supertrend -------------------------------------------------------------
def supertrend_strat(df: pd.DataFrame, p: dict[str, Any]) -> pd.DataFrame:
    st = ind.supertrend(df["high"], df["low"], df["close"], p["st_length"], p["st_mult"])
    signal = st["dir"]  # already 1 / -1
    return _finish(df, signal, ind.atr(df["high"], df["low"], df["close"], p["atr_length"]))


register(StrategyDef(
    name="supertrend",
    description="ATR Supertrend — always in-market, flips long/short on trend change.",
    generate=supertrend_strat,
    default_params={"st_length": 10, "st_mult": 3.0,
                    "atr_length": 14, "atr_stop_mult": 2.5, "rr": 2.5},
    suited_for=["BTCUSDT", "ETHUSDT", "SOLUSDT"],
))


# --- 4. Bollinger + RSI Mean-Reversion ----------------------------------------
def bollinger_meanrev(df: pd.DataFrame, p: dict[str, Any]) -> pd.DataFrame:
    bb = ind.bollinger(df["close"], p["bb_length"], p["bb_mult"])
    rsi = ind.rsi(df["close"], p["rsi_length"])
    adx = ind.adx(df["high"], df["low"], df["close"], p["adx_length"])
    ranging = adx < p["adx_max"]  # disable in strong trends
    long_ = (df["close"] <= bb["lower"]) & (rsi < p["rsi_oversold"]) & ranging
    short_ = (df["close"] >= bb["upper"]) & (rsi > p["rsi_overbought"]) & ranging
    signal = np.where(long_, 1, np.where(short_, -1, 0))
    return _finish(df, pd.Series(signal, index=df.index),
                   ind.atr(df["high"], df["low"], df["close"], p["atr_length"]))


register(StrategyDef(
    name="bollinger_meanrev",
    description="Fade Bollinger band touches with RSI extremes; only in ranging regimes.",
    generate=bollinger_meanrev,
    default_params={"bb_length": 20, "bb_mult": 2.0, "rsi_length": 14,
                    "rsi_oversold": 30, "rsi_overbought": 70, "adx_length": 14,
                    "adx_max": 20, "atr_length": 14, "atr_stop_mult": 1.5, "rr": 1.5},
    suited_for=["ETHUSDT", "SOLUSDT"],
))


# --- 5. Donchian Breakout + volume --------------------------------------------
def donchian_breakout(df: pd.DataFrame, p: dict[str, Any]) -> pd.DataFrame:
    dc = ind.donchian(df["high"], df["low"], p["dc_length"])
    # Use prior bar's channel to avoid look-ahead on the breakout bar.
    upper = dc["upper"].shift(1)
    lower = dc["lower"].shift(1)
    vol_ma = df["volume"].rolling(p["vol_length"]).mean()
    vol_ok = df["volume"] > vol_ma * p["vol_mult"]
    long_ = (df["close"] > upper) & vol_ok
    short_ = (df["close"] < lower) & vol_ok
    signal = np.where(long_, 1, np.where(short_, -1, 0))
    return _finish(df, pd.Series(signal, index=df.index),
                   ind.atr(df["high"], df["low"], df["close"], p["atr_length"]))


register(StrategyDef(
    name="donchian_breakout",
    description="N-period channel breakout confirmed by above-average volume.",
    generate=donchian_breakout,
    default_params={"dc_length": 20, "vol_length": 20, "vol_mult": 1.3,
                    "atr_length": 14, "atr_stop_mult": 2.0, "rr": 2.5},
    suited_for=["SOLUSDT", "BTCUSDT"],
))


# --- 6. VWAP + EMA pullback ----------------------------------------------------
def vwap_ema_pullback(df: pd.DataFrame, p: dict[str, Any]) -> pd.DataFrame:
    vwap = ind.vwap(df["high"], df["low"], df["close"], df["volume"])
    ema_f = ind.ema(df["close"], p["ema_length"])
    # Trend by VWAP side; enter on pullback to the EMA in the trend direction.
    up = (df["close"] > vwap) & (df["low"] <= ema_f) & (df["close"] > ema_f)
    down = (df["close"] < vwap) & (df["high"] >= ema_f) & (df["close"] < ema_f)
    signal = np.where(up, 1, np.where(down, -1, 0))
    return _finish(df, pd.Series(signal, index=df.index),
                   ind.atr(df["high"], df["low"], df["close"], p["atr_length"]))


register(StrategyDef(
    name="vwap_ema_pullback",
    description="Trade pullbacks to EMA in the direction of the VWAP trend.",
    generate=vwap_ema_pullback,
    default_params={"ema_length": 20, "atr_length": 14, "atr_stop_mult": 1.8, "rr": 2.0},
    suited_for=["BTCUSDT", "ETHUSDT", "SOLUSDT"],
))


# --- 7. Ichimoku Cloud --------------------------------------------------------
def ichimoku_cloud(df: pd.DataFrame, p: dict[str, Any]) -> pd.DataFrame:
    ich = ind.ichimoku(df["high"], df["low"], df["close"],
                       p["tenkan"], p["kijun"], p["senkou_b"])
    cloud_top = ich[["span_a", "span_b"]].max(axis=1)
    cloud_bot = ich[["span_a", "span_b"]].min(axis=1)
    long_ = (df["close"] > cloud_top) & (ich["tenkan"] > ich["kijun"])
    short_ = (df["close"] < cloud_bot) & (ich["tenkan"] < ich["kijun"])
    signal = np.where(long_, 1, np.where(short_, -1, 0))
    return _finish(df, pd.Series(signal, index=df.index),
                   ind.atr(df["high"], df["low"], df["close"], p["atr_length"]))


register(StrategyDef(
    name="ichimoku",
    description="Price above/below the cloud with Tenkan/Kijun confirmation.",
    generate=ichimoku_cloud,
    default_params={"tenkan": 9, "kijun": 26, "senkou_b": 52,
                    "atr_length": 14, "atr_stop_mult": 2.5, "rr": 2.5},
    suited_for=["BTCUSDT", "ETHUSDT"],
))


# --- 8. StochRSI momentum -----------------------------------------------------
def stochrsi_strat(df: pd.DataFrame, p: dict[str, Any]) -> pd.DataFrame:
    s = ind.stochrsi(df["close"], p["rsi_length"], p["k"], p["d"])
    ema_trend = ind.ema(df["close"], p["trend_ema"])
    up = df["close"] > ema_trend
    long_ = up & (s["k"] > s["d"]) & (s["k"] < p["oversold"] + 20)
    short_ = (~up) & (s["k"] < s["d"]) & (s["k"] > p["overbought"] - 20)
    signal = np.where(long_, 1, np.where(short_, -1, 0))
    return _finish(df, pd.Series(signal, index=df.index),
                   ind.atr(df["high"], df["low"], df["close"], p["atr_length"]))


register(StrategyDef(
    name="stochrsi",
    description="StochRSI %K/%D crosses, taken in the EMA trend direction.",
    generate=stochrsi_strat,
    default_params={"rsi_length": 14, "k": 3, "d": 3, "trend_ema": 100,
                    "oversold": 20, "overbought": 80,
                    "atr_length": 14, "atr_stop_mult": 2.0, "rr": 2.0},
    suited_for=["BTCUSDT", "ETHUSDT", "SOLUSDT"],
))


# --- 9. TTM Squeeze breakout --------------------------------------------------
def ttm_squeeze(df: pd.DataFrame, p: dict[str, Any]) -> pd.DataFrame:
    bb = ind.bollinger(df["close"], p["length"], p["bb_mult"])
    kc = ind.keltner(df["high"], df["low"], df["close"], p["length"], p["kc_mult"])
    # Squeeze ON when Bollinger is inside Keltner; fire on the release bar.
    squeeze_on = (bb["lower"] > kc["lower"]) & (bb["upper"] < kc["upper"])
    released = squeeze_on.shift(1, fill_value=False) & (~squeeze_on)
    mom = df["close"] - ind.ema(df["close"], p["length"])
    long_ = released & (mom > 0)
    short_ = released & (mom < 0)
    signal = np.where(long_, 1, np.where(short_, -1, 0))
    return _finish(df, pd.Series(signal, index=df.index),
                   ind.atr(df["high"], df["low"], df["close"], p["atr_length"]))


register(StrategyDef(
    name="ttm_squeeze",
    description="Bollinger-inside-Keltner squeeze release, in the momentum direction.",
    generate=ttm_squeeze,
    default_params={"length": 20, "bb_mult": 2.0, "kc_mult": 1.5,
                    "atr_length": 14, "atr_stop_mult": 2.0, "rr": 2.5},
    suited_for=["SOLUSDT", "ETHUSDT"],
))


# --- 10. Bollinger %B z-score mean-reversion ----------------------------------
def bollinger_pctb(df: pd.DataFrame, p: dict[str, Any]) -> pd.DataFrame:
    bb = ind.bollinger(df["close"], p["length"], p["mult"])
    width = (bb["upper"] - bb["lower"]).replace(0.0, np.nan)
    pct_b = (df["close"] - bb["lower"]) / width
    adx = ind.adx(df["high"], df["low"], df["close"], p["adx_length"])
    ranging = adx < p["adx_max"]
    long_ = (pct_b < p["low_b"]) & ranging
    short_ = (pct_b > p["high_b"]) & ranging
    signal = np.where(long_, 1, np.where(short_, -1, 0))
    return _finish(df, pd.Series(signal, index=df.index),
                   ind.atr(df["high"], df["low"], df["close"], p["atr_length"]))


register(StrategyDef(
    name="bollinger_pctb",
    description="Fade Bollinger %B extremes (statistical mean reversion); ranging only.",
    generate=bollinger_pctb,
    default_params={"length": 20, "mult": 2.0, "low_b": 0.05, "high_b": 0.95,
                    "adx_length": 14, "adx_max": 20,
                    "atr_length": 14, "atr_stop_mult": 1.5, "rr": 1.5},
    suited_for=["ETHUSDT", "SOLUSDT"],
))


# --- 11. Parabolic SAR trend --------------------------------------------------
def parabolic_sar(df: pd.DataFrame, p: dict[str, Any]) -> pd.DataFrame:
    sar = ind.psar(df["high"], df["low"], p["step"], p["max_step"])
    signal = sar["dir"]  # already 1 / -1
    return _finish(df, signal, ind.atr(df["high"], df["low"], df["close"], p["atr_length"]))


register(StrategyDef(
    name="parabolic_sar",
    description="Parabolic SAR flip — trend following with a built-in trailing stop.",
    generate=parabolic_sar,
    default_params={"step": 0.02, "max_step": 0.2,
                    "atr_length": 14, "atr_stop_mult": 2.5, "rr": 2.5},
    suited_for=["BTCUSDT", "ETHUSDT", "SOLUSDT"],
))


# --- 12. Funding-rate contrarian (perp-specific) ------------------------------
def funding_contrarian(df: pd.DataFrame, p: dict[str, Any]) -> pd.DataFrame:
    """Fade extreme perp funding: very positive funding = crowded longs paying to
    hold (lean short); very negative = crowded shorts (lean long). Needs the
    ``funding`` column (per-8h fraction) attached by base.enrich_df; if absent or
    flat it simply stays out (signal 0)."""
    if "funding" in df.columns:
        funding = pd.to_numeric(df["funding"], errors="coerce").fillna(0.0)
    else:
        funding = pd.Series(0.0, index=df.index)
    hi = float(p["funding_high"])  # fraction per 8h, e.g. 0.0005 = 0.05%
    lo = float(p["funding_low"])
    long_ = funding <= lo
    short_ = funding >= hi
    signal = np.where(long_, 1, np.where(short_, -1, 0))
    return _finish(df, pd.Series(signal, index=df.index),
                   ind.atr(df["high"], df["low"], df["close"], p["atr_length"]))


register(StrategyDef(
    name="funding_contrarian",
    description="Fade extreme perp funding (crowded longs/shorts). Perp-only edge.",
    generate=funding_contrarian,
    default_params={"funding_high": 0.0005, "funding_low": -0.0005,
                    "atr_length": 14, "atr_stop_mult": 2.0, "rr": 1.5},
    suited_for=["BTCUSDT", "ETHUSDT", "SOLUSDT"],
    needs=("funding",),
))
