from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.services.portfolio_service import PortfolioService
from app.analytics.engine import AnalyticsResult
import logging, dataclasses

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/insights", tags=["insights"])


def _safe_analytics_result(data: dict) -> AnalyticsResult:
    """
    Reconstruct AnalyticsResult from a stored JSON snapshot, safely ignoring
    any extra keys that were added after this dataclass was defined.
    This prevents TypeError on schema evolution.
    """
    known_fields = {f.name for f in dataclasses.fields(AnalyticsResult)}
    safe_data = {k: v for k, v in data.items() if k in known_fields}
    return AnalyticsResult(**safe_data)


@router.post("/{portfolio_id}/generate")
def generate(
    portfolio_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    svc = PortfolioService(db)
    if not svc.get(portfolio_id, current_user.id):
        raise HTTPException(404, "Portfolio not found")

    snap = svc.latest_snapshot(portfolio_id)
    if not snap:
        raise HTTPException(
            400,
            "No analytics snapshot found for this portfolio. "
            "Open the portfolio overview tab first — it runs analytics automatically.",
        )

    # Reconstruct the analytics result safely (tolerates schema changes)
    try:
        result = _safe_analytics_result(snap.result or {})
    except Exception as e:
        logger.exception("Failed to reconstruct AnalyticsResult from snapshot")
        raise HTTPException(500, f"Analytics snapshot corrupt: {e}")

    # Generate memo via LLM
    try:
        from app.ai.insight_engine import InsightEngine
        bundle = InsightEngine().generate(result)
    except RuntimeError as e:
        # RuntimeError = API key / model / auth issue — expose clearly
        logger.error("LLM call failed: %s", e)
        raise HTTPException(500, str(e))
    except Exception as e:
        logger.exception("InsightEngine.generate failed")
        raise HTTPException(500, f"Memo generation failed: {e}")

    # Persist to DB (best-effort — don't fail the response if this breaks)
    try:
        svc.save_ai_report(portfolio_id, snap.id, bundle)
    except Exception as e:
        logger.warning("save_ai_report failed (non-fatal): %s", e)

    return bundle


@router.get("/{portfolio_id}")
def get_insights(
    portfolio_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    svc = PortfolioService(db)
    if not svc.get(portfolio_id, current_user.id):
        raise HTTPException(404, "Portfolio not found")
    report = svc.latest_ai_report(portfolio_id)
    if not report:
        return {"message": "No insights yet. POST to /insights/{id}/generate"}
    return {
        "report_id":         report.id,
        "portfolio_summary": report.portfolio_summary,
        "meeting_prep_notes": report.meeting_prep_notes,
        "risk_commentary":   report.risk_commentary,
        "ai_provider":       report.ai_provider,
        "model":             getattr(report, "model", None),
        "generated_at":      report.created_at.isoformat(),
    }
