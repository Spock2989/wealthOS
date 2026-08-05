"""
WealthOS — FRED sync script.

Idempotent daily sync of every series in the registry. Cron-ready:
  0 6 * * *  cd /opt/wlthos/backend && /opt/wlthos/backend/venv/bin/python scripts/sync_fred.py

Behaviour:
  - Pulls full history on first run, incremental on subsequent runs
    (fetches from start = (latest cached date - 7d) → today).
  - Upserts into `macro_observations` (PK = series_id, observation_date).
  - Logs structured diff per series (inserted / updated / unchanged).
  - Never crashes the whole sync on a single-series failure — moves on
    and reports the failed series at the end.

methodology_version: fred_sync@1.0.0
"""
from __future__ import annotations

import logging
import sys
from datetime import date, timedelta
from typing import List, Tuple

from app.database import SessionLocal, create_tables
from app.services.fred_client import FredClient
from app.services import macro_cache
from app.services.macro_registry import SERIES_REGISTRY

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
)
log = logging.getLogger("fred_sync")

SYNC_VERSION = "1.0.0"
_LOOKBACK_DAYS_FROM_LATEST = 7      # re-fetch the last week each run to catch FRED revisions


def _start_date_for(db, series_id: str) -> date:
    latest = macro_cache.get_latest(db, series_id)
    if latest is None or latest.observation_date is None:
        # First run for this series — pull a wide window so the dashboard
        # has history. 5y covers any reasonable initial back-fill.
        return date.today() - timedelta(days=365 * 5)
    return latest.observation_date - timedelta(days=_LOOKBACK_DAYS_FROM_LATEST)


def main() -> int:
    log.info("fred_sync start version=%s series=%d", SYNC_VERSION, len(SERIES_REGISTRY))

    create_tables()  # safe + idempotent
    client = FredClient()
    if not client.has_key():
        log.error("FRED_API_KEY not set in environment. Aborting.")
        return 2

    db = SessionLocal()
    successes: List[str] = []
    failures: List[Tuple[str, str]] = []

    try:
        for s in SERIES_REGISTRY:
            start = _start_date_for(db, s.series_id)
            res = client.get_series(s.series_id, start=start)
            if not res.ok:
                log.error("series_failed id=%s err=%s", s.series_id, res.error)
                failures.append((s.series_id, res.error or "unknown"))
                continue

            rows = [(o.date, o.value) for o in res.observations]
            counts = macro_cache.upsert_observations(
                db,
                series_id=s.series_id,
                title=(res.meta.title if res.meta else None),
                units=(res.meta.units if res.meta else None),
                frequency=(res.meta.frequency if res.meta else None),
                rows=rows,
            )
            log.info(
                "series_ok id=%-22s fetched=%4d inserted=%4d updated=%4d",
                s.series_id, len(rows), counts["inserted"], counts["updated"],
            )
            successes.append(s.series_id)

    finally:
        db.close()

    log.info(
        "fred_sync done success=%d failure=%d",
        len(successes), len(failures),
    )
    if failures:
        for fid, err in failures:
            log.error("failed_series id=%s err=%s", fid, err)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
