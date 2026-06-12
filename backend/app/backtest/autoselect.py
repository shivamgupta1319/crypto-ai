"""Auto-select — screen every coin × strategy × timeframe by backtest performance,
gate out insignificant / overfit results, rank, and optionally auto-promote the
winners to the live config.

Anti-overfitting (per the project's guiding principles): a candidate is only
*recommended* if it has enough trades to matter, is profitable, **holds up
out-of-sample** (train/test split), and shows no overfit red flags (absurd win
rate / profit factor / near-zero drawdown). Everything is still paper-only.
"""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.backtest.engine import BacktestConfig, run_backtest
from app.data.binance import load_candles
from app.models import ActiveStrategy
from app.strategies.base import all_strategies

# Metrics a user may rank by (all "higher is better"). "composite" is a balanced
# blend (default for one-click auto-select); the rest are single raw metrics.
RANK_METRICS = ("composite", "sharpe", "return_pct", "calmar", "sortino", "profit_factor")


def _composite(m: dict[str, Any]) -> float:
    """Balanced quality score: rewards return + risk-adjusted return + confidence
    (win rate, profit factor), and penalizes drawdown. Used so auto-select picks
    strategies that are profitable *and* steady, not just high-return/high-risk."""
    ret = (m.get("return_pct") or 0) / 100.0
    dd = abs(m.get("max_drawdown_pct") or 0) / 100.0
    sharpe = m.get("sharpe") or 0.0
    win = (m.get("win_rate") or 0) / 100.0
    pf = m.get("profit_factor")
    pf_term = min(float(pf), 3.0) if pf is not None else 1.0
    return round(sharpe + ret - 2.0 * dd + 0.5 * (win - 0.5) + 0.2 * pf_term, 4)


def _score(m: dict[str, Any], metric: str) -> float:
    if metric == "composite":
        return _composite(m)
    v = m.get(metric)
    return float(v) if v is not None else float("-inf")


def _iso_to_ms(value: str) -> int:
    from datetime import UTC, datetime

    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return int(dt.timestamp() * 1000)


def _red_flags(m: dict[str, Any]) -> list[str]:
    """Classic overfit warning signs — never auto-promote these."""
    flags: list[str] = []
    if m.get("win_rate", 0) > 85:
        flags.append("win-rate >85%")
    pf = m.get("profit_factor")
    if pf is not None and pf > 5:
        flags.append("profit-factor >5")
    if m.get("total_trades", 0) >= 5 and abs(m.get("max_drawdown_pct", 0) or 0) < 0.5:
        flags.append("drawdown ~0")
    return flags


def auto_select(
    db: Session,
    symbols: list[str],
    timeframes: list[str],
    strategies: list[str],
    start: str,
    end: str,
    metric: str = "sharpe",
    min_trades: int = 15,
    require_beat_buyhold: bool = False,
    oos_check: bool = True,
    cfg: BacktestConfig | None = None,
    top_n: int = 5,
    per_coin_top: int | None = None,
    promote: bool = False,
) -> dict[str, Any]:
    """Screen all combos, rank, and (optionally) promote the auto-selected picks.

    Selection is either the recommended top ``top_n`` overall, or — when
    ``per_coin_top`` is set — the best ``per_coin_top`` recommended pick(s) for
    each coin (the one-click "let the system choose per coin" mode)."""
    cfg = cfg or BacktestConfig()
    metric = metric if metric in RANK_METRICS else "composite"
    start_ms, end_ms = _iso_to_ms(start), _iso_to_ms(end)

    candidates: list[dict[str, Any]] = []
    for symbol in symbols:
        for timeframe in timeframes:
            try:
                df = load_candles(symbol, timeframe, start_ms, end_ms)
            except Exception:
                continue
            if df.empty or len(df) < 100:
                continue
            for strat in strategies:
                try:
                    full = run_backtest(symbol, timeframe, df, strat, None, cfg)
                except Exception:
                    continue
                m = full.metrics
                flags = _red_flags(m)

                # Out-of-sample: optimize nothing, just check the strategy holds on
                # unseen tail data (70/30 split).
                oos_held_up: bool | None = None
                oos_metric: float | None = None
                if oos_check and len(df) >= 150:
                    split = int(len(df) * 0.7)
                    test_df = df.iloc[split:]
                    try:
                        tm = run_backtest(symbol, timeframe, test_df, strat, None, cfg).metrics
                        oos_metric = _score(tm, metric)
                        oos_held_up = tm["return_pct"] > 0
                    except Exception:
                        oos_held_up = None

                # Rank by the OOS score when available (more trustworthy), else full.
                score = oos_metric if (oos_check and oos_metric is not None) else _score(m, metric)

                reasons: list[str] = []
                if m["total_trades"] < min_trades:
                    reasons.append(f"<{min_trades} trades")
                if m["return_pct"] <= 0:
                    reasons.append("not profitable")
                if require_beat_buyhold and m["return_pct"] <= m.get("buy_hold_return_pct", 0):
                    reasons.append("doesn't beat buy&hold")
                if oos_check and oos_held_up is False:
                    reasons.append("fails out-of-sample")
                if flags:
                    reasons.append("overfit red flags")
                recommended = not reasons

                candidates.append({
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "strategy": strat,
                    "score": round(float(score), 4) if score != float("-inf") else None,
                    "metric": metric,
                    "return_pct": m["return_pct"],
                    "buy_hold_return_pct": m.get("buy_hold_return_pct"),
                    "sharpe": m["sharpe"],
                    "total_trades": m["total_trades"],
                    "win_rate": m["win_rate"],
                    "max_drawdown_pct": m["max_drawdown_pct"],
                    "profit_factor": m["profit_factor"],
                    "oos_held_up": oos_held_up,
                    "flags": flags,
                    "recommended": recommended,
                    "excluded_reasons": reasons,
                })

    # Sort: recommended first, then by score desc.
    candidates.sort(
        key=lambda c: (c["recommended"], c["score"] if c["score"] is not None else float("-inf")),
        reverse=True,
    )
    recommended = [c for c in candidates if c["recommended"]]

    # Selection: best per coin (one-click mode) or top-N overall.
    if per_coin_top:
        by_coin: dict[str, list[dict[str, Any]]] = {}
        for c in recommended:  # already score-sorted
            by_coin.setdefault(c["symbol"], []).append(c)
        selected = [c for lst in by_coin.values() for c in lst[: max(1, per_coin_top)]]
        selected.sort(
            key=lambda c: c["score"] if c["score"] is not None else float("-inf"), reverse=True
        )
    else:
        selected = recommended[: max(0, top_n)]

    if promote and selected:
        for c in selected:
            c["active_id"] = _upsert_active(db, c["symbol"], c["timeframe"], c["strategy"])
            c["promoted"] = True
        db.commit()

    return {
        "metric": metric,
        "combos_tested": len(candidates),
        "candidates": candidates,
        "recommended_count": len(recommended),
        "selected": selected,
        "promoted": [c for c in selected if c.get("promoted")] if promote else [],
        "top_n": top_n,
        "per_coin_top": per_coin_top,
    }


def _upsert_active(db: Session, symbol: str, timeframe: str, strategy: str) -> int:
    existing = db.execute(
        select(ActiveStrategy).where(
            ActiveStrategy.symbol == symbol,
            ActiveStrategy.timeframe == timeframe,
            ActiveStrategy.strategy == strategy,
        )
    ).scalar_one_or_none()
    if existing:
        existing.enabled = 1
        existing.params_json = existing.params_json or "{}"
        db.flush()
        return existing.id
    row = ActiveStrategy(symbol=symbol, timeframe=timeframe, strategy=strategy,
                         params_json=json.dumps({}), enabled=1)
    db.add(row)
    db.flush()
    return row.id


def all_strategy_names() -> list[str]:
    return [s.name for s in all_strategies()]
