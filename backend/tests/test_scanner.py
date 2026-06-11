"""Tests for live scanner entry-event detection (pure, no network/DB)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.live.scanner import detect_entry

TF_MS = 3_600_000  # 1h
PARAMS = {"atr_stop_mult": 2.0, "rr": 2.0}


def _frame(signals: list[int], base: int = 1_700_000_000_000) -> pd.DataFrame:
    n = len(signals)
    open_time = np.arange(n) * TF_MS + base
    close = np.full(n, 100.0)
    return pd.DataFrame(
        {
            "open_time": open_time,
            "open": close,
            "high": close * 1.01,
            "low": close * 0.99,
            "close": close,
            "atr": np.full(n, 2.0),
            "signal": signals,
        }
    )


def _now_with_last_bar_forming(df: pd.DataFrame) -> int:
    # Place "now" inside the last candle so it is still forming and gets dropped.
    return int(df["open_time"].iloc[-1]) + TF_MS // 2


def test_long_entry_on_transition():
    df = _frame([0, 0, 0, 1, 1])  # last bar (idx4) forming -> closed last is idx3 = 1, prev = 0
    now_ms = _now_with_last_bar_forming(df)
    hit = detect_entry(df, PARAMS, now_ms, TF_MS)
    assert hit is not None
    assert hit["direction"] == "LONG"
    assert hit["bar_time"] == int(df["open_time"].iloc[3])
    assert hit["stop"] < hit["entry"] < hit["target"]
    assert hit["rr"] == 2.0


def test_short_entry_on_transition():
    df = _frame([0, 0, 0, -1, -1])
    hit = detect_entry(df, PARAMS, _now_with_last_bar_forming(df), TF_MS)
    assert hit is not None
    assert hit["direction"] == "SHORT"
    assert hit["target"] < hit["entry"] < hit["stop"]


def test_no_entry_when_already_in_position():
    df = _frame([0, 0, 1, 1, 1])  # closed last idx3 = 1, prev idx2 = 1 -> no new entry
    assert detect_entry(df, PARAMS, _now_with_last_bar_forming(df), TF_MS) is None


def test_no_entry_when_flat():
    df = _frame([0, 0, 0, 0, 0])
    assert detect_entry(df, PARAMS, _now_with_last_bar_forming(df), TF_MS) is None


def test_forming_candle_is_dropped():
    # Signal only on the still-forming last bar must NOT emit.
    df = _frame([0, 0, 0, 0, 1])
    assert detect_entry(df, PARAMS, _now_with_last_bar_forming(df), TF_MS) is None


# --- current_setups snapshot (always-populated live state) --------------------
def test_setup_for_reports_long_in_uptrend(trending_up, monkeypatch):
    from app.live import scanner
    monkeypatch.setattr(scanner, "load_candles", lambda *a, **k: trending_up)
    setup = scanner._setup_for("BTCUSDT", "1h", "supertrend", None)
    assert setup is not None
    assert setup["state"] == "LONG"
    assert setup["actionable"] is True
    assert setup["entry"] is not None and setup["stop"] < setup["entry"] < setup["target"]
    assert setup["bars_in_state"] >= 1


def test_setup_for_reports_short_in_downtrend(trending_down, monkeypatch):
    # Confirms SHORT setups surface in the live snapshot (long & short support).
    from app.live import scanner
    monkeypatch.setattr(scanner, "load_candles", lambda *a, **k: trending_down)
    setup = scanner._setup_for("BTCUSDT", "1h", "supertrend", None)
    assert setup is not None
    assert setup["state"] == "SHORT"
    assert setup["target"] < setup["entry"] < setup["stop"]
