from sqlalchemy import Column, String, Float, Integer, DateTime, Text, ForeignKey, Boolean, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base
import uuid

def gen_uuid():
    return str(uuid.uuid4())

class User(Base):
    __tablename__ = "users"
    id            = Column(String, primary_key=True, default=gen_uuid)
    email         = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    name          = Column(String, nullable=False)
    firm          = Column(String, nullable=True)
    role          = Column(String, nullable=True)
    is_active     = Column(Boolean, default=True)
    is_admin      = Column(Boolean, default=False)
    created_at    = Column(DateTime(timezone=True), server_default=func.now())
    updated_at    = Column(DateTime(timezone=True), onupdate=func.now())
    portfolios    = relationship("Portfolio", back_populates="owner", cascade="all, delete")

class DemoRequest(Base):
    __tablename__ = "demo_requests"
    id             = Column(String, primary_key=True, default=gen_uuid)
    ref_id         = Column(String, unique=True, nullable=False)
    name           = Column(String, nullable=False)
    firm           = Column(String, nullable=False)
    email          = Column(String, nullable=False, index=True)
    phone          = Column(String, nullable=False)
    role           = Column(String, nullable=True)
    aum            = Column(String, nullable=True)
    clients        = Column(String, nullable=True)
    preferred_slot = Column(String, nullable=True)
    message        = Column(Text, nullable=True)
    source         = Column(String, nullable=True)
    status         = Column(String, default="new")
    notes          = Column(Text, nullable=True)
    created_at     = Column(DateTime(timezone=True), server_default=func.now())

class Portfolio(Base):
    __tablename__ = "portfolios"
    id          = Column(String, primary_key=True, default=gen_uuid)
    user_id     = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    name        = Column(String, nullable=False)
    pan         = Column(String, nullable=True)
    total_value = Column(Float, default=0.0)
    currency    = Column(String, default="INR")
    is_active   = Column(Boolean, default=True)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())
    updated_at  = Column(DateTime(timezone=True), onupdate=func.now())
    owner       = relationship("User", back_populates="portfolios")
    holdings    = relationship("Holding", back_populates="portfolio", cascade="all, delete")
    snapshots   = relationship("PortfolioSnapshot", back_populates="portfolio", cascade="all, delete")

class Instrument(Base):
    __tablename__ = "instruments"
    id                = Column(String, primary_key=True, default=gen_uuid)
    isin              = Column(String, unique=True, nullable=True, index=True)
    amfi_code         = Column(String, nullable=True, index=True)
    ticker            = Column(String, nullable=True)
    name              = Column(String, nullable=False)
    canonical_name    = Column(String, nullable=True)
    asset_class       = Column(String, nullable=True)
    sub_asset_class   = Column(String, nullable=True)
    sector            = Column(String, nullable=True)
    industry          = Column(String, nullable=True)
    market_cap_bucket = Column(String, nullable=True)
    style_factor      = Column(JSON, nullable=True)
    themes            = Column(JSON, nullable=True)
    geography         = Column(String, default="India")
    liquidity_score   = Column(Float, nullable=True)
    risk_score        = Column(Float, nullable=True)
    factor_exposure   = Column(JSON, nullable=True)
    macro_sensitivity = Column(JSON, nullable=True)
    fund_constituents = Column(JSON, nullable=True)
    last_nav          = Column(Float, nullable=True)
    nav_date          = Column(DateTime, nullable=True)
    updated_at        = Column(DateTime(timezone=True), onupdate=func.now())
    holdings          = relationship("Holding", back_populates="instrument")

class Holding(Base):
    __tablename__ = "holdings"
    id            = Column(String, primary_key=True, default=gen_uuid)
    portfolio_id  = Column(String, ForeignKey("portfolios.id"), nullable=False, index=True)
    instrument_id = Column(String, ForeignKey("instruments.id"), nullable=False)
    folio_number  = Column(String, nullable=True)
    units         = Column(Float, nullable=True)
    nav           = Column(Float, nullable=True)
    value         = Column(Float, nullable=False)
    weight        = Column(Float, nullable=True)
    holding_date  = Column(DateTime, nullable=True)
    source        = Column(String, nullable=True)
    portfolio     = relationship("Portfolio", back_populates="holdings")
    instrument    = relationship("Instrument", back_populates="holdings")

class PortfolioSnapshot(Base):
    __tablename__ = "portfolio_snapshots"
    id            = Column(String, primary_key=True, default=gen_uuid)
    portfolio_id  = Column(String, ForeignKey("portfolios.id"), nullable=False, index=True)
    snapshot_date = Column(DateTime, nullable=False)
    total_value   = Column(Float, nullable=False)
    analytics     = Column(JSON, nullable=True)
    created_at    = Column(DateTime(timezone=True), server_default=func.now())
    portfolio     = relationship("Portfolio", back_populates="snapshots")

class IngestionJob(Base):
    __tablename__ = "ingestion_jobs"
    id             = Column(String, primary_key=True, default=gen_uuid)
    portfolio_id   = Column(String, ForeignKey("portfolios.id"), nullable=False, index=True)
    user_id        = Column(String, ForeignKey("users.id"), nullable=False)
    filename       = Column(String, nullable=False)
    file_type      = Column(String, nullable=True)
    status         = Column(String, default="pending")
    holdings_found = Column(Integer, default=0)
    errors         = Column(JSON, nullable=True)
    created_at     = Column(DateTime(timezone=True), server_default=func.now())
    completed_at   = Column(DateTime, nullable=True)
    