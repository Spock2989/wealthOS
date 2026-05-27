"""
FundConstituent — cached portfolio holdings for each mutual fund scheme.

Populated by AMFIHoldingsService (fetches AMFI monthly portfolio disclosures).
Used by lookthrough_engine.py for recursive fund→stock decomposition.

One row per (scheme_code, underlying_isin) pair — i.e. one row per stock
that a given fund holds. Refreshed monthly when AMFI discloses portfolios.
"""

import uuid
from datetime import datetime
from sqlalchemy import Column, String, Float, DateTime, Index, UniqueConstraint
from app.database import Base


class FundConstituent(Base):
    __tablename__ = "fund_constituents"

    id             = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    # Which fund holds this stock
    scheme_code    = Column(String(32), nullable=False, index=True)
    fund_isin      = Column(String(12), index=True)       # ISIN of the parent fund
    fund_name      = Column(String(512))

    # The underlying stock/instrument this fund holds
    underlying_isin   = Column(String(12), index=True)
    underlying_name   = Column(String(512))
    underlying_sector = Column(String(128))
    underlying_cap    = Column(String(32))                # large/mid/small/other

    # Weight of this stock inside the fund (0–100 scale, % of fund NAV)
    weight_in_fund_pct = Column(Float, nullable=False)

    # When this disclosure was published by AMFI / fetched
    disclosure_date  = Column(String(10))                 # YYYY-MM-DD of the disclosure
    fetched_at       = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("scheme_code", "underlying_isin", "disclosure_date",
                         name="uq_scheme_underlying_date"),
        Index("ix_fc_scheme_date", "scheme_code", "disclosure_date"),
        Index("ix_fc_underlying_isin", "underlying_isin"),
    )
