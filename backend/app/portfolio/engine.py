"""PortfolioEngine — the paper-trading brain.

Consumes scanner signals, applies risk limits (sizing, leverage cap, max
concurrent positions, daily-loss kill switch), opens positions via the broker,
manages stops/targets each cycle, and reports account state. The same risk
logic will guard live trading in Phase 5 — only the broker swaps.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.broker.base import BrokerInterface
from app.broker.paper import PaperBroker
from app.config import settings
from app.db.session import SessionLocal
from app.models import PaperTrade
from app.portfolio.sizing import size_position

broker: BrokerInterface = PaperBroker()


# --- accounting helpers -------------------------------------------------------
def _closed(db: Session) -> list[PaperTrade]:
    return list(
        db.execute(select(PaperTrade).where(PaperTrade.status == "CLOSED")).scalars()
    )


def open_trades(db: Session) -> list[PaperTrade]:
    return list(
        db.execute(select(PaperTrade).where(PaperTrade.status == "OPEN")).scalars()
    )


def realized_balance(db: Session) -> float:
    closed = _closed(db)
    return settings.initial_capital + sum(t.pnl or 0.0 for t in closed)


def _today_realized(db: Session) -> float:
    today = datetime.now(UTC).date()
    return sum(
        (t.pnl or 0.0)
        for t in _closed(db)
        if t.closed_at and t.closed_at.replace(tzinfo=UTC).date() == today
    )


def _funding_accrued(trade: PaperTrade, now: datetime | None = None) -> float:
    """Funding carry cost accrued on an open position since it opened (approximation —
    a conservative drag proportional to notional × hold time, matching the backtester)."""
    now = now or datetime.now(UTC)
    opened = trade.opened_at
    if opened.tzinfo is None:
        opened = opened.replace(tzinfo=UTC)
    hours = max(0.0, (now - opened).total_seconds() / 3600.0)
    return trade.qty * trade.entry_price * (settings.funding_rate_pct_per_8h / 100.0) * (hours / 8.0)


def _unrealized(db: Session, price_cache: dict[str, float]) -> float:
    total = 0.0
    for t in open_trades(db):
        px = price_cache.get(t.symbol)
        if px is None:
            continue
        sign = 1 if t.direction == "LONG" else -1
        total += (px - t.entry_price) * t.qty * sign - _funding_accrued(t)
    return total


def _price_cache(symbols: set[str]) -> dict[str, float]:
    cache: dict[str, float] = {}
    for s in symbols:
        try:
            cache[s] = broker.get_price(s)
        except Exception:
            pass
    return cache


# --- risk gate ----------------------------------------------------------------
def kill_switch_active(db: Session) -> bool:
    limit = -abs(settings.daily_max_loss_pct) / 100.0 * settings.initial_capital
    return _today_realized(db) <= limit


def _can_open(db: Session, symbol: str, strategy: str) -> bool:
    opens = open_trades(db)
    if len(opens) >= settings.max_concurrent_positions:
        return False
    if any(t.symbol == symbol and t.strategy == strategy for t in opens):
        return False  # no stacking the same setup
    return not kill_switch_active(db)


# --- core cycle ---------------------------------------------------------------
def _apply_trailing(trade: PaperTrade, px: float) -> bool:
    """Ratchet the stop toward price once in sufficient profit. Returns True if moved."""
    act = settings.trail_activate_pct / 100.0
    dist = settings.trail_distance_pct / 100.0
    if trade.direction == "LONG":
        if px >= trade.entry_price * (1 + act):
            new_stop = px * (1 - dist)
            if new_stop > trade.stop:
                trade.stop = round(new_stop, 4)
                return True
    else:  # SHORT
        if px <= trade.entry_price * (1 - act):
            new_stop = px * (1 + dist)
            if new_stop < trade.stop:
                trade.stop = round(new_stop, 4)
                return True
    return False


def manage_open_trades(db: Session, price_cache: dict[str, float]) -> list[dict[str, Any]]:
    """Trail stops, then close any open trade whose stop or target is breached."""
    closed_events: list[dict[str, Any]] = []
    moved = False
    for t in open_trades(db):
        px = price_cache.get(t.symbol)
        if px is None:
            continue
        if settings.trailing_enabled and _apply_trailing(t, px):
            moved = True
    if moved:
        db.commit()

    for t in open_trades(db):
        px = price_cache.get(t.symbol)
        if px is None:
            continue
        exit_price = None
        reason = None
        if t.direction == "LONG":
            if px <= t.stop:
                exit_price, reason = t.stop, "stop"
            elif px >= t.target:
                exit_price, reason = t.target, "target"
        else:  # SHORT
            if px >= t.stop:
                exit_price, reason = t.stop, "stop"
            elif px <= t.target:
                exit_price, reason = t.target, "target"
        if exit_price is not None:
            exit_fee = t.qty * exit_price * settings.taker_fee_pct / 100.0 + _funding_accrued(t)
            broker.close_position(db, t, exit_price, exit_fee)
            closed_events.append(
                {"id": t.id, "symbol": t.symbol, "strategy": t.strategy,
                 "reason": reason, "pnl": round(t.pnl or 0.0, 2)}
            )
    return closed_events


def open_from_signal(db: Session, sig: dict[str, Any]) -> dict[str, Any] | None:
    """Open a paper position from a scanner signal if risk checks pass."""
    if not _can_open(db, sig["symbol"], sig["strategy"]):
        return None

    # Meta-label gate (N10): if enabled and a model exists, only take the signal
    # when P(win) clears the threshold. Advisory lever — off by default.
    if settings.meta_label_enabled and sig.get("features"):
        from app.learning import metalabel

        prob = metalabel.p_win(sig["features"], sig["strategy"])
        if prob is not None and prob < settings.meta_label_threshold:
            return None

    equity = realized_balance(db)
    leverage = min(settings.default_leverage, settings.max_leverage)
    qty, _ = size_position(
        equity, sig["entry"], sig["stop"], settings.risk_per_trade_pct,
        leverage, settings.max_position_pct,
    )
    # Agent size multiplier (bounded lever; 1.0 when none set).
    from app.learning.levers import size_multiplier_safe

    qty *= size_multiplier_safe(sig["strategy"])
    if qty <= 0:
        return None

    entry_fee = qty * sig["entry"] * settings.taker_fee_pct / 100.0
    trade = broker.open_position(
        db, symbol=sig["symbol"], strategy=sig["strategy"], direction=sig["direction"],
        qty=qty, leverage=leverage, entry=sig["entry"], stop=sig["stop"],
        target=sig["target"], entry_fee=entry_fee,
    )
    return {"id": trade.id, "symbol": trade.symbol, "strategy": trade.strategy,
            "direction": trade.direction, "qty": round(qty, 6), "entry": trade.entry_price}


def close_trade(db: Session, trade_id: int) -> dict[str, Any] | None:
    """Manually close an open trade at the current market price."""
    t = db.get(PaperTrade, trade_id)
    if t is None or t.status != "OPEN":
        return None
    px = broker.get_price(t.symbol)
    exit_fee = t.qty * px * settings.taker_fee_pct / 100.0 + _funding_accrued(t)
    broker.close_position(db, t, px, exit_fee)
    return {"id": t.id, "symbol": t.symbol, "strategy": t.strategy,
            "reason": "manual", "pnl": round(t.pnl or 0.0, 2)}


def close_trade_by_id(trade_id: int) -> dict[str, Any] | None:
    """Session-managing wrapper so async endpoints can call via a threadpool."""
    with SessionLocal() as db:
        return close_trade(db, trade_id)


def run_paper_cycle(db: Session, new_signals: list[dict[str, Any]]) -> dict[str, Any]:
    """Manage open trades, then open positions for any new signals."""
    symbols = {t.symbol for t in open_trades(db)} | {s["symbol"] for s in new_signals}
    price_cache = _price_cache(symbols)

    closed = manage_open_trades(db, price_cache)
    opened: list[dict[str, Any]] = []
    for sig in new_signals:
        ev = open_from_signal(db, sig)
        if ev:
            opened.append(ev)
    return {"opened": opened, "closed": closed}


# --- reporting ----------------------------------------------------------------
def account_summary(db: Session) -> dict[str, Any]:
    opens = open_trades(db)
    price_cache = _price_cache({t.symbol for t in opens})
    balance = realized_balance(db)
    unreal = _unrealized(db, price_cache)
    closed = _closed(db)
    wins = [t for t in closed if (t.pnl or 0) > 0]
    realized = balance - settings.initial_capital
    equity = balance + unreal
    return {
        "initial_capital": round(settings.initial_capital, 2),
        "balance": round(balance, 2),
        "equity": round(equity, 2),
        "unrealized_pnl": round(unreal, 2),
        "realized_pnl": round(realized, 2),
        "return_pct": round(realized / settings.initial_capital * 100, 2),
        "open_positions": len(opens),
        "closed_trades": len(closed),
        "win_rate": round(len(wins) / len(closed) * 100, 2) if closed else 0.0,
        "kill_switch": kill_switch_active(db),
        "display_currency": settings.display_currency,
    }


def open_positions_view(db: Session) -> list[dict[str, Any]]:
    opens = open_trades(db)
    price_cache = _price_cache({t.symbol for t in opens})
    out = []
    for t in opens:
        px = price_cache.get(t.symbol, t.entry_price)
        sign = 1 if t.direction == "LONG" else -1
        unreal = (px - t.entry_price) * t.qty * sign - _funding_accrued(t)
        out.append({
            "id": t.id, "symbol": t.symbol, "strategy": t.strategy,
            "direction": t.direction, "qty": round(t.qty, 6), "leverage": t.leverage,
            "entry_price": t.entry_price, "stop": t.stop, "target": t.target,
            "current_price": round(px, 4), "unrealized_pnl": round(unreal, 2),
            "opened_at": t.opened_at.isoformat(),
        })
    return out


def closed_trades_view(db: Session, limit: int = 100) -> list[dict[str, Any]]:
    rows = db.execute(
        select(PaperTrade).where(PaperTrade.status == "CLOSED")
        .order_by(PaperTrade.closed_at.desc()).limit(limit)
    ).scalars().all()
    return [{
        "id": t.id, "symbol": t.symbol, "strategy": t.strategy, "direction": t.direction,
        "qty": round(t.qty, 6), "entry_price": t.entry_price, "exit_price": t.exit_price,
        "pnl": round(t.pnl or 0.0, 2), "fees": round(t.fees, 2),
        "opened_at": t.opened_at.isoformat(),
        "closed_at": t.closed_at.isoformat() if t.closed_at else None,
    } for t in rows]


def equity_curve(db: Session) -> list[dict[str, Any]]:
    """Realized equity over time from closed trades (cumulative)."""
    rows = db.execute(
        select(PaperTrade).where(PaperTrade.status == "CLOSED")
        .order_by(PaperTrade.closed_at.asc())
    ).scalars().all()
    eq = settings.initial_capital
    curve = [{"time": 0, "equity": round(eq, 2)}]
    for t in rows:
        eq += t.pnl or 0.0
        ts = int(t.closed_at.replace(tzinfo=UTC).timestamp() * 1000) if t.closed_at else 0
        curve.append({"time": ts, "equity": round(eq, 2)})
    return curve


def strategy_attribution(db: Session) -> list[dict[str, Any]]:
    """Per-strategy P&L breakdown from closed trades — which strategy actually earns."""
    by: dict[str, list[PaperTrade]] = {}
    for t in _closed(db):
        by.setdefault(t.strategy, []).append(t)
    out = []
    for strat, ts in by.items():
        pnls = [t.pnl or 0.0 for t in ts]
        wins = [p for p in pnls if p > 0]
        gross_profit = sum(p for p in pnls if p > 0)
        gross_loss = abs(sum(p for p in pnls if p < 0))
        out.append({
            "strategy": strat,
            "trades": len(ts),
            "net_pnl": round(sum(pnls), 2),
            "win_rate": round(len(wins) / len(ts) * 100, 2) if ts else 0.0,
            "avg_pnl": round(sum(pnls) / len(ts), 2) if ts else 0.0,
            "profit_factor": round(gross_profit / gross_loss, 2) if gross_loss else None,
        })
    out.sort(key=lambda r: r["net_pnl"], reverse=True)
    return out


def risk_view(db: Session) -> dict[str, Any]:
    """Live risk snapshot: exposure, margin usage, concentration, liquidation, correlation."""
    opens = open_trades(db)
    price_cache = _price_cache({t.symbol for t in opens})
    equity = realized_balance(db) + _unrealized(db, price_cache)
    positions = []
    gross = net = margin = 0.0
    by_symbol: dict[str, float] = {}
    net_dirs = set()
    for t in opens:
        px = price_cache.get(t.symbol, t.entry_price)
        sign = 1 if t.direction == "LONG" else -1
        notional = t.qty * px
        gross += notional
        net += notional * sign
        margin += notional / t.leverage if t.leverage else notional
        by_symbol[t.symbol] = by_symbol.get(t.symbol, 0.0) + notional
        net_dirs.add(t.direction)
        # Rough liquidation price (ignores maintenance margin/fees) ~ entry × (1 ∓ 1/lev).
        liq = t.entry_price * (1 - 1 / t.leverage) if t.direction == "LONG" else t.entry_price * (1 + 1 / t.leverage)
        positions.append({
            "id": t.id, "symbol": t.symbol, "direction": t.direction,
            "leverage": t.leverage, "notional": round(notional, 2),
            "margin": round(notional / t.leverage if t.leverage else notional, 2),
            "liquidation_price": round(liq, 4),
        })
    concentration = {s: round(v / gross * 100, 1) for s, v in by_symbol.items()} if gross else {}
    # All open positions in the same direction on correlated majors = concentrated risk.
    correlated = len(opens) > 1 and len(net_dirs) == 1
    return {
        "equity": round(equity, 2),
        "gross_exposure": round(gross, 2),
        "net_exposure": round(net, 2),
        "gross_exposure_pct": round(gross / equity * 100, 1) if equity > 0 else 0.0,
        "margin_used": round(margin, 2),
        "margin_used_pct": round(margin / equity * 100, 1) if equity > 0 else 0.0,
        "concentration_pct": concentration,
        "correlation_warning": correlated,
        "positions": positions,
    }


def reset_account(db: Session) -> int:
    """Wipe all paper trades (fresh paper account). Returns rows deleted."""
    rows = db.execute(select(PaperTrade)).scalars().all()
    n = len(rows)
    for t in rows:
        db.delete(t)
    db.commit()
    return n
