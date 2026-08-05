"""
WealthOS — Macro observation model.

Single source of truth for macro time-series data. Every row carries
full provenance so any number on the dashboard can be traced back to
(source, series_id, observation_date, fetched_at, methodology_version).

methodology_version: macro_observation@1.0.0
"""
from __future__ import annotations

from datetime import datetime, date

from sqlalchemy import Column, String, Float, Date, DateTime, Index
from sqlalchemy.sql import func

from app.database import Base


class MacroObservation(Base):
    """
    One observation of one series on one date.
    Composite PK on (series_id, observation_date) — same series+date is
    a no-op upsert, which is what we want for idempotent daily sync.
    """
    __tablename__ = "macro_observations"

    series_id: str = Column(String(32), primary_key=True, nullable=False)
    observation_date: date = Column(Date, primary_key=True, nullable=False)
    value: float = Column(Float, nullable=True)   # FRED uses '.' for missing → stored as NULL

    source: str = Column(String(16), nullable=False, default="FRED")
    units: str = Column(String(64), nullable=True)
    frequency: str = Column(String(16), nullable=True)   # 'D' / 'W' / 'M' / 'Q' / 'A'
    title: str = Column(String(256), nullable=True)

    methodology_version: str = Column(String(32), nullable=False, default="macro_observation@1.0.0")
    fetched_at: datetime = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        Index("ix_macro_series_date", "series_id", "observation_date"),
    )

    def to_dict(self) -> dict:
        return {
            "series_id": self.series_id,
            "observation_date": self.observation_date.isoformat() if self.observation_date else None,
            "value": self.value,
            "source": self.source,
            "units": self.units,
            "frequency": self.frequency,
            "title": self.title,
            "methodology_version": self.methodology_version,
            "fetched_at": self.fetched_at.isoformat() if self.fetched_at else None,
        }
