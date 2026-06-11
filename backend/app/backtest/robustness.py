"""Robustness tooling — guards against overfitting before promoting a strategy.

All functions reuse the event-driven engine (`run_backtest`) so results match
live behaviour. They take an already-loaded candle DataFrame to avoid refetching.

- parameter_sweep: grid search + 2-param heatmap + ±10% perturbation stability.
- out_of_sample: optimize on the first train_frac, report on the held-out tail.
- walk_forward: rolling optimize→test windows; report per-window consistency.
- monte_carlo: bootstrap the trade sequence → return/drawdown confidence bands.
"""
from __future__ import annotations

import itertools
import random
from typing import Any

import numpy as np
import pandas as pd

from app.backtest.engine import BacktestConfig, run_backtest

MAX_COMBOS = 256  # safety cap on a sweep


def _metric(metrics: dict[str, Any], key: str) -> float:
    v = metrics.get(key)
    return float(v) if isinstance(v, (int, float)) else 0.0


def _grid_combos(param_grid: dict[str, list[Any]]) -> list[dict[str, Any]]:
    if not param_grid:
        return [{}]
    keys = list(param_grid)
    combos = [dict(zip(keys, vals, strict=False)) for vals in itertools.product(*[param_grid[k] for k in keys])]
    return combos[:MAX_COMBOS]


def _summary(strategy: str, params: dict[str, Any], df: pd.DataFrame,
             symbol: str, timeframe: str, cfg: BacktestConfig) -> dict[str, Any]:
    res = run_backtest(symbol, timeframe, df, strategy, params, cfg)
    m = res.metrics
    return {
        "params": params,
        "return_pct": m["return_pct"],
        "sharpe": m["sharpe"],
        "sortino": m["sortino"],
        "max_drawdown_pct": m["max_drawdown_pct"],
        "win_rate": m["win_rate"],
        "profit_factor": m["profit_factor"],
        "total_trades": m["total_trades"],
        "_trades": res.trades,  # kept for Monte Carlo; stripped before JSON if large
    }


def _optimize(df: pd.DataFrame, strategy: str, param_grid: dict[str, list[Any]],
              symbol: str, timeframe: str, cfg: BacktestConfig, metric: str) -> dict[str, Any]:
    best: dict[str, Any] | None = None
    for combo in _grid_combos(param_grid):
        s = _summary(strategy, combo, df, symbol, timeframe, cfg)
        if best is None or _metric(s, metric) > _metric(best, metric):
            best = s
    return best or {"params": {}}


def parameter_sweep(symbol: str, timeframe: str, df: pd.DataFrame, strategy: str,
                    param_grid: dict[str, list[Any]], cfg: BacktestConfig,
                    metric: str = "sharpe") -> dict[str, Any]:
    combos = _grid_combos(param_grid)
    rows = [_summary(strategy, c, df, symbol, timeframe, cfg) for c in combos]
    for r in rows:
        r.pop("_trades", None)
    rows.sort(key=lambda r: _metric(r, metric), reverse=True)
    best = rows[0] if rows else {"params": {}}

    # 2-param heatmap of the chosen metric.
    heatmap = None
    if len(param_grid) == 2:
        kx, ky = list(param_grid)
        heatmap = {
            "x_param": kx, "y_param": ky,
            "x_values": param_grid[kx], "y_values": param_grid[ky],
            "metric": metric,
            "matrix": [
                [next((_metric(r, metric) for r in rows
                       if r["params"].get(kx) == xv and r["params"].get(ky) == yv), None)
                 for xv in param_grid[kx]]
                for yv in param_grid[ky]
            ],
        }

    # ±10% perturbation of the best params — fragile if the edge collapses.
    base_params = best.get("params", {})
    base_metric = _metric(best, metric)
    perturbation = []
    for k, v in base_params.items():
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            continue
        results = {}
        for tag, factor in (("down", 0.9), ("up", 1.1)):
            pv = type(v)(round(v * factor)) if isinstance(v, int) else round(v * factor, 6)
            if pv == v:
                pv = v + (1 if isinstance(v, int) else v * 0.1)
            s = _summary(strategy, {**base_params, k: pv}, df, symbol, timeframe, cfg)
            results[tag] = round(_metric(s, metric), 3)
        # Fragile if either side flips sign or drops >50% vs base.
        fragile = any(
            (base_metric > 0 and (rv <= 0 or rv < base_metric * 0.5)) for rv in results.values()
        )
        perturbation.append({"param": k, "base": round(base_metric, 3), **results, "fragile": fragile})

    return {
        "metric": metric,
        "combos_tested": len(rows),
        "results": rows[:50],
        "best": best,
        "heatmap": heatmap,
        "perturbation": perturbation,
        "robust": all(not p["fragile"] for p in perturbation) if perturbation else None,
    }


def out_of_sample(symbol: str, timeframe: str, df: pd.DataFrame, strategy: str,
                  param_grid: dict[str, list[Any]], cfg: BacktestConfig,
                  metric: str = "sharpe", train_frac: float = 0.7) -> dict[str, Any]:
    split = int(len(df) * train_frac)
    train_df, test_df = df.iloc[:split], df.iloc[split:]
    best = _optimize(train_df, strategy, param_grid, symbol, timeframe, cfg, metric)
    params = best.get("params", {})
    train_m = run_backtest(symbol, timeframe, train_df, strategy, params, cfg).metrics
    test_m = run_backtest(symbol, timeframe, test_df, strategy, params, cfg).metrics
    return {
        "best_params": params,
        "train": train_m,
        "test": test_m,
        "degradation_pct": round(train_m["return_pct"] - test_m["return_pct"], 2),
        "held_up": test_m[metric] > 0 if metric in test_m else test_m["return_pct"] > 0,
    }


def walk_forward(symbol: str, timeframe: str, df: pd.DataFrame, strategy: str,
                 param_grid: dict[str, list[Any]], cfg: BacktestConfig,
                 metric: str = "sharpe", folds: int = 5) -> dict[str, Any]:
    n = len(df)
    seg = n // (folds + 1)
    if seg < 30:  # not enough data to split meaningfully
        return {"windows": [], "note": "not enough data for walk-forward"}
    windows = []
    for i in range(folds):
        train_df = df.iloc[: seg * (i + 1)]
        test_df = df.iloc[seg * (i + 1): seg * (i + 2)]
        if len(test_df) < 20:
            break
        best = _optimize(train_df, strategy, param_grid, symbol, timeframe, cfg, metric)
        params = best.get("params", {})
        test_m = run_backtest(symbol, timeframe, test_df, strategy, params, cfg).metrics
        windows.append({
            "window": i + 1,
            "params": params,
            "test_return_pct": test_m["return_pct"],
            "test_sharpe": test_m["sharpe"],
            "test_trades": test_m["total_trades"],
        })
    positive = sum(1 for w in windows if w["test_return_pct"] > 0)
    return {
        "windows": windows,
        "consistency_pct": round(positive / len(windows) * 100, 1) if windows else 0.0,
        "avg_test_return_pct": round(float(np.mean([w["test_return_pct"] for w in windows])), 2)
        if windows else 0.0,
    }


def monte_carlo(trades: list[dict[str, Any]], initial_capital: float,
                n_iter: int = 1000, seed: int = 42) -> dict[str, Any] | None:
    pnls = [t["pnl"] for t in trades]
    if len(pnls) < 5:
        return None
    rng = random.Random(seed)
    finals, drawdowns = [], []
    for _ in range(n_iter):
        seq = [pnls[rng.randrange(len(pnls))] for _ in range(len(pnls))]  # bootstrap
        equity = initial_capital
        peak = equity
        max_dd = 0.0
        for p in seq:
            equity += p
            peak = max(peak, equity)
            dd = (equity - peak) / peak * 100 if peak else 0.0
            max_dd = min(max_dd, dd)
        finals.append((equity / initial_capital - 1) * 100)
        drawdowns.append(max_dd)

    def pct(arr: list[float], q: float) -> float:
        return round(float(np.percentile(arr, q)), 2)

    return {
        "iterations": n_iter,
        "return_p5": pct(finals, 5),
        "return_p50": pct(finals, 50),
        "return_p95": pct(finals, 95),
        "max_drawdown_p50": pct(drawdowns, 50),
        "max_drawdown_p95": pct(drawdowns, 5),  # 5th pct = worst-5% drawdown
        "prob_profit_pct": round(sum(1 for f in finals if f > 0) / len(finals) * 100, 1),
    }
