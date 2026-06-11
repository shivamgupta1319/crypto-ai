"""Walk-forward auto-optimizer (N10 stage 4).

Periodically re-tunes an active strategy's params on recent data and proposes a
change ONLY when the new params beat the current ones out-of-sample. The proposal
is surfaced for human approval — nothing is applied automatically.

Anti-overfitting: the candidate must (a) win on the out-of-sample test slice and
(b) post a positive walk-forward consistency, not just a better in-sample fit.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from app.backtest import robustness
from app.backtest.engine import BacktestConfig, run_backtest

# Small, sane sweep grids per strategy param (kept tight to limit combinations).
DEFAULT_GRIDS: dict[str, dict[str, list[Any]]] = {
    "ema_trend_adx": {"ema_fast": [10, 20, 30], "ema_slow": [50, 100], "adx_min": [15, 20, 25]},
    "macd_rsi": {"rsi_length": [9, 14, 21], "rsi_overbought": [70, 75], "rsi_oversold": [25, 30]},
    "supertrend": {"atr_length": [10, 14], "multiplier": [2.0, 3.0, 4.0]},
    "bollinger_meanrev": {"length": [14, 20, 30], "mult": [2.0, 2.5]},
    "donchian_breakout": {"length": [20, 40, 55]},
    "ichimoku": {"tenkan": [7, 9], "kijun": [22, 26]},
    "stochrsi": {"length": [14, 21], "k": [3, 5]},
    "parabolic_sar": {"step": [0.01, 0.02], "max_step": [0.1, 0.2]},
}


def grid_for(strategy: str) -> dict[str, list[Any]]:
    return DEFAULT_GRIDS.get(strategy, {})


def propose_params(
    symbol: str,
    timeframe: str,
    df: pd.DataFrame,
    strategy: str,
    current_params: dict[str, Any] | None,
    cfg: BacktestConfig | None = None,
    metric: str = "sharpe",
) -> dict[str, Any]:
    """Return an optimization result + whether to propose a param change.

    ``recommend`` is True only when the optimized params beat current OOS on the
    chosen metric and walk-forward consistency is >= 60%."""
    cfg = cfg or BacktestConfig()
    grid = grid_for(strategy)
    if not grid:
        return {"available": False, "reason": f"No tuning grid defined for {strategy}."}
    if df.empty or len(df) < 150:
        return {"available": False, "reason": "Need >= 150 candles to optimize."}

    oos = robustness.out_of_sample(symbol, timeframe, df, strategy, grid, cfg, metric)
    wf = robustness.walk_forward(symbol, timeframe, df, strategy, grid, cfg, metric)

    # Current params evaluated on the same test slice for a fair comparison.
    split = int(len(df) * 0.7)
    test_df = df.iloc[split:]
    cur_test = run_backtest(symbol, timeframe, test_df, strategy, current_params or {}, cfg).metrics
    cand_test = oos["test"]

    cur_metric = cur_test.get(metric, 0.0) or 0.0
    cand_metric = cand_test.get(metric, 0.0) or 0.0
    consistency = wf.get("consistency_pct", 0.0)
    params_changed = oos["best_params"] != (current_params or {})

    recommend = bool(
        params_changed
        and cand_metric > cur_metric
        and cand_test.get("return_pct", 0) > cur_test.get("return_pct", 0)
        and consistency >= 60.0
    )
    return {
        "available": True,
        "metric": metric,
        "current_params": current_params or {},
        "proposed_params": oos["best_params"],
        "current_test": {"return_pct": cur_test["return_pct"], metric: cur_metric},
        "proposed_test": {"return_pct": cand_test["return_pct"], metric: cand_metric},
        "walk_forward_consistency_pct": consistency,
        "recommend": recommend,
    }
