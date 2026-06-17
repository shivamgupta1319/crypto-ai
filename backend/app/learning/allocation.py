"""Adaptive allocation / auto-disable analysis (N10 stage 5).

Reads realized paper performance per strategy (and per-regime win rates from the
labeled dataset) and proposes bounded changes:
  - disable a persistent loser (enough trades, negative P&L, low win rate)
  - scale a strong/weak performer's size multiplier (within hard bounds)
  - re-enable a disabled strategy whose dataset edge looks favorable again

These are *proposals*; the agent persists them for human approval.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ActiveStrategy, TrainingSample
from app.portfolio.engine import strategy_attribution

# Bounds on the size multiplier lever (the agent can never exceed these).
MIN_MULT, MAX_MULT = 0.25, 2.0
MIN_TRADES_TO_JUDGE = 10


def per_regime_winrate(db: Session) -> dict[str, dict[str, dict[str, float]]]:
    """{strategy: {regime: {win_rate, samples}}} from the labeled dataset."""
    rows = db.execute(select(TrainingSample)).scalars().all()
    agg: dict[str, dict[str, list[int]]] = {}
    for r in rows:
        agg.setdefault(r.strategy, {}).setdefault(r.regime, []).append(r.label)
    out: dict[str, dict[str, dict[str, float]]] = {}
    for strat, regimes in agg.items():
        out[strat] = {
            reg: {"win_rate": round(sum(labels) / len(labels) * 100, 1), "samples": len(labels)}
            for reg, labels in regimes.items()
        }
    return out


def analyze(db: Session) -> dict[str, Any]:
    """Realized per-strategy performance + per-regime edge for the UI/agent."""
    attribution = strategy_attribution(db)
    regimes = per_regime_winrate(db)
    actives = {
        a.strategy: a for a in db.execute(select(ActiveStrategy)).scalars().all()
    }
    rows = []
    for a in attribution:
        strat = a["strategy"]
        rows.append({
            **a,
            "active": strat in actives,
            "enabled": bool(actives[strat].enabled) if strat in actives else False,
            "regimes": regimes.get(strat, {}),
        })
    return {"strategies": rows, "regimes": regimes}


def propose(db: Session) -> list[dict[str, Any]]:
    """Generate allocation proposals (not persisted here — the agent does that)."""
    attribution = strategy_attribution(db)
    actives = {a.strategy: a for a in db.execute(select(ActiveStrategy)).scalars().all()}
    proposals: list[dict[str, Any]] = []

    for a in attribution:
        strat = a["strategy"]
        trades, net, win = a["trades"], a["net_pnl"], a["win_rate"]
        if trades < MIN_TRADES_TO_JUDGE:
            continue
        active = actives.get(strat)

        # Persistent loser -> propose disable.
        if active is not None and active.enabled and net < 0 and win < 40:
            proposals.append({
                "kind": "disable_strategy",
                "title": f"Disable {strat} (losing)",
                "rationale": (
                    f"{strat} is net {net} over {trades} paper trades with a {win}% win "
                    f"rate — a persistent loser. Proposing to disable it."
                ),
                "payload": {"strategy": strat},
                "prev": {"enabled": True},
                "confidence": 0.7,
            })
        # Strong winner -> propose a size bump (bounded).
        elif active is not None and active.enabled and net > 0 and win >= 55 and trades >= 15:
            proposals.append({
                "kind": "set_size_multiplier",
                "title": f"Increase {strat} size to 1.5x",
                "rationale": (
                    f"{strat} is net +{net} over {trades} trades at {win}% win rate — "
                    f"proposing a 1.5x size multiplier (bounded at {MAX_MULT}x)."
                ),
                "payload": {"strategy": strat, "multiplier": 1.5},
                "prev": {"multiplier": 1.0},
                "confidence": 0.6,
            })

    # Per-regime weak spots: a strategy that loses badly in a specific regime gets
    # a proposed size reduction *in that regime only* (bounded lever).
    for strat, regimes in per_regime_winrate(db).items():
        for reg, stat in regimes.items():
            if stat["samples"] >= MIN_TRADES_TO_JUDGE and stat["win_rate"] < 35:
                proposals.append({
                    "kind": "set_regime_multiplier",
                    "title": f"Reduce {strat} size in {reg} to 0.5x",
                    "rationale": (
                        f"{strat} wins only {stat['win_rate']}% in {reg} over "
                        f"{stat['samples']} samples — proposing a 0.5x size multiplier "
                        f"in that regime (bounded at {MIN_MULT}x)."
                    ),
                    "payload": {"strategy": strat, "regime": reg, "multiplier": 0.5},
                    "prev": {"multiplier": 1.0},
                    "confidence": 0.55,
                })
    return proposals
