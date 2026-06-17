"""Bounded levers the agent can pull (with human approval).

Each lever is small, reversible, and clamped so an approved proposal can never
drive the system outside its hard risk caps. Per-strategy size multipliers are
stored as a JSON setting and read by the paper-trader when sizing.
"""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.models import Setting

_MULT_KEY = "agent_size_multipliers"
_REGIME_KEY = "agent_regime_multipliers"
MIN_MULT, MAX_MULT = 0.25, 2.0


def size_multipliers(db: Session) -> dict[str, float]:
    row = db.get(Setting, _MULT_KEY)
    if row is None:
        return {}
    try:
        return {k: float(v) for k, v in json.loads(row.value_json).items()}
    except (ValueError, json.JSONDecodeError):
        return {}


def get_multiplier(db: Session, strategy: str) -> float:
    return size_multipliers(db).get(strategy, 1.0)


def set_multiplier(db: Session, strategy: str, mult: float) -> None:
    mult = max(MIN_MULT, min(MAX_MULT, float(mult)))
    current = size_multipliers(db)
    current[strategy] = mult
    row = db.get(Setting, _MULT_KEY)
    payload = json.dumps(current)
    if row is None:
        db.add(Setting(key=_MULT_KEY, value_json=payload))
    else:
        row.value_json = payload
    db.commit()


def size_multiplier_safe(strategy: str) -> float:
    """Session-managing read for the paper-trader (own short-lived session)."""
    from app.db.session import SessionLocal

    try:
        with SessionLocal() as db:
            return get_multiplier(db, strategy)
    except Exception:  # noqa: BLE001 — never block trading on a lever read
        return 1.0


# --- per-regime size multipliers: {strategy: {regime: multiplier}} -----------
def regime_multipliers(db: Session) -> dict[str, dict[str, float]]:
    row = db.get(Setting, _REGIME_KEY)
    if row is None:
        return {}
    try:
        data = json.loads(row.value_json)
        return {s: {r: float(m) for r, m in regs.items()} for s, regs in data.items()}
    except (ValueError, AttributeError, json.JSONDecodeError):
        return {}


def get_regime_multiplier(db: Session, strategy: str, regime: str) -> float:
    return regime_multipliers(db).get(strategy, {}).get(regime, 1.0)


def set_regime_multiplier(db: Session, strategy: str, regime: str, mult: float) -> None:
    mult = max(MIN_MULT, min(MAX_MULT, float(mult)))
    current = regime_multipliers(db)
    current.setdefault(strategy, {})[regime] = mult
    row = db.get(Setting, _REGIME_KEY)
    payload = json.dumps(current)
    if row is None:
        db.add(Setting(key=_REGIME_KEY, value_json=payload))
    else:
        row.value_json = payload
    db.commit()


def regime_multiplier_safe(strategy: str, regime: str) -> float:
    """Session-managing read for the paper-trader (own short-lived session)."""
    from app.db.session import SessionLocal

    try:
        with SessionLocal() as db:
            return get_regime_multiplier(db, strategy, regime)
    except Exception:  # noqa: BLE001 — never block trading on a lever read
        return 1.0


def lever_summary(db: Session) -> dict[str, Any]:
    return {
        "size_multipliers": size_multipliers(db),
        "regime_multipliers": regime_multipliers(db),
    }
