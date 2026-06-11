"""Runtime-editable settings backed by the ``settings`` DB table.

Defaults come from ``config.py``. This layer lets the user tune risk/leverage/
universe from the Settings UI without editing code or restarting (most knobs
take effect immediately; the scan interval applies on the next scheduler start).

Each editable field has a validator + bounds so the API can't be driven into an
unsafe state (e.g. leverage above the hard cap or risk above 10%).
"""
from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.config import settings
from app.models import Setting


@dataclass(frozen=True)
class Field:
    key: str
    kind: str  # "float" | "int" | "bool" | "symbols" | "timeframes"
    label: str
    minimum: float | None = None
    maximum: float | None = None
    note: str | None = None


# Whitelist of what the UI may edit. Anything not here is config-only.
FIELDS: list[Field] = [
    Field("risk_per_trade_pct", "float", "Risk per trade (%)", 0.1, 10.0),
    Field("default_leverage", "float", "Default leverage (x)", 1.0, 30.0),
    Field("max_leverage", "float", "Max leverage cap (x)", 1.0, 30.0),
    Field("max_concurrent_positions", "int", "Max concurrent positions", 1, 50),
    Field("max_position_pct", "float", "Max position size (% equity)", 1.0, 100.0),
    Field("daily_max_loss_pct", "float", "Daily loss kill-switch (%)", 0.5, 50.0),
    Field("trailing_enabled", "bool", "Trailing stop enabled"),
    Field("trail_activate_pct", "float", "Trail activate (%)", 0.1, 20.0),
    Field("trail_distance_pct", "float", "Trail distance (%)", 0.1, 20.0),
    Field("scan_interval_seconds", "int", "Scan interval (s)", 15, 3600,
          note="Applies on next backend restart."),
    Field("symbols", "symbols", "Symbol universe", note="Binance USDⓈ-M perpetuals, e.g. BTCUSDT."),
    Field("timeframes", "timeframes", "Timeframes"),
    Field("meta_label_enabled", "bool", "Meta-label filter (AI)",
          note="Gate new entries by the trained P(win) model."),
    Field("meta_label_threshold", "float", "Meta-label P(win) threshold", 0.4, 0.9),
]
_BY_KEY = {f.key: f for f in FIELDS}

_VALID_TF = {"1m", "5m", "15m", "30m", "1h", "4h", "1d"}


def _coerce(field: Field, value: Any) -> Any:
    """Validate + coerce a raw value for a field, raising ValueError on bad input."""
    if field.kind in ("float", "int"):
        try:
            num = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{field.label}: must be a number") from exc
        if field.minimum is not None and num < field.minimum:
            raise ValueError(f"{field.label}: min is {field.minimum}")
        if field.maximum is not None and num > field.maximum:
            raise ValueError(f"{field.label}: max is {field.maximum}")
        return int(num) if field.kind == "int" else num
    if field.kind == "bool":
        return bool(value)
    if field.kind == "symbols":
        if not isinstance(value, list) or not value:
            raise ValueError("Symbol universe must be a non-empty list")
        syms = [str(s).upper().strip() for s in value]
        for s in syms:
            if not s.endswith("USDT") or len(s) < 6:
                raise ValueError(f"Invalid symbol '{s}' (expected like BTCUSDT)")
        return list(dict.fromkeys(syms))  # de-dupe, preserve order
    if field.kind == "timeframes":
        if not isinstance(value, list) or not value:
            raise ValueError("Timeframes must be a non-empty list")
        tfs = [str(t).strip() for t in value]
        bad = [t for t in tfs if t not in _VALID_TF]
        if bad:
            raise ValueError(f"Invalid timeframes {bad}. Allowed: {sorted(_VALID_TF)}")
        return list(dict.fromkeys(tfs))
    raise ValueError(f"Unknown field kind: {field.kind}")


def _apply(key: str, value: Any) -> None:
    """Mutate the live settings singleton (pydantic instances are mutable)."""
    setattr(settings, key, value)


def load_overrides(db: Session) -> None:
    """Apply all stored overrides onto the live settings object (call at startup)."""
    rows = db.query(Setting).all()
    for row in rows:
        if row.key not in _BY_KEY:
            continue
        try:
            value = _coerce(_BY_KEY[row.key], json.loads(row.value_json))
            _apply(row.key, value)
        except (ValueError, json.JSONDecodeError):
            continue  # ignore corrupt/stale rows rather than failing boot


def effective() -> dict[str, Any]:
    """Current effective values for every editable field + their bounds/meta."""
    return {
        "values": {f.key: getattr(settings, f.key) for f in FIELDS},
        "fields": [
            {"key": f.key, "kind": f.kind, "label": f.label,
             "min": f.minimum, "max": f.maximum, "note": f.note}
            for f in FIELDS
        ],
    }


def update(db: Session, overrides: dict[str, Any]) -> dict[str, Any]:
    """Validate + persist + apply a batch of overrides. Raises ValueError if any
    value is invalid (nothing is applied in that case)."""
    unknown = [k for k in overrides if k not in _BY_KEY]
    if unknown:
        raise ValueError(f"Unknown settings: {unknown}")
    # Validate everything first (all-or-nothing).
    coerced = {k: _coerce(_BY_KEY[k], v) for k, v in overrides.items()}
    # Cross-field guard: default leverage can't exceed the (possibly new) cap.
    cap = coerced.get("max_leverage", settings.max_leverage)
    dft = coerced.get("default_leverage", settings.default_leverage)
    if dft > cap:
        raise ValueError("Default leverage can't exceed the max leverage cap")

    for key, value in coerced.items():
        row = db.get(Setting, key)
        payload = json.dumps(value)
        if row is None:
            db.add(Setting(key=key, value_json=payload))
        else:
            row.value_json = payload
        _apply(key, value)
    db.commit()
    return effective()


def reset(db: Session) -> dict[str, Any]:
    """Delete all overrides. Note: live settings stay until next restart reloads
    the (now empty) overrides — we re-import defaults by reconstructing them."""
    db.query(Setting).delete()
    db.commit()
    # Re-apply pristine defaults from a fresh Settings() construction.
    from app.config import Settings as _S

    fresh = _S()
    for f in FIELDS:
        _apply(f.key, getattr(fresh, f.key))
    return effective()


# Convenience for callers that need an apply function (e.g. agent levers later).
APPLY: Callable[[str, Any], None] = _apply
