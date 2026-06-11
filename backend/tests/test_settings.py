"""N9 settings-store tests — validation, persistence, cross-field guards, reset."""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import settings_store as ss
from app.config import settings
from app.db.session import Base
from app.models import Setting  # noqa: F401  (register table)


@pytest.fixture
def db():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(eng)
    Session = sessionmaker(bind=eng)
    with Session() as s:
        yield s


@pytest.fixture(autouse=True)
def restore_settings():
    snapshot = {f.key: getattr(settings, f.key) for f in ss.FIELDS}
    yield
    for k, v in snapshot.items():
        setattr(settings, k, v)


def test_update_applies_and_persists(db):
    out = ss.update(db, {"risk_per_trade_pct": 2.5, "default_leverage": 8})
    assert out["values"]["risk_per_trade_pct"] == 2.5
    assert settings.risk_per_trade_pct == 2.5
    assert settings.default_leverage == 8
    # Persisted: a fresh load_overrides re-applies after a reset of the live value.
    settings.risk_per_trade_pct = 1.0
    ss.load_overrides(db)
    assert settings.risk_per_trade_pct == 2.5


def test_rejects_out_of_bounds(db):
    with pytest.raises(ValueError, match="max"):
        ss.update(db, {"max_leverage": 999})
    with pytest.raises(ValueError, match="min"):
        ss.update(db, {"risk_per_trade_pct": 0})


def test_cross_field_leverage_guard(db):
    with pytest.raises(ValueError, match="exceed"):
        ss.update(db, {"default_leverage": 20, "max_leverage": 10})


def test_rejects_unknown_key(db):
    with pytest.raises(ValueError, match="Unknown"):
        ss.update(db, {"initial_capital": 5})  # not in the editable whitelist


def test_symbol_universe_validation(db):
    ss.update(db, {"symbols": ["btcusdt", "ETHUSDT", "BTCUSDT"]})
    assert settings.symbols == ["BTCUSDT", "ETHUSDT"]  # upper + de-duped
    with pytest.raises(ValueError, match="Invalid symbol"):
        ss.update(db, {"symbols": ["NOTACOIN"]})


def test_timeframe_validation(db):
    with pytest.raises(ValueError, match="Invalid timeframes"):
        ss.update(db, {"timeframes": ["1h", "7y"]})


def test_reset_clears_overrides(db):
    ss.update(db, {"risk_per_trade_pct": 4.0})
    assert settings.risk_per_trade_pct == 4.0
    ss.reset(db)
    assert db.query(Setting).count() == 0
    assert settings.risk_per_trade_pct == 1.0  # back to config default


def test_effective_exposes_bounds():
    eff = ss.effective()
    keys = {f["key"] for f in eff["fields"]}
    assert "risk_per_trade_pct" in keys and "symbols" in keys
    assert eff["values"]["max_leverage"] == settings.max_leverage
