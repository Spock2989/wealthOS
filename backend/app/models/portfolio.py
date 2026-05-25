
from sqlalchemy import Column, String, Float, ForeignKey, DateTime, Text, Date
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base
import uuid

class Portfolio(Base):
    __tablename__ = "portfolios"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    advisor_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    client_id = Column(String(36), ForeignKey("clients.id", ondelete="SET NULL"), nullable=True)
    name = Column(String(256), nullable=False)
    filename = Column(String(512))
    total_value = Column(Float)
    status = Column(String(32), default="pending", index=True)
    error_message = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    advisor = relationship("User", back_populates="portfolios")
    client = relationship("Client", back_populates="portfolios")
    holdings = relationship("Holding", back_populates="portfolio", cascade="all, delete-orphan")
    snapshots = relationship("AnalyticsSnapshot", back_populates="portfolio", cascade="all, delete-orphan")
    ai_reports = relationship("AIReport", back_populates="portfolio", cascade="all, delete-orphan")
