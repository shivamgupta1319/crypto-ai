"""Settings API — read/update runtime-editable risk/leverage/universe knobs."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import settings_store
from app.db.session import get_db

router = APIRouter(prefix="/api/settings", tags=["settings"])


class UpdateRequest(BaseModel):
    values: dict[str, Any]


@router.get("")
def get_settings() -> dict[str, Any]:
    return settings_store.effective()


@router.put("")
def update_settings(req: UpdateRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        return settings_store.update(db, req.values)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/reset")
def reset_settings(db: Session = Depends(get_db)) -> dict[str, Any]:
    return settings_store.reset(db)
