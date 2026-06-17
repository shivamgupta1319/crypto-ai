"""N10 stages 4-6 — walk-forward optimizer, allocation proposals, and the agent
proposal lifecycle (generate -> approve -> revert) with bounded levers."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.db.session import Base
from app.learning import agent as brain
from app.learning import allocation, levers, optimizer
from app.models import (  # noqa: F401
    ActiveStrategy,
    AgentProposal,
    PaperTrade,
    Setting,
    TrainingSample,
)


@pytest.fixture
def db():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(eng)
    with sessionmaker(bind=eng)() as s:
        yield s


def _candles(closes: np.ndarray) -> pd.DataFrame:
    n = len(closes)
    open_time = np.arange(n) * 3_600_000 + 1_700_000_000_000
    opens = np.concatenate([[closes[0]], closes[:-1]])
    df = pd.DataFrame({
        "open_time": open_time, "open": opens,
        "high": np.maximum(opens, closes) * 1.003, "low": np.minimum(opens, closes) * 0.997,
        "close": closes, "volume": np.full(n, 1000.0),
    })
    df["time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    return df.set_index("time")


def _add_trade(db, strategy, pnl, status="CLOSED"):
    db.add(PaperTrade(
        symbol="BTCUSDT", strategy=strategy, direction="LONG", qty=1.0, leverage=3,
        entry_price=100.0, stop=98.0, target=104.0, exit_price=100 + pnl,
        pnl=pnl, status=status,
    ))
    db.commit()


# ---- stage 4: optimizer ------------------------------------------------------
def test_optimizer_returns_structure(db):
    rs = np.random.RandomState(3)
    closes = 100 + rs.normal(0, 1, 600).cumsum()
    closes = np.maximum(closes, 10)
    out = optimizer.propose_params("BTCUSDT", "1h", _candles(closes), "macd_rsi", {})
    assert out["available"] is True
    assert "proposed_params" in out and "recommend" in out
    assert isinstance(out["recommend"], bool)


def test_optimizer_no_grid():
    out = optimizer.propose_params("BTCUSDT", "1h", _candles(np.linspace(100, 110, 300)),
                                   "funding_contrarian", {})
    assert out["available"] is False  # no tuning grid defined


# ---- stage 5: allocation -----------------------------------------------------
def test_allocation_proposes_disable_for_loser(db):
    db.add(ActiveStrategy(symbol="BTCUSDT", timeframe="1h", strategy="macd_rsi", enabled=1))
    db.commit()
    for _ in range(12):
        _add_trade(db, "macd_rsi", -50.0)  # consistent losses
    props = allocation.propose(db)
    kinds = {p["kind"] for p in props}
    assert "disable_strategy" in kinds


# ---- stage 6: agent lifecycle ------------------------------------------------
def test_agent_generate_approve_revert(db):
    db.add(ActiveStrategy(symbol="BTCUSDT", timeframe="1h", strategy="macd_rsi", enabled=1))
    db.commit()
    for _ in range(12):
        _add_trade(db, "macd_rsi", -40.0)

    created = brain.generate_proposals(db)
    assert len(created) >= 1
    # Dedup: a second pass creates nothing new.
    assert brain.generate_proposals(db) == []

    disable = next(p for p in created if p.kind == "disable_strategy")
    brain.approve(db, disable.id)
    active = db.query(ActiveStrategy).filter_by(strategy="macd_rsi").first()
    assert active.enabled == 0  # lever applied

    reverted = brain.revert(db, disable.id)
    assert reverted.status == "reverted"
    active = db.query(ActiveStrategy).filter_by(strategy="macd_rsi").first()
    assert active.enabled == 1  # restored


def test_size_multiplier_lever_bounded(db):
    levers.set_multiplier(db, "macd_rsi", 99.0)  # way over cap
    assert levers.get_multiplier(db, "macd_rsi") == levers.MAX_MULT
    levers.set_multiplier(db, "macd_rsi", 0.01)  # under floor
    assert levers.get_multiplier(db, "macd_rsi") == levers.MIN_MULT
    assert levers.get_multiplier(db, "unknown") == 1.0


def _add_sample(db, strategy, regime, label, bar_time):
    db.add(TrainingSample(
        symbol="BTCUSDT", timeframe="1h", strategy=strategy, direction=1,
        regime=regime, label=label, bar_time=bar_time, source="backtest",
    ))


def test_regime_multiplier_lever_bounded(db):
    levers.set_regime_multiplier(db, "macd_rsi", "ranging", 99.0)  # over cap
    assert levers.get_regime_multiplier(db, "macd_rsi", "ranging") == levers.MAX_MULT
    levers.set_regime_multiplier(db, "macd_rsi", "ranging", 0.01)  # under floor
    assert levers.get_regime_multiplier(db, "macd_rsi", "ranging") == levers.MIN_MULT
    # Untouched regime/strategy default to neutral 1.0.
    assert levers.get_regime_multiplier(db, "macd_rsi", "trending_up") == 1.0
    assert levers.get_regime_multiplier(db, "unknown", "ranging") == 1.0


def test_allocation_proposes_regime_reduction(db):
    for i in range(12):
        _add_sample(db, "macd_rsi", "ranging", 0, i)  # all losses in 'ranging'
    db.commit()
    props = allocation.propose(db)
    regime_props = [p for p in props if p["kind"] == "set_regime_multiplier"]
    assert any(p["payload"]["regime"] == "ranging" for p in regime_props)


def test_agent_applies_and_reverts_regime_multiplier(db):
    for i in range(12):
        _add_sample(db, "macd_rsi", "ranging", 0, i)
    db.commit()
    created = brain.generate_proposals(db)
    rp = next(p for p in created if p.kind == "set_regime_multiplier")
    brain.approve(db, rp.id)
    assert levers.get_regime_multiplier(db, "macd_rsi", "ranging") == 0.5  # lever applied
    brain.revert(db, rp.id)
    assert levers.get_regime_multiplier(db, "macd_rsi", "ranging") == 1.0  # restored


def test_overview_shape(db):
    ov = brain.overview(db)
    for key in ("dataset", "model", "allocation", "pending_proposals", "levers"):
        assert key in ov
    assert ov["meta_label_enabled"] == settings.meta_label_enabled
