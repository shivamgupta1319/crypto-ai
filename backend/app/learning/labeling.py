"""Triple-barrier labeling (López de Prado) for meta-labeling (N10 stage 1).

For an entry at bar i with a stop and target, walk forward bar-by-bar and label:
  - 1 (win)  : target touched before stop
  - 0 (loss) : stop touched before target (or timeout closes at a loss)
  - timeout  : neither barrier within ``max_bars`` — labeled by sign of the
               close-to-close return (small wins count as 1, else 0)

Look-ahead-safe: only uses bars strictly *after* the entry bar. Intrabar touches
use the bar high/low (same convention as the backtest engine).
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def triple_barrier(
    df: pd.DataFrame,
    entry_idx: int,
    direction: int,
    stop: float,
    target: float,
    max_bars: int = 48,
) -> dict | None:
    """Label a single hypothetical trade. Returns a dict with label/realized_r/
    bars_held, or None if there isn't enough forward data to evaluate."""
    n = len(df)
    if entry_idx >= n - 1:
        return None
    high = df["high"].to_numpy()
    low = df["low"].to_numpy()
    close = df["close"].to_numpy()
    entry = float(close[entry_idx])
    risk = abs(entry - stop)
    if risk <= 0:
        return None

    end = min(entry_idx + max_bars, n - 1)
    for j in range(entry_idx + 1, end + 1):
        hi, lo = float(high[j]), float(low[j])
        if direction == 1:
            hit_stop = lo <= stop
            hit_tgt = hi >= target
        else:
            hit_stop = hi >= stop
            hit_tgt = lo <= target
        # If both barriers fall inside the same bar, assume the stop hit first
        # (conservative — matches the engine's pessimistic intrabar rule).
        if hit_stop:
            return {"label": 0, "realized_r": round(-1.0, 4), "bars_held": j - entry_idx}
        if hit_tgt:
            r = (target - entry) / risk if direction == 1 else (entry - target) / risk
            return {"label": 1, "realized_r": round(float(r), 4), "bars_held": j - entry_idx}

    # Timeout: mark to the last close.
    exit_px = float(close[end])
    pnl = (exit_px - entry) * direction
    r = pnl / risk
    return {
        "label": 1 if r > 0 else 0,
        "realized_r": round(float(r), 4),
        "bars_held": end - entry_idx,
        "timeout": True,
    }


def label_entries(
    df: pd.DataFrame,
    signals: np.ndarray,
    stops: np.ndarray,
    targets: np.ndarray,
    max_bars: int = 48,
) -> list[dict]:
    """Label every entry-event bar (where the target position flips into a
    direction). Returns one dict per labeled entry with its bar index."""
    out: list[dict] = []
    prev = 0
    for i in range(1, len(df)):
        cur = int(signals[i])
        if cur != 0 and cur != prev:
            stop, target = float(stops[i]), float(targets[i])
            if np.isfinite(stop) and np.isfinite(target):
                res = triple_barrier(df, i, cur, stop, target, max_bars)
                if res is not None:
                    out.append({"bar_idx": i, "direction": cur, **res})
        prev = cur
    return out
