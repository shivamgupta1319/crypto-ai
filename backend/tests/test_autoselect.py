"""Auto-select screener — ranking, anti-overfit gates, and optional promotion."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.backtest import autoselect
from app.backtest.engine import BacktestConfig
from app.db.session import Base
from app.models import ActiveStrategy  # noqa: F401


@pytest.fixture
def db():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(eng)
    with sessionmaker(bind=eng)() as s:
        yield s


@pytest.fixture(autouse=True)
def stub_candles(monkeypatch):
    """Deterministic candles for any (symbol, tf) — a noisy uptrend."""
    def _loader(symbol, timeframe, start_ms, end_ms, ensure=True):
        n = 400
        rs = np.random.RandomState(abs(hash((symbol, timeframe))) % (2**32))
        closes = 100 + rs.normal(0, 1, n).cumsum() + np.linspace(0, 20, n)
        closes = np.maximum(closes, 10)
        ot = np.arange(n) * 3_600_000 + 1_700_000_000_000
        o = np.concatenate([[closes[0]], closes[:-1]])
        df = pd.DataFrame({
            "open_time": ot, "open": o, "high": np.maximum(o, closes) * 1.003,
            "low": np.minimum(o, closes) * 0.997, "close": closes, "volume": np.full(n, 1000.0),
        })
        df["time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
        return df.set_index("time")

    monkeypatch.setattr(autoselect, "load_candles", _loader)


def test_autoselect_ranks_and_flags(db):
    out = autoselect.auto_select(
        db, ["BTCUSDT", "ETHUSDT"], ["1h"], ["macd_rsi", "ema_trend_adx", "supertrend"],
        "2024-01-01", "2024-03-01", metric="sharpe", min_trades=1, cfg=BacktestConfig(),
    )
    assert out["combos_tested"] == 6  # 2 symbols x 1 tf x 3 strategies
    # Sorted: recommended first, then by score desc.
    recs = [c for c in out["candidates"] if c["recommended"]]
    assert out["recommended_count"] == len(recs)
    scored = [c["score"] for c in recs if c["score"] is not None]
    assert scored == sorted(scored, reverse=True)
    for c in out["candidates"]:
        assert {"symbol", "timeframe", "strategy", "oos_held_up", "flags", "excluded_reasons"} <= set(c)


def test_min_trades_gate_excludes(db):
    out = autoselect.auto_select(
        db, ["BTCUSDT"], ["1h"], ["macd_rsi"], "2024-01-01", "2024-03-01",
        min_trades=9999, cfg=BacktestConfig(),  # impossible -> excluded
    )
    c = out["candidates"][0]
    assert c["recommended"] is False
    assert any("trades" in r for r in c["excluded_reasons"])


def test_promote_writes_active_rows_with_ids(db):
    out = autoselect.auto_select(
        db, ["BTCUSDT", "ETHUSDT"], ["1h"], ["macd_rsi", "supertrend"],
        "2024-01-01", "2024-03-01", min_trades=1, oos_check=False,
        cfg=BacktestConfig(), top_n=2, promote=True,
    )
    promoted = out["promoted"]
    rows = db.query(ActiveStrategy).all()
    assert len(rows) == len(promoted)
    if promoted:
        assert all(r.enabled == 1 for r in rows)
        # Each promoted pick carries its active_id + metrics for the UI / remove action.
        for p in promoted:
            assert "active_id" in p and "return_pct" in p and "max_drawdown_pct" in p
            assert db.get(ActiveStrategy, p["active_id"]) is not None


def test_best_per_coin_selection(db):
    out = autoselect.auto_select(
        db, ["BTCUSDT", "ETHUSDT"], ["1h"], ["macd_rsi", "supertrend", "ema_trend_adx"],
        "2024-01-01", "2024-03-01", min_trades=1, oos_check=False,
        metric="composite", cfg=BacktestConfig(), per_coin_top=1, promote=True,
    )
    # At most one pick per coin.
    by_coin: dict[str, int] = {}
    for p in out["selected"]:
        by_coin[p["symbol"]] = by_coin.get(p["symbol"], 0) + 1
    assert all(n <= 1 for n in by_coin.values())


def test_invalid_metric_falls_back_to_composite(db):
    out = autoselect.auto_select(
        db, ["BTCUSDT"], ["1h"], ["macd_rsi"], "2024-01-01", "2024-03-01",
        metric="bogus", min_trades=1, cfg=BacktestConfig(),
    )
    assert out["metric"] == "composite"
