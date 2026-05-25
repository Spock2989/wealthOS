
from sqlalchemy import Column, String, ForeignKey, DateTime, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base
import uuid

class AnalyticsSnapshot(Base):
    __tablename__ = "analytics_snapshots"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    portfolio_id = Column(String(36), ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False, index=True)
    result = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    portfolio = relationship("Portfolio", back_populates="snapshots")
