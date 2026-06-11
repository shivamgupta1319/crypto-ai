"""Shared fixtures — synthetic candles so tests need no network access."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


def _make_candles(closes: np.ndarray, start_ms: int = 1_700_000_000_000,
                  step_ms: int = 3_600_000) -> pd.DataFrame:
    n = len(closes)
    open_time = np.arange(n) * step_ms + start_ms
    opens = np.concatenate([[closes[0]], closes[:-1]])
    highs = np.maximum(opens, closes) * 1.002
    lows = np.minimum(opens, closes) * 0.998
    volume = np.full(n, 1000.0)
    df = pd.DataFrame({
        "open_time": open_time,
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": volume,
    })
    df["time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    return df.set_index("time")


@pytest.fixture
def trending_up() -> pd.DataFrame:
    # Steady uptrend with mild noise.
    base = np.linspace(100, 200, 400)
    noise = np.sin(np.arange(400) / 5) * 1.5
    return _make_candles(base + noise)


@pytest.fixture
def trending_down() -> pd.DataFrame:
    # Steady downtrend with mild noise.
    base = np.linspace(200, 100, 400)
    noise = np.sin(np.arange(400) / 5) * 1.5
    return _make_candles(base + noise)


@pytest.fixture
def choppy() -> pd.DataFrame:
    # Range-bound oscillation around 100.
    closes = 100 + np.sin(np.arange(400) / 8) * 8
    return _make_candles(closes)
