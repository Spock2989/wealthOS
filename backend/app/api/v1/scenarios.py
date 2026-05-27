"""
WealthOS — Scenario Engine API Route
POST /api/v1/scenarios/{portfolio_id}/run
GET  /api/v1/scenarios/{portfolio_id}       (run all 20 scenarios)
GET  /api/v1/scenarios/available            (list scenario IDs + names)

Input contract:
  Pulls sector_exposure and market_cap_exposure from the latest analytics
  snapshot for the given portfolio, then pipes them into the deterministic
  scenario engine (engines/scenario_engine.py).

  If no snapshot exists, returns 202 with a message to run analytics first.

Output contract:
  {
    "portfolio_id": str,
    "total_value_inr": float,
    "scenarios": [...],        # ranked by |impact_pct| desc
    "macro_sensitivity": {...}, # full 11-variable matrix
    "methodology_version": "scenario_v2.1",
    "snapshot_used_at": iso8601
  }
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../../.."))

from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.services.portfolio_service import PortfolioService

# Import deterministic engines (no LLM, no randomness)
from engines.scenario_engine import (
    run_scenarios,
    run_custom_scenario,
    compute_full_macro_sensitivity_matrix,
    MACRO_SENSITIVITY,
    SCENARIOS,
)

router = APIRouter(prefix="/scenarios", tags=["scenarios"])


# ── Request schema ─────────────────────────────────────────────
class ScenarioRunRequest(BaseModel):
    scenario_ids: Optional[List[str]] = None   # None = run all 20
    custom_shocks: Optional[dict] = None        # {sector: shock_pct} for custom scenario
    custom_name: Optional[str] = "Custom Scenario"


# ── Available scenarios list ───────────────────────────────────
@router.get("/available")
def list_available_scenarios():
    """Return all scenario IDs, names, categories, and severity levels."""
    return {
        "scenarios": [
            {
                "id": s["id"],
                "name": s["name"],
                "category": s.get("category", ""),
                "severity": s.get("severity", ""),
                "horizon": s.get("horizon", ""),
                "historical_analog": s.get("historical_analog", ""),
            }
            for s in SCENARIOS
        ],
        "macro_events": list(MACRO_SENSITIVITY.keys()),
        "total_scenarios": len(SCENARIOS),
        "total_macro_events": len(MACRO_SENSITIVITY),
    }


# ── Helper: extract inputs from snapshot ──────────────────────
def _extract_scenario_inputs(snapshot_result: dict) -> tuple:
    """
    Extract (sector_exp, cap_split, total_value) from an AnalyticsSnapshot result dict.
    All values are in percentage (0-100 scale) as expected by the scenario engine.
    """
    sector_raw = snapshot_result.get("sector_exposure", {})
    cap_raw    = snapshot_result.get("market_cap_exposure", {})

    # sector_exposure.by_sector: {sector_name: pct_of_portfolio}
    sector_exp = sector_raw.get("by_sector", {})
    if not isinstance(sector_exp, dict):
        sector_exp = {}

    # market_cap_exposure.by_cap_pct_of_portfolio: {cap_bucket: pct}
    cap_split = cap_raw.get("by_cap_pct_of_portfolio", {})
    if not isinstance(cap_split, dict):
        cap_split = {}

    total_value = float(snapshot_result.get("total_value_inr", 0.0))
    return sector_exp, cap_split, total_value


def _get_snapshot_or_raise(portfolio_id: str, svc: PortfolioService):
    snap = svc.latest_snapshot(portfolio_id)
    if not snap:
        raise HTTPException(
            status_code=202,
            detail="No analytics snapshot found. Run POST /api/v1/analytics/{id}/rerun first."
        )
    return snap


# ── Run all scenarios ─────────────────────────────────────────
@router.get("/{portfolio_id}")
@router.post("/{portfolio_id}")          # frontend compat: POST without /run
def get_all_scenarios(
    portfolio_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Run all 20 institutional scenarios against this portfolio.
    Uses the latest analytics snapshot for sector/cap inputs.
    Returns scenarios ranked by absolute impact (worst-case first).
    """
    svc = PortfolioService(db)
    if not svc.get(portfolio_id, current_user.id):
        raise HTTPException(404, "Portfolio not found")

    snap = _get_snapshot_or_raise(portfolio_id, svc)
    sector_exp, cap_split, total_value = _extract_scenario_inputs(snap.result)

    if not sector_exp:
        raise HTTPException(
            422,
            "Portfolio has no sector exposure data. Ensure holdings have sector tags."
        )

    results = run_scenarios(sector_exp, cap_split, total_value)
    macro_matrix = compute_full_macro_sensitivity_matrix(sector_exp, total_value)

    # Portfolio outlook — deterministic forward projection (3-6M, 1-2Y, 3-5Y)
    outlook = {}
    try:
        from engines.outlook_engine import run_outlook
        outlook = run_outlook(sector_exp, cap_split, total_value)
    except Exception as _e:
        import logging
        logging.getLogger(__name__).warning("outlook_engine failed: %s", _e)

    return {
        "portfolio_id":        portfolio_id,
        "total_value_inr":     total_value,
        "scenarios":           results,
        "macro_sensitivity":   macro_matrix,
        "outlook":             outlook,
        "methodology_version": "scenario_v2.1",
        "snapshot_used_at":    snap.created_at.isoformat(),
        "sector_inputs":       sector_exp,
        "cap_inputs":          cap_split,
    }


# ── Run specific or custom scenario ──────────────────────────
@router.post("/{portfolio_id}/run")
def run_scenario(
    portfolio_id: str,
    body: ScenarioRunRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Run specific scenario IDs or a custom sector-shock scenario.

    - Pass `scenario_ids` to run a subset of the 20 pre-defined scenarios.
    - Pass `custom_shocks` (e.g. {"IT": -0.15, "BFSI": -0.20}) to run a
      fully custom scenario; `custom_name` sets the display label.
    - Pass neither to run all 20 scenarios (same as GET).
    """
    svc = PortfolioService(db)
    if not svc.get(portfolio_id, current_user.id):
        raise HTTPException(404, "Portfolio not found")

    snap = _get_snapshot_or_raise(portfolio_id, svc)
    sector_exp, cap_split, total_value = _extract_scenario_inputs(snap.result)

    if not sector_exp:
        raise HTTPException(422, "No sector exposure data in snapshot.")

    if body.custom_shocks:
        result = run_custom_scenario(
            sector_shocks=body.custom_shocks,
            sector_exp=sector_exp,
            cap_split=cap_split,
            total_value=total_value,
            scenario_name=body.custom_name or "Custom Scenario",
        )
        return {
            "portfolio_id":        portfolio_id,
            "total_value_inr":     total_value,
            "scenario":            result,
            "methodology_version": "scenario_v2.1",
            "snapshot_used_at":    snap.created_at.isoformat(),
        }

    # Run named scenarios
    results = run_scenarios(
        sector_exp=sector_exp,
        cap_split=cap_split,
        total_value=total_value,
        scenario_ids=body.scenario_ids,
    )
    return {
        "portfolio_id":        portfolio_id,
        "total_value_inr":     total_value,
        "scenarios":           results,
        "methodology_version": "scenario_v2.1",
        "snapshot_used_at":    snap.created_at.isoformat(),
    }
