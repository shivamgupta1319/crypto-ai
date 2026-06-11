"""Portfolio engine + sizing tests (in-memory DB, fake broker — no network)."""
from __future__ import annotations

from datetime import UTC

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401  (register tables on Base.metadata)
from app.broker.paper import PaperBroker
from app.config import settings
from app.db.session import Base
from app.portfolio import engine as pe
from app.portfolio.sizing import size_position


# --- sizing -------------------------------------------------------------------
def test_sizing_risk_based():
    qty, risk = size_position(100_000, 100.0, 98.0, 1.0, 3.0, 30.0)
    assert risk == pytest.approx(1000.0)  # 1% of 100k
    assert qty == pytest.approx(500.0)    # 1000 / 2.0 stop distance


def test_sizing_capped_by_leverage_notional():
    # Tiny stop -> huge raw qty, must be capped by max notional (100k*30%*3x=90k).
    qty, _ = size_position(100_000, 100.0, 99.9, 1.0, 3.0, 30.0)
    assert qty == pytest.approx(900.0)


def test_sizing_zero_when_no_stop_distance():
    assert size_position(100_000, 100.0, 100.0, 1.0, 3.0, 30.0) == (0.0, 0.0)


def test_sizing_scales_with_higher_leverage():
    # New 30x cap allows a far larger notional than the old 3x for a tight stop.
    qty_3x, _ = size_position(100_000, 100.0, 99.9, 1.0, 3.0, 30.0)
    qty_30x, _ = size_position(100_000, 100.0, 99.9, 1.0, 30.0, 30.0)
    assert qty_30x == pytest.approx(qty_3x * 10)
    assert qty_30x == pytest.approx(9000.0)


def test_max_leverage_is_30():
    assert settings.max_leverage == 30.0


# --- engine fixtures ----------------------------------------------------------
class FakeBroker(PaperBroker):
    def __init__(self) -> None:
        self.prices: dict[str, float] = {}

    def get_price(self, symbol: str) -> float:
        return self.prices[symbol]


@pytest.fixture
def db():
    eng = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(eng)
    Session = sessionmaker(bind=eng)
    with Session() as s:
        yield s


@pytest.fixture
def fake_broker(monkeypatch):
    fb = FakeBroker()
    monkeypatch.setattr(pe, "broker", fb)
    return fb


def _sig(symbol="BTCUSDT", direction="LONG", entry=100.0, stop=98.0, target=104.0):
    return {"symbol": symbol, "strategy": "ema_trend_adx", "direction": direction,
            "entry": entry, "stop": stop, "target": target}


# --- engine behaviour ---------------------------------------------------------
def test_open_from_signal_creates_position(db, fake_broker):
    ev = pe.open_from_signal(db, _sig())
    assert ev is not None
    opens = pe.open_trades(db)
    assert len(opens) == 1
    assert opens[0].symbol == "BTCUSDT"
    assert opens[0].qty == pytest.approx(500.0)  # 1% risk over 2.0 stop


def test_no_stacking_same_setup(db, fake_broker):
    assert pe.open_from_signal(db, _sig()) is not None
    assert pe.open_from_signal(db, _sig()) is None  # duplicate symbol+strategy rejected


def test_manage_closes_on_target(db, fake_broker):
    pe.open_from_signal(db, _sig(entry=100.0, stop=98.0, target=104.0))
    fake_broker.prices["BTCUSDT"] = 104.5  # target breached
    closed = pe.manage_open_trades(db, {"BTCUSDT": 104.5})
    assert len(closed) == 1
    assert closed[0]["reason"] == "target"
    assert closed[0]["pnl"] > 0
    assert len(pe.open_trades(db)) == 0


def test_manage_closes_on_stop_with_loss(db, fake_broker):
    pe.open_from_signal(db, _sig(entry=100.0, stop=98.0, target=104.0))
    closed = pe.manage_open_trades(db, {"BTCUSDT": 97.0})  # stop breached
    assert closed[0]["reason"] == "stop"
    assert closed[0]["pnl"] < 0


def test_kill_switch_blocks_new_trades(db, fake_broker):
    # Force a big realized loss today via a closed trade, then assert the gate.
    pe.open_from_signal(db, _sig(entry=100.0, stop=98.0, target=104.0))
    big_loss = -abs(settings.daily_max_loss_pct) / 100 * settings.initial_capital - 1
    trade = pe.open_trades(db)[0]
    trade.status = "CLOSED"
    trade.pnl = big_loss
    from datetime import datetime, timezone
    trade.closed_at = datetime.now(UTC)
    db.commit()
    assert pe.kill_switch_active(db) is True
    assert pe.open_from_signal(db, _sig(symbol="ETHUSDT")) is None


def test_account_summary_shapes(db, fake_broker):
    fake_broker.prices["BTCUSDT"] = 102.0
    pe.open_from_signal(db, _sig())
    s = pe.account_summary(db)
    assert s["initial_capital"] == settings.initial_capital
    assert s["open_positions"] == 1
    assert s["unrealized_pnl"] > 0  # price moved up on a long


def test_trailing_stop_ratchets_up_then_closes(db, fake_broker):
    pe.open_from_signal(db, _sig(entry=100.0, stop=98.0, target=120.0))
    trade = pe.open_trades(db)[0]
    # Price jumps to 105 (>= +1% activate); stop trails to 105*0.99 = 103.95.
    pe.manage_open_trades(db, {"BTCUSDT": 105.0})
    db.refresh(trade)
    assert trade.stop == pytest.approx(103.95)
    # Trailing never loosens on a smaller favorable move.
    pe.manage_open_trades(db, {"BTCUSDT": 104.5})
    db.refresh(trade)
    assert trade.stop == pytest.approx(103.95)
    # Pull back through the trailed stop -> closes in profit.
    closed = pe.manage_open_trades(db, {"BTCUSDT": 103.0})
    assert len(closed) == 1 and closed[0]["reason"] == "stop"
    assert closed[0]["pnl"] > 0


def test_manual_close_at_market(db, fake_broker):
    pe.open_from_signal(db, _sig(entry=100.0, stop=98.0, target=110.0))
    tid = pe.open_trades(db)[0].id
    fake_broker.prices["BTCUSDT"] = 101.5
    ev = pe.close_trade(db, tid)
    assert ev is not None and ev["reason"] == "manual"
    assert len(pe.open_trades(db)) == 0
    # Closing a non-existent / already-closed trade returns None.
    assert pe.close_trade(db, tid) is None


def test_strategy_attribution(db, fake_broker):
    # Two strategies: one winner, one loser.
    pe.open_from_signal(db, _sig(symbol="BTCUSDT", entry=100.0, stop=98.0, target=104.0))
    pe.manage_open_trades(db, {"BTCUSDT": 104.5})  # win
    pe.open_from_signal(db, {**_sig(symbol="ETHUSDT", entry=100.0, stop=98.0, target=104.0),
                             "strategy": "macd_rsi"})
    pe.manage_open_trades(db, {"ETHUSDT": 97.0})  # loss
    attr = pe.strategy_attribution(db)
    assert len(attr) == 2
    names = {a["strategy"] for a in attr}
    assert names == {"ema_trend_adx", "macd_rsi"}
    # Sorted by net_pnl descending → winner first.
    assert attr[0]["net_pnl"] >= attr[1]["net_pnl"]


def test_risk_view(db, fake_broker):
    fake_broker.prices["BTCUSDT"] = 100.0
    fake_broker.prices["ETHUSDT"] = 100.0
    pe.open_from_signal(db, _sig(symbol="BTCUSDT"))
    pe.open_from_signal(db, {**_sig(symbol="ETHUSDT"), "strategy": "macd_rsi"})
    r = pe.risk_view(db)
    assert r["gross_exposure"] > 0
    assert len(r["positions"]) == 2
    assert r["correlation_warning"] is True  # two longs = same direction
    assert all(p["liquidation_price"] < p_entry for p, p_entry in
               zip(r["positions"], [100.0, 100.0], strict=False))  # long liq below entry


def test_reset_account(db, fake_broker):
    pe.open_from_signal(db, _sig())
    assert len(pe.open_trades(db)) == 1
    deleted = pe.reset_account(db)
    assert deleted == 1
    assert len(pe.open_trades(db)) == 0


def test_funding_accrues_over_time(db, fake_broker):
    pe.open_from_signal(db, _sig(entry=100.0, stop=98.0, target=104.0))
    t = pe.open_trades(db)[0]
    # Backdate the open by 24h → funding should be a positive drag.
    from datetime import datetime, timedelta, timezone
    t.opened_at = datetime.now(UTC) - timedelta(hours=24)
    db.commit()
    assert pe._funding_accrued(t) > 0
