#!/usr/bin/env python3
"""
WealthOS — AMFI Instrument Master Seeder
========================================
Fetches the live AMFI NAV data feed and seeds the canonical instruments table.

AMFI URL: https://www.amfiindia.com/spages/NAVAll.txt
Format: Scheme Code;ISIN Div Payout/IDCW;ISIN Div Reinvestment;Scheme Name;Net Asset Value;Date

Run:
    cd /opt/wlthos/backend
    source venv/bin/activate
    python3 scripts/seed_amfi.py

Idempotent: safe to re-run — uses upsert on scheme_code.
"""

import os
import sys
import logging
import requests
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import SessionLocal, engine
from models import Base, AMFIInstrument

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

AMFI_URL = "https://www.amfiindia.com/spages/NAVAll.txt"


def fetch_amfi_data() -> list[dict]:
    log.info(f"Fetching AMFI data from {AMFI_URL}")
    resp = requests.get(AMFI_URL, timeout=30)
    resp.raise_for_status()
    text = resp.content.decode("utf-8", errors="replace")
    lines = text.strip().split("\n")

    instruments = []
    current_amc = None
    current_category = None
    parsed = skipped = 0

    for line in lines:
        line = line.strip()
        if not line:
            continue

        if ";" not in line:
            upper = line.upper()
            if any(x in upper for x in ["MUTUAL FUND", "ASSET MANAGEMENT", "AMC"]):
                current_amc = line
            elif any(x in upper for x in ["OPEN ENDED", "CLOSE ENDED", "INTERVAL"]):
                current_category = line
            continue

        parts = line.split(";")
        if len(parts) < 6 or parts[0].strip() == "Scheme Code":
            skipped += 1
            continue

        try:
            scheme_code = int(parts[0].strip())
        except ValueError:
            skipped += 1
            continue

        isin_payout = parts[1].strip() or None
        if isin_payout == "-":
            isin_payout = None
        isin_reinvest = parts[2].strip() or None
        if isin_reinvest == "-":
            isin_reinvest = None

        scheme_name = parts[3].strip()
        try:
            nav = float(parts[4].strip())
        except ValueError:
            nav = None

        try:
            nav_date = datetime.strptime(parts[5].strip(), "%d-%b-%Y").date()
        except (ValueError, AttributeError):
            nav_date = None

        canonical_isin = isin_payout or isin_reinvest

        fund_type = "unknown"
        if current_category:
            c = current_category.upper()
            if "EQUITY" in c:
                fund_type = "equity"
            elif any(x in c for x in ["DEBT", "LIQUID", "GILT", "BOND", "DURATION", "OVERNIGHT", "FLOATER", "CREDIT", "MONEY MARKET"]):
                fund_type = "debt"
            elif "HYBRID" in c:
                fund_type = "hybrid"
            elif "ETF" in c:
                fund_type = "etf"
            elif "INDEX" in c:
                fund_type = "index"
            elif "FUND OF FUND" in c:
                fund_type = "fof"

        instruments.append({
            "scheme_code": scheme_code,
            "isin_payout": isin_payout,
            "isin_reinvest": isin_reinvest,
            "canonical_isin": canonical_isin,
            "scheme_name": scheme_name,
            "amc_name": current_amc,
            "category": current_category,
            "fund_type": fund_type,
            "nav": nav,
            "nav_date": nav_date,
        })
        parsed += 1

    log.info(f"Parsed {parsed} instruments, skipped {skipped} lines")
    return instruments


def upsert_instruments(db, instruments: list[dict]) -> tuple[int, int]:
    inserted = updated = 0
    for data in instruments:
        existing = db.query(AMFIInstrument).filter_by(scheme_code=data["scheme_code"]).first()
        if existing:
            for k, v in data.items():
                setattr(existing, k, v)
            existing.updated_at = datetime.utcnow()
            updated += 1
        else:
            db.add(AMFIInstrument(**data))
            inserted += 1
        if (inserted + updated) % 500 == 0:
            db.commit()
            log.info(f"  {inserted + updated} processed...")
    db.commit()
    return inserted, updated


def main():
    log.info("=" * 55)
    log.info("WealthOS AMFI Instrument Master Seeder")
    log.info("=" * 55)

    Base.metadata.create_all(bind=engine)
    instruments = fetch_amfi_data()

    if not instruments:
        log.error("No instruments fetched.")
        sys.exit(1)

    db = SessionLocal()
    try:
        inserted, updated = upsert_instruments(db, instruments)
        total = db.query(AMFIInstrument).count()
        log.info(f"Done: {inserted} inserted, {updated} updated → {total} total in DB")
    except Exception as e:
        db.rollback()
        log.error(f"Error: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
