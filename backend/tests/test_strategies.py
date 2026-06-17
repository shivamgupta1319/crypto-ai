"""Strategy library smoke tests on synthetic candles."""
from __future__ import annotations

import pytest

from app.strategies.base import all_strategies, run_strategy, stop_target


def test_all_strategies_registered():
    names = {s.name for s in all_strategies()}
    expected = {
        "ema_trend_adx", "macd_rsi", "supertrend",
        "bollinger_meanrev", "donchian_breakout", "vwap_ema_pullback",
        "ichimoku", "stochrsi", "ttm_squeeze", "bollinger_pctb", "parabolic_sar",
    }
    assert expected <= names
    assert len(names) >= 11


@pytest.mark.parametrize("name", [s.name for s in all_strategies()])
def test_strategy_outputs_signal_and_atr(name, trending_up):
    out = run_strategy(name, trending_up)
    assert "signal" in out.columns
    assert "atr" in out.columns
    assert set(out["signal"].unique()) <= {-1, 0, 1}
    assert len(out) == len(trending_up)


def test_run_strategy_clamps_out_of_range_signals(trending_up):
    """A misbehaving strategy emitting values outside {-1,0,1} (or NaN) must be
    clamped so the backtester/scanner never latch a non-reversing position."""
    import numpy as np

    from app.strategies.base import _REGISTRY, StrategyDef, register, run_strategy

    def bad_generate(df, params):
        df["atr"] = 1.0
        df["signal"] = 2  # out of contract range
        df.iloc[0, df.columns.get_loc("signal")] = np.nan
        df.iloc[1, df.columns.get_loc("signal")] = -5
        return df

    register(StrategyDef(name="_bad_test", description="x", generate=bad_generate))
    try:
        out = run_strategy("_bad_test", trending_up)
        assert set(out["signal"].unique()) <= {-1, 0, 1}
        assert out["signal"].iloc[0] == 0   # NaN -> flat
        assert out["signal"].iloc[1] == -1  # -5 clamped
        assert out["signal"].iloc[2] == 1   # 2 clamped
    finally:
        _REGISTRY.pop("_bad_test", None)


def test_ema_trend_goes_long_in_uptrend(trending_up):
    out = run_strategy("ema_trend_adx", trending_up)
    # A persistent uptrend should produce some long target-position bars.
    assert (out["signal"] == 1).sum() > 0
    assert (out["signal"] == -1).sum() == 0


def test_supertrend_always_in_market(trending_up):
    out = run_strategy("supertrend", trending_up)
    # Supertrend is a continuous-position strategy: never flat after warmup.
    assert (out["signal"].iloc[50:] != 0).all()


def test_parabolic_sar_always_in_market(trending_up):
    out = run_strategy("parabolic_sar", trending_up)
    assert (out["signal"].iloc[50:] != 0).all()


def test_ichimoku_long_in_uptrend(trending_up):
    out = run_strategy("ichimoku", trending_up)
    assert (out["signal"] == 1).sum() > 0


def test_new_strategies_short_in_downtrend(trending_down):
    # Trend-following additions should be able to go short.
    for name in ("ichimoku", "parabolic_sar"):
        out = run_strategy(name, trending_down)
        assert (out["signal"] == -1).sum() > 0


def test_stop_target_long_and_short():
    stop, target = stop_target(1, 100.0, 2.0, {"atr_stop_mult": 2.0, "rr": 2.0})
    assert stop == pytest.approx(96.0)   # 100 - 2*2
    assert target == pytest.approx(108.0)  # 100 + 2*2*2
    stop_s, target_s = stop_target(-1, 100.0, 2.0, {"atr_stop_mult": 2.0, "rr": 2.0})
    assert stop_s == pytest.approx(104.0)
    assert target_s == pytest.approx(92.0)
