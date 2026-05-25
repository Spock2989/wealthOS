
from sqlalchemy import Column, String, Float, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base
import uuid

class Holding(Base):
    __tablename__ = "holdings"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    portfolio_id = Column(String(36), ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False, index=True)
    instrument_name = Column(String(512), nullable=False)
    isin = Column(String(12), index=True)
    folio_number = Column(String(64))
    asset_class = Column(String(32), nullable=False, index=True)
    sub_asset_class = Column(String(128))
    sector = Column(String(128))
    market_cap = Column(String(32))
    geography = Column(String(64), default="India")
    style = Column(String(32))
    quantity = Column(Float)
    nav = Column(Float)
    current_value = Column(Float, nullable=False)
    allocation_percent = Column(Float)
    risk_score = Column(Float)
    liquidity_score = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)
    portfolio = relationship("Portfolio", back_populates="holdings")
