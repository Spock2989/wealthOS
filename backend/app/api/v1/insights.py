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

@router.post("/{portfolio_id}/generate")
def generate(portfolio_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    svc = PortfolioService(db)
    if not svc.get(portfolio_id, current_user.id): raise HTTPException(404, "Not found")
    snap = svc.latest_snapshot(portfolio_id)
    if not snap: raise HTTPException(400, "Run analytics first")
    try:
        from app.ai.insight_engine import InsightEngine
        result = AnalyticsResult(**snap.result)
        bundle = InsightEngine().generate(result)
    except Exception as e:
        logger.exception(e)
        raise HTTPException(500, f"AI failed: {str(e)}")
    try:
        report = svc.save_ai_report(portfolio_id, snap.id, bundle)
    except Exception:
        pass
    return bundle

@router.get("/{portfolio_id}")
def get_insights(portfolio_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    svc = PortfolioService(db)
    if not svc.get(portfolio_id, current_user.id): raise HTTPException(404, "Not found")
    report = svc.latest_ai_report(portfolio_id)
    if not report: return {"message": "No insights yet. POST to /insights/{id}/generate"}
    return {"report_id":report.id,"portfolio_summary":report.portfolio_summary,
            "meeting_prep_notes":report.meeting_prep_notes,"risk_commentary":report.risk_commentary,
            "ai_provider":report.ai_provider,"generated_at":report.created_at.isoformat()}
