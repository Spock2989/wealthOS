
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.services.portfolio_service import PortfolioService

router = APIRouter(prefix="/portfolios", tags=["portfolios"])

@router.get("/")
def list_portfolios(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    svc = PortfolioService(db)
    return [{"id":p.id,"name":p.name,"filename":p.filename,"status":p.status,
             "total_value":p.total_value,"holding_count":svc.holding_count(p.id),
             "created_at":p.created_at.isoformat()} for p in svc.get_all(current_user.id)]

@router.get("/{portfolio_id}")
def get_portfolio(portfolio_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    svc = PortfolioService(db)
    p = svc.get(portfolio_id, current_user.id)
    if not p: raise HTTPException(404, "Not found")
    return {"id":p.id,"name":p.name,"filename":p.filename,"status":p.status,
            "error_message":p.error_message,"total_value":p.total_value,
            "holding_count":svc.holding_count(p.id),
            "created_at":p.created_at.isoformat(),
            "updated_at":p.updated_at.isoformat() if p.updated_at else None}

@router.get("/{portfolio_id}/holdings")
def get_holdings(portfolio_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    svc = PortfolioService(db)
    if not svc.get(portfolio_id, current_user.id): raise HTTPException(404, "Not found")
    holdings = svc.get_holdings(portfolio_id)
    return {"portfolio_id":portfolio_id,"count":len(holdings),
            "holdings":[{"id":h.id,"instrument_name":h.instrument_name,"isin":h.isin,
                "asset_class":h.asset_class,"sector":h.sector,"market_cap":h.market_cap,
                "current_value":h.current_value,"allocation_percent":round(h.allocation_percent or 0,2),
                "risk_score":h.risk_score,"liquidity_score":h.liquidity_score,
                "quantity":h.quantity,"nav":h.nav} for h in holdings]}

@router.delete("/{portfolio_id}", status_code=204)
def delete_portfolio(portfolio_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    svc = PortfolioService(db)
    if not svc.delete(portfolio_id, current_user.id): raise HTTPException(404, "Not found")
