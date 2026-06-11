"""N10 stage 1+2 tests — regime detection, feature extraction, triple-barrier
labeling, and the dataset builder/store."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base
from app.learning import dataset, features, labeling
from app.learning.features import ALL_FEATURES
from app.models import TrainingSample  # noqa: F401
from app.regime import current_regime, regime_series


def _candles(closes: np.ndarray) -> pd.DataFrame:
    n = len(closes)
    open_time = np.arange(n) * 3_600_000 + 1_700_000_000_000
    opens = np.concatenate([[closes[0]], closes[:-1]])
    df = pd.DataFrame({
        "open_time": open_time, "open": opens,
        "high": np.maximum(opens, closes) * 1.002,
        "low": np.minimum(opens, closes) * 0.998,
        "close": closes, "volume": np.full(n, 1000.0),
    })
    df["time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    return df.set_index("time")


@pytest.fixture
def db():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(eng)
    with sessionmaker(bind=eng)() as s:
        yield s


# --- regime -------------------------------------------------------------------
def test_regime_uptrend():
    df = _candles(np.linspace(100, 200, 300))
    reg = regime_series(df)
    assert (reg.iloc[60:] == "trending_up").mean() > 0.5
    assert current_regime(df) in ("trending_up", "high_vol")


def test_regime_short_data_safe():
    assert current_regime(_candles(np.array([100.0, 101.0]))) == "ranging"


# --- triple-barrier labeling --------------------------------------------------
def test_triple_barrier_win():
    closes = np.full(50, 100.0)
    df = _candles(closes)
    df.iloc[5, df.columns.get_loc("high")] = 110.0  # target touched at bar 5
    res = labeling.triple_barrier(df, 0, 1, stop=95.0, target=108.0, max_bars=20)
    assert res["label"] == 1 and res["realized_r"] > 0


def test_triple_barrier_loss():
    df = _candles(np.full(50, 100.0))
    df.iloc[3, df.columns.get_loc("low")] = 90.0  # stop touched at bar 3
    res = labeling.triple_barrier(df, 0, 1, stop=95.0, target=108.0, max_bars=20)
    assert res["label"] == 0 and res["realized_r"] == -1.0


def test_triple_barrier_timeout():
    df = _candles(np.full(30, 100.0))  # flat — neither barrier hit
    res = labeling.triple_barrier(df, 0, 1, stop=95.0, target=108.0, max_bars=10)
    assert res.get("timeout") is True


# --- features -----------------------------------------------------------------
def test_feature_frame_has_all_numeric():
    df = _candles(np.linspace(100, 130, 200))
    f = features.compute_feature_frame(df)
    for name in features.FEATURE_NAMES:
        assert name in f.columns
    vec = features.row_to_vector(f.iloc[-1])
    assert set(vec) == set(ALL_FEATURES)
    # regime one-hot sums to 1
    assert sum(vec[r] for r in features.REGIME_FEATURES) == 1.0
    assert all(np.isfinite(v) for v in vec.values())


# --- dataset build + persist + load ------------------------------------------
def test_build_and_persist_dataset(db):
    # A choppy series so the strategy produces several entries.
    rng = np.linspace(0, 12 * np.pi, 400)
    closes = 100 + 8 * np.sin(rng) + np.linspace(0, 10, 400)
    df = _candles(closes)
    samples = dataset.build_samples("BTCUSDT", "1h", df, "macd_rsi")
    assert len(samples) > 0
    for s in samples:
        assert s["label"] in (0, 1)
        assert set(s["features"]) == set(ALL_FEATURES)

    inserted = dataset.persist_samples(db, samples)
    assert inserted == len(samples)
    # Idempotent: re-persisting the same samples inserts nothing new.
    assert dataset.persist_samples(db, samples) == 0

    X, y, rows = dataset.load_dataset(db, strategy="macd_rsi")
    assert X.shape[0] == len(samples)
    assert X.shape[1] == len(ALL_FEATURES)
    stats = dataset.dataset_stats(db)
    assert stats["total"] == len(samples)
