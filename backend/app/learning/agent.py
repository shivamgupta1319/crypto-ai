"""The adaptive agent orchestrator (N10 stage 6).

A periodic review reads the analytics from stages 1–5 and writes concrete,
bounded **proposals** to the ``agent_proposals`` table plus a plain-English
assessment (via the AI wrapper, if configured). A human approves or rejects each
proposal in the UI; approval applies it through the existing levers, and every
applied change is reversible.

Proposals are generated deterministically from realized performance — the LLM
only narrates. The agent never trades and never auto-applies.
"""
from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import ai
from app.config import settings
from app.learning import allocation, dataset, levers, metalabel
from app.models import ActiveStrategy, AgentProposal

# Pending-proposal narrative cache (avoid re-calling the LLM every poll).
_narrative_cache: dict[str, Any] = {}
_NARRATIVE_TTL = 900.0


def _utcnow() -> datetime:
    return datetime.now(UTC)


# ---- proposal generation -----------------------------------------------------
def _pending_signatures(db: Session) -> set[tuple[str, str]]:
    rows = db.execute(
        select(AgentProposal).where(AgentProposal.status == "pending")
    ).scalars().all()
    return {(r.kind, json.dumps(json.loads(r.payload_json or "{}"), sort_keys=True)) for r in rows}


def generate_proposals(db: Session) -> list[AgentProposal]:
    """Build allocation-based proposals; persist new ones (deduped vs pending)."""
    candidates = allocation.propose(db)
    existing = _pending_signatures(db)
    created: list[AgentProposal] = []
    for c in candidates:
        sig = (c["kind"], json.dumps(c["payload"], sort_keys=True))
        if sig in existing:
            continue
        row = AgentProposal(
            kind=c["kind"], title=c["title"], rationale=c["rationale"],
            payload_json=json.dumps(c["payload"]), prev_json=json.dumps(c.get("prev", {})),
            confidence=float(c.get("confidence", 0.5)), status="pending",
        )
        db.add(row)
        created.append(row)
        existing.add(sig)
    if created:
        db.commit()
        for r in created:
            db.refresh(r)
    return created


# ---- apply / revert levers ---------------------------------------------------
def _set_enabled(db: Session, strategy: str, enabled: bool) -> None:
    rows = db.execute(
        select(ActiveStrategy).where(ActiveStrategy.strategy == strategy)
    ).scalars().all()
    for r in rows:
        r.enabled = 1 if enabled else 0
    db.commit()


def _persist_setting(db: Session, key: str, value: Any) -> None:
    from app.settings_store import update

    update(db, {key: value})


def _apply(db: Session, p: AgentProposal) -> None:
    payload = json.loads(p.payload_json or "{}")
    if p.kind == "disable_strategy":
        _set_enabled(db, payload["strategy"], False)
    elif p.kind == "enable_strategy":
        _set_enabled(db, payload["strategy"], True)
    elif p.kind == "set_size_multiplier":
        levers.set_multiplier(db, payload["strategy"], payload["multiplier"])
    elif p.kind == "set_meta_threshold":
        _persist_setting(db, "meta_label_threshold", payload["threshold"])
    elif p.kind == "set_meta_enabled":
        _persist_setting(db, "meta_label_enabled", bool(payload["enabled"]))
    elif p.kind == "update_params":
        row = db.execute(
            select(ActiveStrategy).where(
                ActiveStrategy.strategy == payload["strategy"],
                ActiveStrategy.symbol == payload.get("symbol"),
                ActiveStrategy.timeframe == payload.get("timeframe"),
            )
        ).scalars().first()
        if row is not None:
            row.params_json = json.dumps(payload["params"])
            db.commit()
    else:
        raise ValueError(f"Unknown proposal kind: {p.kind}")


def _revert(db: Session, p: AgentProposal) -> None:
    prev = json.loads(p.prev_json or "{}")
    payload = json.loads(p.payload_json or "{}")
    if p.kind in ("disable_strategy", "enable_strategy"):
        _set_enabled(db, payload["strategy"], bool(prev.get("enabled", True)))
    elif p.kind == "set_size_multiplier":
        levers.set_multiplier(db, payload["strategy"], float(prev.get("multiplier", 1.0)))
    elif p.kind == "set_meta_threshold":
        _persist_setting(db, "meta_label_threshold", prev.get("threshold", settings.meta_label_threshold))
    elif p.kind == "set_meta_enabled":
        _persist_setting(db, "meta_label_enabled", bool(prev.get("enabled", False)))
    elif p.kind == "update_params" and prev.get("params") is not None:
        row = db.execute(
            select(ActiveStrategy).where(
                ActiveStrategy.strategy == payload["strategy"],
                ActiveStrategy.symbol == payload.get("symbol"),
                ActiveStrategy.timeframe == payload.get("timeframe"),
            )
        ).scalars().first()
        if row is not None:
            row.params_json = json.dumps(prev["params"])
            db.commit()


def approve(db: Session, proposal_id: int) -> AgentProposal | None:
    p = db.get(AgentProposal, proposal_id)
    if p is None or p.status != "pending":
        return None
    _apply(db, p)
    p.status = "approved"
    p.decided_at = _utcnow()
    db.commit()
    db.refresh(p)
    return p


def reject(db: Session, proposal_id: int) -> AgentProposal | None:
    p = db.get(AgentProposal, proposal_id)
    if p is None or p.status != "pending":
        return None
    p.status = "rejected"
    p.decided_at = _utcnow()
    db.commit()
    db.refresh(p)
    return p


def revert(db: Session, proposal_id: int) -> AgentProposal | None:
    p = db.get(AgentProposal, proposal_id)
    if p is None or p.status != "approved":
        return None
    _revert(db, p)
    p.status = "reverted"
    p.decided_at = _utcnow()
    db.commit()
    db.refresh(p)
    return p


# ---- serialization + narrative -----------------------------------------------
def proposal_dict(p: AgentProposal) -> dict[str, Any]:
    return {
        "id": p.id,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "kind": p.kind,
        "title": p.title,
        "rationale": p.rationale,
        "payload": json.loads(p.payload_json or "{}"),
        "confidence": p.confidence,
        "status": p.status,
        "decided_at": p.decided_at.isoformat() if p.decided_at else None,
    }


def list_proposals(db: Session, status: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    stmt = select(AgentProposal).order_by(AgentProposal.id.desc()).limit(limit)
    if status:
        stmt = stmt.where(AgentProposal.status == status)
    return [proposal_dict(p) for p in db.execute(stmt).scalars().all()]


def _narrative(db: Session, alloc: dict[str, Any], pending: list[dict[str, Any]]) -> str | None:
    if not settings.ai_enabled:
        return None
    now = time.time()
    if _narrative_cache.get("text") and (now - _narrative_cache.get("at", 0)) < _NARRATIVE_TTL:
        return _narrative_cache["text"]
    lines = ["Per-strategy paper performance:"]
    for s in alloc["strategies"][:10]:
        lines.append(
            f"- {s['strategy']}: net {s['net_pnl']}, {s['trades']} trades, "
            f"win {s['win_rate']}%, {'enabled' if s['enabled'] else 'disabled'}"
        )
    prop_lines = "\n".join(f"- {p['title']}: {p['rationale']}" for p in pending) or "None."
    prompt = (
        "You are the adaptive 'coach' for a crypto paper-trading system. Given the "
        "per-strategy performance and the system's own proposed changes below, write "
        "a short (<=140 words) assessment: what's working, what's leaking money, and "
        "whether the proposed changes look sensible. You do NOT place trades; a human "
        "approves each change. Be measured and flag overfitting risk.\n\n"
        + "\n".join(lines)
        + f"\n\nProposed changes awaiting approval:\n{prop_lines}\n"
    )
    text = ai.complete(prompt)
    if text:
        _narrative_cache.update(text=text, at=now)
    return text


def review_cycle(db: Session) -> dict[str, Any]:
    """Generate fresh proposals + a narrative. Returns a summary."""
    created = generate_proposals(db)
    alloc = allocation.analyze(db)
    pending = list_proposals(db, status="pending")
    narrative = _narrative(db, alloc, pending)
    return {
        "created": len(created),
        "pending": len(pending),
        "narrative": narrative,
    }


def overview(db: Session) -> dict[str, Any]:
    """Everything the Agent page needs in one call."""
    alloc = allocation.analyze(db)
    pending = list_proposals(db, status="pending")
    return {
        "enabled": True,
        "ai_enabled": settings.ai_enabled,
        "meta_label_enabled": settings.meta_label_enabled,
        "meta_label_threshold": settings.meta_label_threshold,
        "dataset": dataset.dataset_stats(db),
        "model": metalabel.model_status(),
        "allocation": alloc,
        "levers": levers.lever_summary(db),
        "pending_proposals": pending,
        "recent_proposals": list_proposals(db, limit=20),
        "narrative": _narrative_cache.get("text"),
    }
