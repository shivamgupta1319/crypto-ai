"""Risk-based position sizing (shared by paper and live)."""
from __future__ import annotations


def size_position(
    equity: float,
    entry: float,
    stop: float,
    risk_pct: float,
    leverage: float,
    max_position_pct: float,
) -> tuple[float, float]:
    """Return (qty, risk_amount).

    Risk a fixed % of equity per trade; quantity follows from the stop distance.
    Capped so notional never exceeds equity * max_position_pct% * leverage.
    """
    risk_amount = equity * risk_pct / 100.0
    stop_dist = abs(entry - stop)
    if stop_dist <= 0 or equity <= 0:
        return 0.0, 0.0
    qty = risk_amount / stop_dist
    max_notional = equity * (max_position_pct / 100.0) * leverage
    if qty * entry > max_notional:
        qty = max_notional / entry
    return qty, risk_amount
