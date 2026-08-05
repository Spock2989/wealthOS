"""
WealthOS Analytics API — single endpoint for all portfolio intelligence.

GET  /api/v1/analytics/{portfolio_id}         — return latest snapshot
POST /api/v1/analytics/{portfolio_id}/rerun   — recompute + save + return

Output: complete AnalyticsResult (Tier 1 composition + Tier 2 scenarios/macro
        + Tier 3 lookthrough) via AnalyticsEngine.run().

All computation is deterministic. No LLM calls in this path.
methodology_version: wealthos_analytics@3.0
"""

import logging
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.services.portfolio_service import PortfolioService
from app.analytics.engine import AnalyticsEngine

log = logging.getLogger(__name__)
router = APIRouter(prefix="/analytics", tags=["analytics"])
_engine = AnalyticsEngine()


@router.get("/{portfolio_id}")
def get_analytics(
    portfolio_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return the latest analytics snapshot for this portfolio."""
    svc = PortfolioService(db)
    if not svc.get(portfolio_id, current_user.id):
        raise HTTPException(404, "Portfolio not found")
    snap = svc.latest_snapshot(portfolio_id)
    if not snap:
        raise HTTPException(202, "Analytics not ready — run POST /rerun first")
    return snap.result


@router.post("/{portfolio_id}/rerun")
def rerun(
    portfolio_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Recompute the full analytics pipeline for this portfolio and save a new snapshot.
    Runs: Tier 1 composition + Tier 2 scenarios/macro sensitivity + Tier 3 lookthrough.
    """
    svc = PortfolioService(db)
    if not svc.get(portfolio_id, current_user.id):
        raise HTTPException(404, "Portfolio not found")
    canonical = svc.holdings_as_canonical(portfolio_id)
    if not canonical:
        raise HTTPException(400, "No holdings found — upload a portfolio first")

    result = _engine.run(canonical)
    snap = svc.save_snapshot(portfolio_id, result)
    log.info(
        "analytics_rerun portfolio=%s holdings=%d scenarios=%d",
        portfolio_id, result.holding_count, len(result.scenarios),
    )
    return {
        "snapshot_id":         snap.id,
        "holding_count":       result.holding_count,
        "total_value_inr":     result.total_value_inr,
        "scenarios_computed":  len(result.scenarios),
        "lookthrough_funds":   result.lookthrough.get("fund_count", 0),
        "methodology_version": result.methodology_version,
        "result":              snap.result,
    }
