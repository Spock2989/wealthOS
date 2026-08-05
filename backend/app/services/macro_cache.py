"""
WealthOS — Macro cache (DB-backed).

Read path for the dashboard + scenario engine. Always reads from the
`macro_observations` table. Writes happen only via `scripts/sync_fred.py`.

Determinism contract:
  - Same DB state → same returned values.
  - No fetch-on-demand: if a series is missing, return empty + a flag.
  - Stale detection: if newest observation is older than `stale_after_days`
    for the series's frequency, callers receive `is_stale=True`.

methodology_version: macro_cache@1.0.0
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models.macro_observation import MacroObservation

CACHE_VERSION = "1.0.0"

# How long without an update before we flag a series as stale, per frequency.
# Daily series tolerate 7d (covers weekends + bank holidays + FRED lag).
# Monthly series tolerate 45d. Annual tolerate 400d.
STALE_AFTER_DAYS: Dict[str, int] = {
    "D": 7, "W": 14, "M": 45, "Q": 120, "A": 400, "SA": 400, "BW": 21,
}
_DEFAULT_STALE_DAYS = 45


@dataclass
class SeriesSnapshot:
    series_id: str
    title: Optional[str]
    units: Optional[str]
    frequency: Optional[str]
    latest_value: Optional[float]
    latest_date: Optional[str]
    fetched_at: Optional[str]
    is_stale: bool
    methodology_version: str = CACHE_VERSION


@dataclass
class MacroSnapshot:
    series: List[SeriesSnapshot] = field(default_factory=list)
    methodology_version: str = CACHE_VERSION
    computed_at: str = ""

    def to_dict(self) -> Dict:
        return {
            "methodology_version": self.methodology_version,
            "computed_at": self.computed_at,
            "series": [s.__dict__ for s in self.series],
        }


def get_history(
    db: Session,
    series_id: str,
    start: Optional[date] = None,
    end: Optional[date] = None,
) -> List[MacroObservation]:
    """Read observations for a series, optionally bounded. Deterministic order."""
    q = db.query(MacroObservation).filter(MacroObservation.series_id == series_id)
    if start:
        q = q.filter(MacroObservation.observation_date >= start)
    if end:
        q = q.filter(MacroObservation.observation_date <= end)
    return q.order_by(MacroObservation.observation_date.asc()).all()


def get_latest(db: Session, series_id: str) -> Optional[MacroObservation]:
    return (
        db.query(MacroObservation)
        .filter(MacroObservation.series_id == series_id)
        .order_by(MacroObservation.observation_date.desc())
        .first()
    )


def _is_stale(latest_date: Optional[date], frequency: Optional[str]) -> bool:
    if latest_date is None:
        return True
    horizon = STALE_AFTER_DAYS.get((frequency or "").upper(), _DEFAULT_STALE_DAYS)
    return (date.today() - latest_date) > timedelta(days=horizon)


def build_snapshot(db: Session, series_ids: List[str]) -> MacroSnapshot:
    """Build the macro dashboard snapshot — latest value per series + staleness."""
    out: List[SeriesSnapshot] = []
    for sid in series_ids:
        latest = get_latest(db, sid)
        if latest is None:
            out.append(SeriesSnapshot(
                series_id=sid, title=None, units=None, frequency=None,
                latest_value=None, latest_date=None, fetched_at=None, is_stale=True,
            ))
            continue
        out.append(SeriesSnapshot(
            series_id=sid,
            title=latest.title,
            units=latest.units,
            frequency=latest.frequency,
            latest_value=latest.value,
            latest_date=latest.observation_date.isoformat(),
            fetched_at=latest.fetched_at.isoformat() if latest.fetched_at else None,
            is_stale=_is_stale(latest.observation_date, latest.frequency),
        ))
    return MacroSnapshot(
        series=out,
        computed_at=datetime.now(timezone.utc).isoformat(),
    )


def upsert_observations(
    db: Session,
    series_id: str,
    title: Optional[str],
    units: Optional[str],
    frequency: Optional[str],
    rows: List[Tuple[date, Optional[float]]],
) -> Dict[str, int]:
    """
    Idempotent upsert. Returns counts so the sync script can log a diff.
    Same input bytes → same DB state (PK is (series_id, observation_date)).
    """
    inserted = 0
    updated = 0
    now = datetime.now(timezone.utc)
    for obs_date, value in rows:
        existing = (
            db.query(MacroObservation)
            .filter(
                MacroObservation.series_id == series_id,
                MacroObservation.observation_date == obs_date,
            )
            .first()
        )
        if existing is None:
            db.add(MacroObservation(
                series_id=series_id,
                observation_date=obs_date,
                value=value,
                source="FRED",
                units=units,
                frequency=frequency,
                title=title,
                fetched_at=now,
            ))
            inserted += 1
        else:
            # Only update if the value actually changed — preserves fetched_at
            # for unchanged observations, which keeps the audit trail meaningful.
            if existing.value != value or existing.title != title:
                existing.value = value
                existing.title = title
                existing.units = units
                existing.frequency = frequency
                existing.fetched_at = now
                updated += 1
    db.commit()
    return {"inserted": inserted, "updated": updated}
