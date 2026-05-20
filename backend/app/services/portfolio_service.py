
from sqlalchemy.orm import Session
from typing import List, Optional
from app.models.portfolio import Portfolio
from app.models.holding import Holding
from app.models.analytics_snapshot import AnalyticsSnapshot
from app.models.ai_report import AIReport
from app.normalizer.canonical_schema import CanonicalHolding
from app.analytics.engine import AnalyticsResult
import uuid
from datetime import datetime

class PortfolioService:
    def __init__(self, db: Session):
        self.db = db

    def create(self, advisor_id, name, filename, client_id=None):
        p = Portfolio(id=str(uuid.uuid4()), advisor_id=advisor_id, name=name, filename=filename, client_id=client_id, status="pending")
        self.db.add(p); self.db.commit(); self.db.refresh(p)
        return p

    def get(self, portfolio_id, advisor_id):
        return self.db.query(Portfolio).filter(Portfolio.id==portfolio_id, Portfolio.advisor_id==advisor_id).first()

    def get_all(self, advisor_id):
        return self.db.query(Portfolio).filter(Portfolio.advisor_id==advisor_id).order_by(Portfolio.created_at.desc()).all()

    def set_status(self, portfolio_id, status, error=None):
        p = self.db.query(Portfolio).filter(Portfolio.id==portfolio_id).first()
        if p:
            p.status = status
            if error: p.error_message = error
            p.updated_at = datetime.utcnow()
            self.db.commit()

    def delete(self, portfolio_id, advisor_id):
        p = self.get(portfolio_id, advisor_id)
        if not p: return False
        self.db.delete(p); self.db.commit()
        return True

    def holding_count(self, portfolio_id):
        return self.db.query(Holding).filter(Holding.portfolio_id==portfolio_id).count()

    def save_holdings(self, portfolio_id, canonical: List[CanonicalHolding], total_value):
        self.db.query(Holding).filter(Holding.portfolio_id==portfolio_id).delete()
        for h in canonical:
            alloc = (h.current_value / total_value * 100) if total_value > 0 else 0
            self.db.add(Holding(
                portfolio_id=portfolio_id, instrument_name=h.instrument_name,
                isin=h.isin, folio_number=h.folio_number, asset_class=h.asset_class,
                sub_asset_class=h.sub_asset_class, sector=h.sector, market_cap=h.market_cap,
                geography=h.geography, quantity=h.quantity, nav=h.nav,
                current_value=h.current_value, allocation_percent=alloc,
                risk_score=h.risk_score, liquidity_score=h.liquidity_score,
            ))
        p = self.db.query(Portfolio).filter(Portfolio.id==portfolio_id).first()
        if p: p.total_value = total_value; p.updated_at = datetime.utcnow()
        self.db.commit()

    def get_holdings(self, portfolio_id):
        return self.db.query(Holding).filter(Holding.portfolio_id==portfolio_id).order_by(Holding.current_value.desc()).all()

    def holdings_as_canonical(self, portfolio_id):
        return [CanonicalHolding(instrument_name=h.instrument_name, isin=h.isin,
            folio_number=h.folio_number, asset_class=h.asset_class,
            sub_asset_class=h.sub_asset_class, sector=h.sector, market_cap=h.market_cap,
            geography=h.geography or "India", quantity=h.quantity, nav=h.nav,
            current_value=h.current_value, allocation_percent=h.allocation_percent,
            risk_score=h.risk_score, liquidity_score=h.liquidity_score)
            for h in self.get_holdings(portfolio_id)]

    def save_snapshot(self, portfolio_id, result: AnalyticsResult):
        snap = AnalyticsSnapshot(portfolio_id=portfolio_id, result=result.to_dict())
        self.db.add(snap); self.db.commit(); self.db.refresh(snap)
        return snap

    def latest_snapshot(self, portfolio_id):
        return self.db.query(AnalyticsSnapshot).filter(AnalyticsSnapshot.portfolio_id==portfolio_id).order_by(AnalyticsSnapshot.created_at.desc()).first()

    def save_ai_report(self, portfolio_id, snapshot_id, bundle):
        report = AIReport(portfolio_id=portfolio_id, snapshot_id=snapshot_id,
            report_type="portfolio_review", portfolio_summary=bundle.portfolio_summary,
            meeting_prep_notes=bundle.meeting_prep_notes, risk_commentary=bundle.risk_commentary,
            ai_provider=bundle.ai_provider, model=bundle.model)
        self.db.add(report); self.db.commit(); self.db.refresh(report)
        return report

    def latest_ai_report(self, portfolio_id):
        return self.db.query(AIReport).filter(AIReport.portfolio_id==portfolio_id).order_by(AIReport.created_at.desc()).first()
