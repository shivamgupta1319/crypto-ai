"""Meta-labeling model (N10 stage 3) — the core loss-reducer.

A secondary classifier scores each base-strategy signal with P(win) from its
context features. At signal time we only take the trade when P(win) >= threshold,
and can use the score to scale size. The model is trained on the triple-barrier
labeled dataset (stage 1), validated out-of-sample, and persisted to disk.

Adoption rule (enforced by the agent, not here): only use the filter if it
improves out-of-sample Sharpe AND reduces losing trades vs unfiltered.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import numpy as np
from sqlalchemy.orm import Session

from app.config import BASE_DIR
from app.learning.dataset import load_dataset
from app.learning.features import ALL_FEATURES, vector_list

logger = logging.getLogger("cryptoai.metalabel")

MODEL_DIR = BASE_DIR / "models"
MIN_SAMPLES = 100  # cold-start guard: don't trust a model trained on too little

# Lazily-loaded in-memory model cache, keyed by strategy ("__all__" for global).
_loaded: dict[str, Any] = {}


def _model_path(strategy: str) -> Path:
    safe = strategy.replace("/", "_")
    return MODEL_DIR / f"metalabel_{safe}.joblib"


def train(
    db: Session, strategy: str | None = None, test_frac: float = 0.3
) -> dict[str, Any]:
    """Train + out-of-sample evaluate a gradient-boosted classifier. Persists the
    model and returns metrics. Raises ValueError if there isn't enough data."""
    from sklearn.ensemble import GradientBoostingClassifier
    from sklearn.metrics import roc_auc_score

    X, y, _rows = load_dataset(db, strategy=strategy)
    key = strategy or "__all__"
    if len(X) < MIN_SAMPLES:
        raise ValueError(
            f"Need >= {MIN_SAMPLES} samples to train (have {len(X)}). "
            "Build more from backtests first."
        )
    if len(set(y.tolist())) < 2:
        raise ValueError("Training data has only one outcome class; need both wins and losses.")

    # Time-ordered split (rows come back in insertion/bar order) — no shuffling,
    # to approximate out-of-sample rather than leak future bars into training.
    split = int(len(X) * (1 - test_frac))
    X_tr, X_te, y_tr, y_te = X[:split], X[split:], y[:split], y[split:]
    if len(X_te) < 20 or len(set(y_te.tolist())) < 2:
        # Fall back to a random split if the tail is degenerate.
        from sklearn.model_selection import train_test_split

        X_tr, X_te, y_tr, y_te = train_test_split(
            X, y, test_size=test_frac, random_state=42, stratify=y
        )

    clf = GradientBoostingClassifier(random_state=42, n_estimators=120, max_depth=3)
    clf.fit(X_tr, y_tr)

    proba_te = clf.predict_proba(X_te)[:, 1]
    try:
        auc = float(roc_auc_score(y_te, proba_te))
    except ValueError:
        auc = float("nan")
    base_rate = float(np.mean(y))

    # Importance of each feature (rounded), for the agent's explanation.
    importances = {
        name: round(float(imp), 4)
        for name, imp in zip(ALL_FEATURES, clf.feature_importances_, strict=False)
    }

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    import joblib

    joblib.dump({"clf": clf, "features": list(ALL_FEATURES)}, _model_path(key))
    _loaded[key] = {"clf": clf}
    meta = {
        "strategy": key,
        "samples": int(len(X)),
        "train": int(len(X_tr)),
        "test": int(len(X_te)),
        "oos_auc": round(auc, 3) if auc == auc else None,  # NaN-safe
        "base_win_rate": round(base_rate * 100, 1),
        "top_features": dict(sorted(importances.items(), key=lambda kv: kv[1], reverse=True)[:5]),
    }
    (MODEL_DIR / f"metalabel_{key.replace('/', '_')}.json").write_text(json.dumps(meta))
    return meta


def _load(strategy: str):
    key = strategy
    if key in _loaded:
        return _loaded[key]
    path = _model_path(key)
    if not path.exists():
        # Fall back to a global model if a per-strategy one isn't trained.
        if strategy != "__all__":
            return _load("__all__")
        return None
    import joblib

    try:
        bundle = joblib.load(path)
        _loaded[key] = bundle
        return bundle
    except Exception as exc:  # noqa: BLE001
        logger.warning("failed to load metalabel model %s: %s", key, exc)
        return None


def p_win(features: dict[str, float], strategy: str) -> float | None:
    """P(win) for a signal's feature vector, or None if no model is available."""
    bundle = _load(strategy)
    if bundle is None:
        return None
    clf = bundle["clf"]
    x = np.array([vector_list(features)], dtype=float)
    try:
        return round(float(clf.predict_proba(x)[0, 1]), 4)
    except Exception:  # noqa: BLE001
        return None


def predict_mask(strategy: str, df, threshold: float) -> np.ndarray | None:
    """Per-bar boolean entry mask: True where P(win) >= threshold. None if no model.

    Warmup bars with non-finite features are masked False (don't trade blind).
    """
    bundle = _load(strategy)
    if bundle is None:
        return None
    from app.learning.features import ALL_FEATURES as _AF
    from app.learning.features import compute_feature_frame, row_to_vector

    feats = compute_feature_frame(df)
    clf = bundle["clf"]
    rows = []
    valid = []
    for _, row in feats.iterrows():
        ok = bool(np.isfinite(row.get("rsi", np.nan)) and np.isfinite(row.get("adx", np.nan)))
        valid.append(ok)
        vec = row_to_vector(row)
        rows.append([vec.get(n, 0.0) for n in _AF])
    proba = clf.predict_proba(np.array(rows, dtype=float))[:, 1]
    mask = (proba >= threshold) & np.array(valid)
    return mask


def evaluate_filter(
    symbol: str, timeframe: str, df, strategy: str,
    params: dict[str, Any] | None = None, cfg=None, threshold: float = 0.5,
) -> dict[str, Any]:
    """Backtest the strategy with and without the meta-label filter and compare.

    The agent adopts the filter only if it raises OOS Sharpe AND cuts losing
    trades — this function returns the numbers that decision is based on."""
    from app.backtest.engine import BacktestConfig, run_backtest

    cfg = cfg or BacktestConfig()
    mask = predict_mask(strategy, df, threshold)
    if mask is None:
        return {"available": False, "reason": "No trained model for this strategy."}

    base = run_backtest(symbol, timeframe, df, strategy, params, cfg)
    filt = run_backtest(symbol, timeframe, df, strategy, params, cfg, entry_mask=mask)

    def _losers(res):
        return sum(1 for t in res.trades if t["pnl"] < 0)

    b, f = base.metrics, filt.metrics
    improved = (
        f.get("sharpe", 0) >= b.get("sharpe", 0)
        and _losers(filt) <= _losers(base)
        and f.get("total_trades", 0) > 0
    )
    return {
        "available": True,
        "threshold": threshold,
        "without": {"return_pct": b["return_pct"], "sharpe": b["sharpe"],
                    "trades": b["total_trades"], "win_rate": b["win_rate"],
                    "max_drawdown_pct": b["max_drawdown_pct"], "losers": _losers(base)},
        "with": {"return_pct": f["return_pct"], "sharpe": f["sharpe"],
                 "trades": f["total_trades"], "win_rate": f["win_rate"],
                 "max_drawdown_pct": f["max_drawdown_pct"], "losers": _losers(filt)},
        "improved": bool(improved),
    }


def model_status(db: Session | None = None) -> dict[str, Any]:
    """Which meta-label models are trained on disk + their saved metrics."""
    if not MODEL_DIR.exists():
        return {"models": []}
    out = []
    for meta_file in sorted(MODEL_DIR.glob("metalabel_*.json")):
        try:
            out.append(json.loads(meta_file.read_text()))
        except Exception:  # noqa: BLE001
            continue
    return {"models": out, "min_samples": MIN_SAMPLES}


def reset_cache() -> None:
    _loaded.clear()
