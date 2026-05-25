"""
WealthOS — AMFIInstrument SQLAlchemy model
Add this to models.py or import from here.
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, Date, DateTime, Index
from database import Base


class AMFIInstrument(Base):
    """
    Canonical instrument master table seeded from AMFI NAVAll.txt.
    Primary key: scheme_code (AMFI unique scheme identifier).
    """
    __tablename__ = "amfi_instruments"

    id = Column(Integer, primary_key=True, index=True)
    scheme_code = Column(Integer, unique=True, nullable=False, index=True)

    # ISINs
    isin_payout = Column(String(12), nullable=True, index=True)      # ISIN for Div Payout / IDCW
    isin_reinvest = Column(String(12), nullable=True, index=True)    # ISIN for Div Reinvestment
    canonical_isin = Column(String(12), nullable=True, index=True)   # isin_payout preferred

    # Identity
    scheme_name = Column(String(512), nullable=False)
    amc_name = Column(String(256), nullable=True)
    category = Column(String(256), nullable=True)   # e.g. "Open Ended Equity Schemes"
    fund_type = Column(String(32), nullable=True)   # equity/debt/hybrid/etf/index/fof/unknown

    # Pricing
    nav = Column(Float, nullable=True)
    nav_date = Column(Date, nullable=True)

    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Composite indexes for fast lookups
    __table_args__ = (
        Index("ix_amfi_isin_payout", "isin_payout"),
        Index("ix_amfi_isin_reinvest", "isin_reinvest"),
        Index("ix_amfi_canonical_isin", "canonical_isin"),
        Index("ix_amfi_amc_type", "amc_name", "fund_type"),
    )

    def __repr__(self):
        return f"<AMFIInstrument {self.scheme_code}: {self.scheme_name[:40]}>"
