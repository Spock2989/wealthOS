
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.services.portfolio_service import PortfolioService

router = APIRouter(prefix="/reports", tags=["reports"])

@router.get("/{portfolio_id}/summary")
def summary(portfolio_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    svc = PortfolioService(db)
    p = svc.get(portfolio_id, current_user.id)
    if not p: raise HTTPException(404, "Not found")
    snap = svc.latest_snapshot(portfolio_id)
    report = svc.latest_ai_report(portfolio_id)
    a = snap.result if snap else {}
    return {"portfolio_id":portfolio_id,"filename":p.filename,"status":p.status,
            "total_value_inr":p.total_value,"holding_count":svc.holding_count(portfolio_id),
            "diversification_score":a.get("diversification",{}).get("score"),
            "resilience_score":a.get("stress_test",{}).get("summary",{}).get("resilience_score"),
            "warnings":a.get("warnings",[]),"has_insights":bool(report),"has_analytics":bool(snap)}
