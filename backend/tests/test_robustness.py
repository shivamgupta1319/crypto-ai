"""Robustness suite tests on synthetic candles (no network)."""
from __future__ import annotations

from app.backtest.engine import BacktestConfig, run_backtest
from app.backtest.robustness import (
    monte_carlo,
    out_of_sample,
    parameter_sweep,
    walk_forward,
)

CFG = BacktestConfig()


def test_parameter_sweep_ranks_and_perturbs(trending_up):
    grid = {"st_mult": [2.0, 3.0, 4.0]}
    out = parameter_sweep("BTCUSDT", "1h", trending_up, "supertrend", grid, CFG, "return_pct")
    assert out["combos_tested"] == 3
    # Ranked descending by the chosen metric.
    rets = [r["return_pct"] for r in out["results"]]
    assert rets == sorted(rets, reverse=True)
    assert out["best"]["params"]["st_mult"] in (2.0, 3.0, 4.0)
    assert len(out["perturbation"]) >= 1
    assert out["robust"] in (True, False)


def test_parameter_sweep_heatmap_two_params(trending_up):
    grid = {"st_length": [7, 10], "st_mult": [2.0, 3.0]}
    out = parameter_sweep("BTCUSDT", "1h", trending_up, "supertrend", grid, CFG, "return_pct")
    hm = out["heatmap"]
    assert hm is not None
    assert hm["x_param"] == "st_length" and hm["y_param"] == "st_mult"
    assert len(hm["matrix"]) == 2 and len(hm["matrix"][0]) == 2


def test_out_of_sample_split(trending_up):
    grid = {"st_mult": [2.0, 3.0]}
    out = out_of_sample("BTCUSDT", "1h", trending_up, "supertrend", grid, CFG, "return_pct")
    assert "train" in out and "test" in out
    assert "best_params" in out
    assert isinstance(out["held_up"], bool)


def test_walk_forward_windows(trending_up):
    grid = {"st_mult": [2.0, 3.0]}
    out = walk_forward("BTCUSDT", "1h", trending_up, "supertrend", grid, CFG, "return_pct", folds=3)
    assert len(out["windows"]) >= 1
    assert 0.0 <= out["consistency_pct"] <= 100.0


def test_monte_carlo_percentiles(trending_up):
    res = run_backtest("BTCUSDT", "1h", trending_up, "supertrend")
    mc = monte_carlo(res.trades, CFG.initial_capital, n_iter=200)
    assert mc is not None
    assert mc["return_p5"] <= mc["return_p50"] <= mc["return_p95"]
    assert 0.0 <= mc["prob_profit_pct"] <= 100.0


def test_monte_carlo_too_few_trades():
    assert monte_carlo([{"pnl": 1.0}], 100000, n_iter=50) is None
