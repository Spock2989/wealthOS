from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from database import get_db
from models import Portfolio, Holding, PortfolioSnapshot
from auth import get_current_user
from engines.analytics_core import compute_portfolio_analytics

router = APIRouter()

class CreatePortfolioRequest(BaseModel):
    name: str
    pan:  Optional[str] = None

@router.get("/portfolios")
def list_portfolios(db: Session = Depends(get_db), user=Depends(get_current_user)):
    portfolios = db.query(Portfolio).filter(
        Portfolio.user_id == user.id, Portfolio.is_active == True
    ).all()
    return [_serialize_portfolio(p) for p in portfolios]

@router.post("/portfolios")
def create_portfolio(body: CreatePortfolioRequest, db: Session = Depends(get_db), user=Depends(get_current_user)):
    p = Portfolio(user_id=user.id, name=body.name, pan=body.pan)
    db.add(p); db.commit(); db.refresh(p)
    return _serialize_portfolio(p)

@router.get("/portfolios/{portfolio_id}")
def get_portfolio(portfolio_id: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    p = _get_owned(portfolio_id, user.id, db)
    holdings = db.query(Holding).filter(Holding.portfolio_id == portfolio_id).all()
    latest_snap = db.query(PortfolioSnapshot).filter(
        PortfolioSnapshot.portfolio_id == portfolio_id
    ).order_by(PortfolioSnapshot.created_at.desc()).first()
    analytics = latest_snap.analytics if latest_snap else None
    if not analytics and holdings:
        analytics = compute_portfolio_analytics(holdings, db)
    return {**_serialize_portfolio(p), "holdings": [_serialize_holding(h) for h in holdings], "analytics": analytics}

@router.delete("/portfolios/{portfolio_id}")
def delete_portfolio(portfolio_id: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    p = _get_owned(portfolio_id, user.id, db)
    p.is_active = False; db.commit()
    return {"status": "deleted"}

@router.post("/portfolios/{portfolio_id}/analyze")
def analyze_portfolio(portfolio_id: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    p = _get_owned(portfolio_id, user.id, db)
    holdings = db.query(Holding).filter(Holding.portfolio_id == portfolio_id).all()
    if not holdings:
        raise HTTPException(status_code=400, detail="No holdings found — upload a CAS first")
    analytics = compute_portfolio_analytics(holdings, db)
    snap = PortfolioSnapshot(
        portfolio_id=portfolio_id, snapshot_date=datetime.utcnow(),
        total_value=p.total_value, analytics=analytics,
    )
    db.add(snap); db.commit()
    return {"status": "ok", "analytics": analytics}

def _get_owned(portfolio_id, user_id, db):
    p = db.query(Portfolio).filter(
        Portfolio.id == portfolio_id, Portfolio.user_id == user_id, Portfolio.is_active == True
    ).first()
    if not p:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    return p

def _serialize_portfolio(p):
    return {
        "id": p.id, "name": p.name, "pan": p.pan,
        "total_value": p.total_value, "currency": p.currency,
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }

def _serialize_holding(h):
    return {
        "id": h.id, "instrument_id": h.instrument_id,
        "name": h.instrument.name if h.instrument else "Unknown",
        "isin": h.instrument.isin if h.instrument else None,
        "sector": h.instrument.sector if h.instrument else None,
        "asset_class": h.instrument.asset_class if h.instrument else None,
        "market_cap": h.instrument.market_cap_bucket if h.instrument else None,
        "units": h.units, "nav": h.nav, "value": h.value,
        "weight": h.weight, "folio": h.folio_number,
    }