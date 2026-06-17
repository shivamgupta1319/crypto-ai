"""Live signal scanner.

For each promoted (active) strategy, evaluate it on the latest *closed* candle,
detect an entry event (the target position changing into a direction), compute
entry/stop/target/R:R/confidence, and persist a Signal — deduped per bar so the
same candle never emits twice. Reuses the exact strategy functions the
backtester uses, so live signals match backtested behaviour.
"""
from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from typing import Any

import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.data.binance import load_candles, tf_to_ms
from app.db.session import SessionLocal
from app.models import ActiveStrategy, Signal
from app.strategies.base import (
    all_strategies,
    enrich_df,
    merge_params,
    run_strategy,
    stop_target,
)

# How many bars of history to pull for indicator warmup before evaluating.
WARMUP_BARS = 400

# Wall-clock of the last completed scan cycle (epoch seconds); None until first run.
_last_scan_at: float | None = None


def _confidence(annotated: pd.DataFrame, direction: int = 0) -> float:
    """Multi-factor confidence in [0.2, 0.97]: trend strength (ADX) plus whether
    RSI and MACD agree with the trade direction. Falls back to 0.5 on error."""
    from app import indicators as ind

    try:
        high, low, close = annotated["high"], annotated["low"], annotated["close"]
        adx_val = float(ind.adx(high, low, close, 14).iloc[-1])
        adx_norm = min(max(adx_val - 15, 0) / 35, 1.0)  # ~20 weak → ~50 strong
        conf = 0.25 + 0.40 * adx_norm
        if direction != 0:
            rsi_val = float(ind.rsi(close, 14).iloc[-1])
            macd_hist = float(ind.macd(close)["hist"].iloc[-1])
            rsi_agrees = (rsi_val > 50) if direction == 1 else (rsi_val < 50)
            macd_agrees = (macd_hist > 0) if direction == 1 else (macd_hist < 0)
            conf += 0.175 * (1 if rsi_agrees else 0) + 0.175 * (1 if macd_agrees else 0)
        return round(min(max(conf, 0.2), 0.97), 3)
    except Exception:
        return 0.5


def detect_entry(
    annotated: pd.DataFrame, params: dict[str, Any], now_ms: int, tf_ms: int
) -> dict[str, Any] | None:
    """Pure entry-event detection on an annotated (signal+atr) frame.

    Returns a signal dict for the latest CLOSED bar if an entry just triggered,
    else None. Look-ahead-safe: drops the still-forming current candle.
    """
    closed = annotated[annotated["open_time"] + tf_ms <= now_ms]
    if len(closed) < 2:
        return None

    cur = int(closed["signal"].iloc[-1])
    prev = int(closed["signal"].iloc[-2])
    if cur == 0 or cur == prev:  # no new entry into a direction
        return None

    atr_val = float(closed["atr"].iloc[-1])
    if not (atr_val > 0):
        return None

    entry = float(closed["close"].iloc[-1])
    stop, target = stop_target(cur, entry, atr_val, params)
    rr = abs(target - entry) / abs(entry - stop) if entry != stop else 0.0
    return {
        "direction": "LONG" if cur == 1 else "SHORT",
        "entry": round(entry, 4),
        "stop": round(float(stop), 4),
        "target": round(float(target), 4),
        "rr": round(float(rr), 2),
        "confidence": _confidence(closed, cur),
        "bar_time": int(closed["open_time"].iloc[-1]),
    }


def _features_at(df: pd.DataFrame, bar_time: int) -> dict[str, float] | None:
    """Context feature vector at the bar with the given open_time (for meta-labeling)."""
    try:
        from app.learning.features import compute_feature_frame, row_to_vector

        feats = compute_feature_frame(df)
        match = df.index[df["open_time"] == bar_time]
        if len(match) == 0:
            return None
        return row_to_vector(feats.loc[match[0]])
    except Exception:
        return None


def _already_emitted(db: Session, symbol: str, timeframe: str, strategy: str, bar_time: int) -> bool:
    existing = db.execute(
        select(Signal.id).where(
            Signal.symbol == symbol,
            Signal.timeframe == timeframe,
            Signal.strategy == strategy,
            Signal.bar_time == bar_time,
        )
    ).first()
    return existing is not None


def scan_active() -> list[dict[str, Any]]:
    """Evaluate every enabled active strategy; persist & return any new signals.

    Synchronous (network + DB). Intended to be called from a threadpool by the
    async scheduler job.
    """
    global _last_scan_at
    now_ms = int(time.time() * 1000)
    _last_scan_at = time.time()
    new_signals: list[dict[str, Any]] = []

    with SessionLocal() as db:
        actives = db.execute(
            select(ActiveStrategy).where(ActiveStrategy.enabled == 1)
        ).scalars().all()

        for a in actives:
            tf_ms = tf_to_ms(a.timeframe)
            start_ms = now_ms - WARMUP_BARS * tf_ms
            try:
                df = load_candles(a.symbol, a.timeframe, start_ms, now_ms)
            except Exception:
                continue  # network hiccup — skip this cycle, try next time
            if df.empty or len(df) < 60:
                continue

            params = merge_params(a.strategy, json.loads(a.params_json or "{}"))
            df = enrich_df(a.strategy, df, a.symbol)
            annotated = run_strategy(a.strategy, df, params)
            hit = detect_entry(annotated, params, now_ms, tf_ms)
            if not hit:
                continue
            if _already_emitted(db, a.symbol, a.timeframe, a.strategy, hit["bar_time"]):
                continue

            row = Signal(
                symbol=a.symbol,
                timeframe=a.timeframe,
                strategy=a.strategy,
                direction=hit["direction"],
                entry=hit["entry"],
                stop=hit["stop"],
                target=hit["target"],
                confidence=hit["confidence"],
                bar_time=hit["bar_time"],
            )
            db.add(row)
            db.commit()
            db.refresh(row)
            payload = {
                "id": row.id,
                "symbol": row.symbol,
                "timeframe": row.timeframe,
                "strategy": row.strategy,
                "direction": row.direction,
                "entry": row.entry,
                "stop": row.stop,
                "target": row.target,
                "rr": hit["rr"],
                "confidence": row.confidence,
                "bar_time": row.bar_time,
                "created_at": row.created_at.isoformat(),
            }
            # Attach context features so the paper-trader's meta-label gate can
            # score this signal (only when the filter is enabled).
            if settings.meta_label_enabled:
                payload["features"] = _features_at(df, hit["bar_time"])
            # Current market regime, so the paper-trader can apply a per-regime
            # size multiplier (cheap — computed on the already-loaded frame).
            from app.regime import current_regime

            payload["regime"] = current_regime(df)
            new_signals.append(payload)

    return new_signals


def _setup_for(
    symbol: str, timeframe: str, strategy: str, overrides: dict[str, Any] | None
) -> dict[str, Any] | None:
    """Current actionable state of a strategy on its latest closed candle.

    Unlike detect_entry (which only fires on the transition bar), this always
    reports the live state — LONG / SHORT / FLAT — so the UI is never empty.
    """
    now_ms = int(time.time() * 1000)
    tf_ms = tf_to_ms(timeframe)
    start_ms = now_ms - WARMUP_BARS * tf_ms
    df = load_candles(symbol, timeframe, start_ms, now_ms)
    if df.empty or len(df) < 60:
        return None

    params = merge_params(strategy, overrides or {})
    df = enrich_df(strategy, df, symbol)
    annotated = run_strategy(strategy, df, params)
    closed = annotated[annotated["open_time"] + tf_ms <= now_ms]
    if len(closed) < 2:
        return None

    sigs = closed["signal"].to_numpy()
    cur = int(sigs[-1])
    prev = int(sigs[-2])
    state = "LONG" if cur == 1 else "SHORT" if cur == -1 else "FLAT"

    bars_in_state = 1
    for i in range(len(sigs) - 2, -1, -1):
        if int(sigs[i]) == cur:
            bars_in_state += 1
        else:
            break

    price = round(float(closed["close"].iloc[-1]), 4)
    entry = stop = target = rr = None
    if cur != 0:
        atr_val = float(closed["atr"].iloc[-1])
        entry = price
        if atr_val > 0:
            s, t = stop_target(cur, entry, atr_val, params)
            stop, target = round(float(s), 4), round(float(t), 4)
            rr = round(abs(target - entry) / abs(entry - stop), 2) if entry != stop else 0.0

    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "strategy": strategy,
        "state": state,
        "fresh": cur != 0 and cur != prev,  # just triggered this bar
        "actionable": cur != 0,
        "price": price,
        "entry": entry,
        "stop": stop,
        "target": target,
        "rr": rr,
        "confidence": _confidence(closed, cur),
        "bars_in_state": bars_in_state,
    }


def current_setups(scope: str = "active") -> list[dict[str, Any]]:
    """Live state of every monitored strategy.

    scope="active": the promoted strategies (what the scanner actually trades).
    scope="all": every strategy in the library across the configured symbols on
    a default timeframe — a preview of the whole universe.
    """
    if scope == "all":
        default_tf = "1h" if "1h" in settings.timeframes else settings.timeframes[0]
        combos = [
            (sym, default_tf, s.name, None)
            for s in all_strategies()
            for sym in settings.symbols
        ]
    else:
        with SessionLocal() as db:
            actives = db.execute(
                select(ActiveStrategy).where(ActiveStrategy.enabled == 1)
            ).scalars().all()
        combos = [
            (a.symbol, a.timeframe, a.strategy, json.loads(a.params_json or "{}"))
            for a in actives
        ]

    out: list[dict[str, Any]] = []
    for symbol, timeframe, strategy, overrides in combos:
        try:
            setup = _setup_for(symbol, timeframe, strategy, overrides)
        except Exception:
            setup = None
        if setup:
            out.append(setup)
    # Actionable setups first, then by confidence.
    out.sort(key=lambda s: (s["actionable"], s["confidence"]), reverse=True)
    return out


def get_scan_status() -> dict[str, Any]:
    with SessionLocal() as db:
        monitored = (
            db.execute(
                select(func.count()).select_from(ActiveStrategy).where(ActiveStrategy.enabled == 1)
            ).scalar()
            or 0
        )
    last = (
        datetime.fromtimestamp(_last_scan_at, tz=UTC).isoformat()
        if _last_scan_at
        else None
    )
    return {
        "last_scan_at": last,
        "monitored": int(monitored),
        "interval_s": settings.scan_interval_seconds,
        "alerts_enabled": settings.alerts_enabled,
        "price_stream": settings.price_stream_enabled,
    }
