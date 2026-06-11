"""N10 stage 3 tests — meta-label training, P(win) scoring, entry mask, and the
with/without filter evaluation. Uses a synthetic dataset + a tmp model dir."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base
from app.learning import dataset, metalabel
from app.models import TrainingSample  # noqa: F401


def _candles(closes: np.ndarray) -> pd.DataFrame:
    n = len(closes)
    open_time = np.arange(n) * 3_600_000 + 1_700_000_000_000
    opens = np.concatenate([[closes[0]], closes[:-1]])
    df = pd.DataFrame({
        "open_time": open_time, "open": opens,
        "high": np.maximum(opens, closes) * 1.003,
        "low": np.minimum(opens, closes) * 0.997,
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


@pytest.fixture(autouse=True)
def tmp_model_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(metalabel, "MODEL_DIR", tmp_path / "models")
    monkeypatch.setattr(metalabel, "MIN_SAMPLES", 40)  # synthetic data is small
    metalabel.reset_cache()
    yield
    metalabel.reset_cache()


def _seed_dataset(db, n=1500, seed=7):
    """A seeded random walk produces many entries with BOTH wins and losses."""
    rs = np.random.RandomState(seed)
    steps = rs.normal(0, 1.0, n).cumsum()
    closes = 100 + steps + 3 * np.sin(np.linspace(0, 24 * np.pi, n))
    closes = np.maximum(closes, 5.0)
    df = _candles(closes)
    samples = dataset.build_samples("BTCUSDT", "1h", df, "macd_rsi")
    dataset.persist_samples(db, samples)
    return df, len(samples)


def test_train_requires_min_samples(db):
    # No data at all -> must raise rather than train on nothing.
    with pytest.raises(ValueError):
        metalabel.train(db, strategy="nonexistent_strategy")


def test_train_and_predict(db):
    df, n = _seed_dataset(db)
    assert n >= metalabel.MIN_SAMPLES, f"need >= {metalabel.MIN_SAMPLES} samples, got {n}"
    meta = metalabel.train(db, strategy="macd_rsi")
    assert meta["samples"] == n
    assert "top_features" in meta

    # p_win returns a probability in [0,1] for a feature vector.
    from app.learning.features import compute_feature_frame, row_to_vector
    feats = compute_feature_frame(df)
    vec = row_to_vector(feats.iloc[-1])
    p = metalabel.p_win(vec, "macd_rsi")
    assert p is not None and 0.0 <= p <= 1.0

    # Entry mask aligns to bars and is boolean.
    mask = metalabel.predict_mask("macd_rsi", df, threshold=0.5)
    assert mask is not None and mask.dtype == bool and len(mask) == len(df)


def test_p_win_none_without_model(db):
    assert metalabel.p_win({"rsi": 50}, "macd_rsi") is None
    assert metalabel.predict_mask("macd_rsi", _candles(np.linspace(100, 110, 100)), 0.5) is None


def test_evaluate_filter(db):
    df, n = _seed_dataset(db)
    assert n >= metalabel.MIN_SAMPLES
    metalabel.train(db, strategy="macd_rsi")
    out = metalabel.evaluate_filter("BTCUSDT", "1h", df, "macd_rsi", threshold=0.5)
    assert out["available"] is True
    assert "with" in out and "without" in out
    assert "improved" in out
    # Filtered run takes no more trades than the unfiltered run.
    assert out["with"]["trades"] <= out["without"]["trades"]
