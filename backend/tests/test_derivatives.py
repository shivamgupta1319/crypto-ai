"""N6 market-intelligence tests — derivatives data (mocked httpx), funding
attachment + the funding_contrarian strategy, and correlation matrix."""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.data import derivatives as dv
from app.strategies.base import enrich_df, run_strategy


def _candles(n=200):
    closes = np.linspace(100, 120, n)
    open_time = np.arange(n) * 3_600_000 + 1_700_000_000_000
    df = pd.DataFrame({
        "open_time": open_time, "open": closes, "high": closes * 1.01,
        "low": closes * 0.99, "close": closes, "volume": np.full(n, 1000.0),
    })
    df["time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    return df.set_index("time")


# --- derivatives data (mocked) ------------------------------------------------
def test_funding_now(monkeypatch):
    dv._cache.clear()
    monkeypatch.setattr(dv, "_get_json", lambda *a, **k: {
        "lastFundingRate": "0.0001", "markPrice": "60000.5", "nextFundingTime": 123,
    })
    out = dv.funding_now("BTCUSDT")
    assert out["funding_rate_pct"] == 0.01
    assert out["mark_price"] == 60000.5
    assert out["funding_apr_pct"] == round(0.0001 * 3 * 365 * 100, 2)


def test_snapshot_graceful_on_error(monkeypatch):
    dv._cache.clear()

    def boom(*a, **k):
        raise RuntimeError("blocked")

    monkeypatch.setattr(dv, "_get_json", boom)
    snap = dv.derivatives_snapshot(["BTCUSDT"])
    assert snap[0]["symbol"] == "BTCUSDT"
    assert snap[0]["available"] is False  # never raises


def test_global_stats(monkeypatch):
    dv._cache.clear()
    monkeypatch.setattr(dv, "_get_json", lambda *a, **k: {"data": {
        "total_market_cap": {"usd": 2.5e12},
        "market_cap_percentage": {"btc": 54.3, "eth": 17.1},
        "market_cap_change_percentage_24h_usd": -1.2,
    }})
    g = dv.global_stats()
    assert g["btc_dominance_pct"] == 54.3
    assert g["total_market_cap_usd"] == 2.5e12


# --- funding attachment + strategy --------------------------------------------
def test_attach_funding_forward_fills(monkeypatch):
    df = _candles(50)
    fh = pd.DataFrame({
        "funding_time": [int(df["open_time"].iloc[0]), int(df["open_time"].iloc[20])],
        "funding_rate": [0.001, -0.001],
    })
    monkeypatch.setattr(dv, "funding_history", lambda *a, **k: fh)
    out = dv.attach_funding(df, "BTCUSDT")
    assert "funding" in out.columns
    assert out["funding"].iloc[0] == 0.001
    assert out["funding"].iloc[25] == -0.001  # forward-filled from bar 20


def test_attach_funding_empty_is_zero(monkeypatch):
    df = _candles(30)
    monkeypatch.setattr(dv, "funding_history",
                        lambda *a, **k: pd.DataFrame(columns=["funding_time", "funding_rate"]))
    out = dv.attach_funding(df, "BTCUSDT")
    assert (out["funding"] == 0.0).all()


def test_funding_contrarian_fades_extremes():
    df = _candles(60)
    df["funding"] = 0.0
    df.loc[df.index[30:40], "funding"] = 0.001   # crowded longs -> short
    df.loc[df.index[40:50], "funding"] = -0.001  # crowded shorts -> long
    out = run_strategy("funding_contrarian", df)
    assert (out["signal"].iloc[30:40] == -1).all()
    assert (out["signal"].iloc[40:50] == 1).all()


def test_funding_contrarian_flat_without_funding():
    df = _candles(40)  # no funding column attached
    out = run_strategy("funding_contrarian", df)
    assert (out["signal"] == 0).all()  # stays out rather than crashing


def test_enrich_df_attaches_for_needy_strategy(monkeypatch):
    df = _candles(20)
    monkeypatch.setattr(dv, "funding_history", lambda *a, **k: pd.DataFrame(
        {"funding_time": [int(df["open_time"].iloc[0])], "funding_rate": [0.0002]}))
    enriched = enrich_df("funding_contrarian", df, "BTCUSDT")
    assert "funding" in enriched.columns
    # A strategy that doesn't declare needs is untouched.
    plain = enrich_df("macd_rsi", df, "BTCUSDT")
    assert "funding" not in plain.columns
