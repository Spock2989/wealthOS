
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.services.portfolio_service import PortfolioService
from app.analytics.engine import AnalyticsEngine

router = APIRouter(prefix="/analytics", tags=["analytics"])
engine = AnalyticsEngine()

@router.get("/{portfolio_id}")
def get_analytics(portfolio_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    svc = PortfolioService(db)
    if not svc.get(portfolio_id, current_user.id): raise HTTPException(404, "Not found")
    snap = svc.latest_snapshot(portfolio_id)
    if not snap: raise HTTPException(202, "Analytics not ready yet")
    return snap.result

@router.post("/{portfolio_id}/rerun")
def rerun(portfolio_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    svc = PortfolioService(db)
    if not svc.get(portfolio_id, current_user.id): raise HTTPException(404, "Not found")
    canonical = svc.holdings_as_canonical(portfolio_id)
    if not canonical: raise HTTPException(400, "No holdings found")
    result = engine.run(canonical)
    snap = svc.save_snapshot(portfolio_id, result)
    return {"snapshot_id": snap.id, "result": snap.result}
