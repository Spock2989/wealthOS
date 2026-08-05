"""
WealthOS — Macro API routes.

Read-only endpoints over the `macro_observations` cache. Never calls FRED
inline; callers get instant, deterministic responses from the DB.

methodology_version: macro_api@1.0.0

Endpoints:
  GET /api/v1/macro/series                 → list of supported series + metadata
  GET /api/v1/macro/snapshot               → latest value per series for the dashboard
  GET /api/v1/macro/series/{series_id}     → full history (optionally bounded)
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.services import macro_cache
from app.services.macro_registry import SERIES_REGISTRY, registered_ids

router = APIRouter(prefix="/macro", tags=["macro"])


@router.get("/series")
def list_series(current_user: User = Depends(get_current_user)):
    """List every series WealthOS tracks, with metadata. Static — no DB hit."""
    return {
        "methodology_version": "macro_api@1.0.0",
        "count": len(SERIES_REGISTRY),
        "series": [s.to_dict() for s in SERIES_REGISTRY],
    }


@router.get("/snapshot")
def macro_snapshot(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Dashboard payload: latest value + staleness flag for every tracked series."""
    snap = macro_cache.build_snapshot(db, registered_ids())
    return snap.to_dict()


@router.get("/series/{series_id}")
def series_history(
    series_id: str,
    start: Optional[date] = Query(default=None),
    end: Optional[date] = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Full or bounded history for one series. Deterministic order (asc by date)."""
    if series_id not in registered_ids():
        raise HTTPException(404, f"series not tracked: {series_id}")
    rows = macro_cache.get_history(db, series_id, start, end)
    return {
        "methodology_version": "macro_api@1.0.0",
        "series_id": series_id,
        "count": len(rows),
        "observations": [r.to_dict() for r in rows],
    }
