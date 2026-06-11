"""Build + persist labeled training samples (N10 stage 1).

Cold-start: run a strategy over a candle window, and for each entry event compute
the context features (at the entry bar) + the triple-barrier outcome. This yields
a labeled dataset without waiting for live paper trades to accumulate.
"""
from __future__ import annotations

import json
from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.learning.features import ALL_FEATURES, compute_feature_frame, row_to_vector
from app.learning.labeling import triple_barrier
from app.models import TrainingSample
from app.strategies.base import enrich_df, merge_params, run_strategy, stop_target


def build_samples(
    symbol: str,
    timeframe: str,
    df: pd.DataFrame,
    strategy: str,
    params: dict[str, Any] | None = None,
    max_bars: int = 48,
    source: str = "backtest",
) -> list[dict[str, Any]]:
    """Return labeled feature samples for every entry event in ``df``."""
    if df.empty or len(df) < 80:
        return []
    df = enrich_df(strategy, df, symbol)
    run_params = merge_params(strategy, params)
    annotated = run_strategy(strategy, df, params)
    feats = compute_feature_frame(df)

    sig = annotated["signal"].to_numpy()
    atr = annotated["atr"].to_numpy()
    open_time = df["open_time"].to_numpy()

    samples: list[dict[str, Any]] = []
    prev = 0
    for i in range(1, len(df)):
        cur = int(sig[i])
        if cur != 0 and cur != prev and np.isfinite(atr[i]) and atr[i] > 0:
            entry = float(df["close"].iloc[i])
            stop, target = stop_target(cur, entry, float(atr[i]), run_params)
            res = triple_barrier(df, i, cur, stop, target, max_bars)
            if res is not None:
                frow = feats.iloc[i]
                if pd.isna(frow.get("rsi")) or pd.isna(frow.get("adx")):
                    prev = cur
                    continue  # warmup region — features not ready
                vec = row_to_vector(frow)
                samples.append({
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "strategy": strategy,
                    "direction": cur,
                    "regime": str(frow.get("regime", "ranging")),
                    "features": vec,
                    "label": int(res["label"]),
                    "realized_r": float(res["realized_r"]),
                    "bars_held": int(res["bars_held"]),
                    "source": source,
                    "bar_time": int(open_time[i]),
                })
        prev = cur
    return samples


def persist_samples(db: Session, samples: list[dict[str, Any]]) -> int:
    """Upsert samples; returns the number of new rows inserted (dupes ignored)."""
    if not samples:
        return 0
    payload = [{
        "symbol": s["symbol"], "timeframe": s["timeframe"], "strategy": s["strategy"],
        "direction": s["direction"], "regime": s["regime"],
        "features_json": json.dumps(s["features"]), "label": s["label"],
        "realized_r": s["realized_r"], "bars_held": s["bars_held"],
        "source": s["source"], "bar_time": s["bar_time"],
    } for s in samples]
    before = db.query(TrainingSample).count()
    stmt = sqlite_insert(TrainingSample).values(payload)
    stmt = stmt.on_conflict_do_nothing(
        index_elements=["symbol", "timeframe", "strategy", "bar_time", "source"]
    )
    db.execute(stmt)
    db.commit()
    return db.query(TrainingSample).count() - before


def load_dataset(
    db: Session, strategy: str | None = None, symbol: str | None = None
) -> tuple[np.ndarray, np.ndarray, list[TrainingSample]]:
    """Load (X, y, rows) for training. X is ordered by ALL_FEATURES."""
    stmt = select(TrainingSample)
    if strategy:
        stmt = stmt.where(TrainingSample.strategy == strategy)
    if symbol:
        stmt = stmt.where(TrainingSample.symbol == symbol)
    rows = db.execute(stmt).scalars().all()
    X, y = [], []
    for r in rows:
        feats = json.loads(r.features_json or "{}")
        X.append([float(feats.get(name, 0.0)) for name in ALL_FEATURES])
        y.append(int(r.label))
    return np.array(X, dtype=float), np.array(y, dtype=int), list(rows)


def dataset_stats(db: Session) -> dict[str, Any]:
    """Per-strategy sample counts + win rate, for the agent + UI."""
    rows = db.execute(select(TrainingSample)).scalars().all()
    by: dict[str, list[TrainingSample]] = {}
    for r in rows:
        by.setdefault(r.strategy, []).append(r)
    out = []
    for strat, rs in sorted(by.items()):
        wins = sum(1 for r in rs if r.label == 1)
        out.append({
            "strategy": strat,
            "samples": len(rs),
            "win_rate": round(wins / len(rs) * 100, 1) if rs else 0.0,
            "avg_r": round(sum(r.realized_r for r in rs) / len(rs), 3) if rs else 0.0,
        })
    return {"total": len(rows), "by_strategy": out}
