
from sqlalchemy import Column, String, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base
import uuid

class Client(Base):
    __tablename__ = "clients"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    advisor_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(256), nullable=False)
    email = Column(String(256))
    phone = Column(String(32))
    created_at = Column(DateTime, default=datetime.utcnow)
    advisor = relationship("User", back_populates="clients")
    portfolios = relationship("Portfolio", back_populates="client")
