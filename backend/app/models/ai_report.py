
from sqlalchemy import Column, String, ForeignKey, DateTime, Text, Integer
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base
import uuid

class AIReport(Base):
    __tablename__ = "ai_reports"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    portfolio_id = Column(String(36), ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False, index=True)
    snapshot_id = Column(String(36), ForeignKey("analytics_snapshots.id"), nullable=True)
    report_type = Column(String(64))
    portfolio_summary = Column(Text)
    meeting_prep_notes = Column(Text)
    risk_commentary = Column(Text)
    ai_provider = Column(String(32))
    model = Column(String(64))
    prompt_tokens = Column(Integer)
    completion_tokens = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)
    portfolio = relationship("Portfolio", back_populates="ai_reports")
