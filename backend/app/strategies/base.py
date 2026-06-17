"""Strategy contract + registry shared by the backtester and the live scanner.

A strategy is a pure function ``generate(df, params) -> pd.DataFrame`` that adds:
  - ``signal``: the *target position* at each bar's close — 1 (long), -1 (short), 0 (flat)
  - ``atr``:    ATR series used for stop/target placement

Because both the backtest engine and the live scanner call the exact same
function, a backtested edge behaves identically when traded live.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

GenerateFn = Callable[[pd.DataFrame, dict[str, Any]], pd.DataFrame]


@dataclass(frozen=True)
class StrategyDef:
    name: str
    description: str
    generate: GenerateFn
    default_params: dict[str, Any] = field(default_factory=dict)
    suited_for: list[str] = field(default_factory=list)  # e.g. ["BTCUSDT"]
    # Extra data columns a strategy needs merged onto the candle frame before it
    # runs (e.g. "funding" for perp-funding strategies). Attached by ``enrich_df``
    # in BOTH the backtest and live paths so the shared-function invariant holds.
    needs: tuple[str, ...] = ()


def enrich_df(name: str, df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """Attach any extra data columns a strategy declares via ``needs``.

    Called identically by the backtester and the live scanner so a funding-aware
    strategy sees the same inputs in both. Best-effort: if the data can't be
    fetched the column defaults to neutral so the strategy stays flat.
    """
    needs = get_strategy(name).needs
    if "funding" in needs and "funding" not in df.columns:
        from app.data.derivatives import attach_funding

        df = attach_funding(df, symbol)
    return df


_REGISTRY: dict[str, StrategyDef] = {}


def register(strategy: StrategyDef) -> StrategyDef:
    _REGISTRY[strategy.name] = strategy
    return strategy


def get_strategy(name: str) -> StrategyDef:
    if name not in _REGISTRY:
        raise KeyError(f"Unknown strategy: {name}. Available: {list(_REGISTRY)}")
    return _REGISTRY[name]


def all_strategies() -> list[StrategyDef]:
    return list(_REGISTRY.values())


def merge_params(name: str, overrides: dict[str, Any] | None) -> dict[str, Any]:
    params = dict(get_strategy(name).default_params)
    if overrides:
        params.update(overrides)
    return params


def run_strategy(
    name: str, df: pd.DataFrame, overrides: dict[str, Any] | None = None
) -> pd.DataFrame:
    """Run a registered strategy, returning df with ``signal`` and ``atr`` columns."""
    strat = get_strategy(name)
    params = merge_params(name, overrides)
    out = strat.generate(df.copy(), params)
    # Enforce the contract: signal is a target position in {-1, 0, 1}. NaN -> flat,
    # and any out-of-range value is clamped so a misbehaving strategy can't latch a
    # non-reversing position downstream (backtester/scanner rely on this invariant).
    out["signal"] = out["signal"].fillna(0).clip(-1, 1).astype(int)
    return out


def stop_target(
    direction: int, entry: float, atr_value: float, params: dict[str, Any]
) -> tuple[float, float]:
    """Compute (stop, target) from ATR and the reward:risk multiple in params."""
    stop_mult = float(params.get("atr_stop_mult", 2.0))
    rr = float(params.get("rr", 2.0))
    risk = atr_value * stop_mult
    if direction == 1:  # long
        return entry - risk, entry + risk * rr
    return entry + risk, entry - risk * rr  # short
