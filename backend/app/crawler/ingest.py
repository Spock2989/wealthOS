"""
WealthOS — AMFI constituent ingestion orchestration.

Writes real disclosures into fund_constituents tagged source='amfi_disclosure'.
Nothing is written unless every gate in core.run_gates passes.

Supersession: real data supersedes modelled data for a scheme. The reverse is
forbidden — a synthetic row must never displace a real one.

Idempotency: re-running the same file for the same scheme and disclosure date
replaces that scheme's rows for that date rather than accumulating duplicates.

methodology_version: amfi_ingest@1.0.0
"""

from __future__ import annotations

import os
import uuid
import hashlib
import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime

from app.crawler.core import (
    SOURCE_AMFI_DISCLOSURE, ParsedSheet, SchemeResolver, run_gates,
)
from app.crawler.adapters import ADAPTERS

logger = logging.getLogger(__name__)

SYNTHETIC = "synthetic_estimated"


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def ensure_schema(conn: sqlite3.Connection) -> None:
    """Additive, idempotent migration — same pattern as _ensure_source_column."""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(fund_constituents)").fetchall()}
    for name, ddl in (
        ("source",         "ALTER TABLE fund_constituents ADD COLUMN source TEXT"),
        ("amc_code",       "ALTER TABLE fund_constituents ADD COLUMN amc_code TEXT"),
        ("source_file",    "ALTER TABLE fund_constituents ADD COLUMN source_file TEXT"),
        ("source_sha256",  "ALTER TABLE fund_constituents ADD COLUMN source_sha256 TEXT"),
        ("source_sheet",   "ALTER TABLE fund_constituents ADD COLUMN source_sheet TEXT"),
        ("ingest_run_id",  "ALTER TABLE fund_constituents ADD COLUMN ingest_run_id TEXT"),
        ("superseded_at",  "ALTER TABLE fund_constituents ADD COLUMN superseded_at TEXT"),
    ):
        if name not in cols:
            conn.execute(ddl)
    conn.execute("""CREATE TABLE IF NOT EXISTS ingest_runs (
        id TEXT PRIMARY KEY, started_at TEXT, finished_at TEXT, amc_code TEXT,
        files_seen INTEGER, sheets_parsed INTEGER, sheets_accepted INTEGER,
        sheets_rejected INTEGER, rows_written INTEGER, status TEXT)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS ingest_rejections (
        id TEXT PRIMARY KEY, run_id TEXT, amc_code TEXT, scheme_name TEXT,
        gate TEXT, detail TEXT, source_file TEXT, source_sheet TEXT,
        source_sha256 TEXT, created_at TEXT)""")
    conn.execute("CREATE INDEX IF NOT EXISTS ix_fc_superseded ON fund_constituents(superseded_at)")
    conn.commit()


@dataclass
class RunStats:
    run_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    files_seen: int = 0
    sheets_parsed: int = 0
    accepted: int = 0
    rejected: int = 0
    rows_written: int = 0
    schemes: list[str] = field(default_factory=list)
    rejections: list[tuple] = field(default_factory=list)


def _write_sheet(conn, sheet: ParsedSheet, sha: str, run_id: str) -> int:
    """
    Write one scheme's constituents atomically against every plan-variant ISIN.

    A scheme's Direct/Regular and Growth/IDCW plans share one portfolio, so the
    same rows are linked to each ISIN. Existing rows for this scheme+date are
    cleared first, which makes re-runs idempotent.
    """
    now = datetime.utcnow().isoformat()
    disc = sheet.disclosure_date.isoformat()
    written = 0
    for fund_isin, scheme_code in sheet.scheme_isins:
        # Clear any prior real rows for this scheme+date so re-runs are
        # idempotent rather than accumulating duplicates.
        conn.execute(
            "DELETE FROM fund_constituents WHERE scheme_code=? AND disclosure_date=? AND source=?",
            (scheme_code, disc, SOURCE_AMFI_DISCLOSURE))
        # Real data supersedes modelled data for this fund. Never the reverse.
        conn.execute(
            "UPDATE fund_constituents SET superseded_at=? "
            "WHERE scheme_code=? AND source=? AND superseded_at IS NULL",
            (now, scheme_code, SYNTHETIC))
        for r in sheet.rows:
            conn.execute("""
                INSERT OR REPLACE INTO fund_constituents
                (id, scheme_code, fund_isin, fund_name, underlying_isin, underlying_name,
                 underlying_sector, underlying_cap, weight_in_fund_pct, disclosure_date,
                 fetched_at, source, amc_code, source_file, source_sha256, source_sheet,
                 ingest_run_id, superseded_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,NULL)
            """, (
                str(uuid.uuid4()), scheme_code, fund_isin, sheet.scheme_name,
                r.isin, r.name, r.industry, None, round(r.pct, 6), disc, now,
                SOURCE_AMFI_DISCLOSURE, sheet.amc_code, os.path.basename(sheet.source_file),
                sha, sheet.source_sheet, run_id,
            ))
            written += 1
    return written


def ingest_paths(paths: list[str], amc_code: str, db_path: str,
                 dry_run: bool = False) -> RunStats:
    """Parse, gate, and (unless dry_run) write. One AMC per call."""
    adapter = ADAPTERS[amc_code]
    resolver = SchemeResolver(db_path)
    st = RunStats()
    conn = sqlite3.connect(db_path)
    try:
        ensure_schema(conn)
        conn.execute("BEGIN IMMEDIATE")
        for p in paths:
            st.files_seen += 1
            try:
                sheets = adapter.parse_file(p)
            except Exception as e:
                st.rejected += 1
                st.rejections.append((os.path.basename(p), "", "PARSE_ERROR", str(e)[:120]))
                continue
            sha = _sha256(p)
            for sh in sheets:
                st.sheets_parsed += 1
                reason = run_gates(sh, resolver)
                if reason:
                    st.rejected += 1
                    gate = reason.split(":")[0]
                    st.rejections.append((os.path.basename(p), sh.scheme_name[:52], gate, reason))
                    if not dry_run:
                        conn.execute(
                            "INSERT INTO ingest_rejections VALUES (?,?,?,?,?,?,?,?,?,?)",
                            (str(uuid.uuid4()), st.run_id, amc_code, sh.scheme_name,
                             gate, reason, os.path.basename(p), sh.source_sheet, sha,
                             datetime.utcnow().isoformat()))
                    continue
                st.accepted += 1
                st.schemes.append(sh.scheme_name)
                if not dry_run:
                    st.rows_written += _write_sheet(conn, sh, sha, st.run_id)
        if dry_run:
            conn.execute("ROLLBACK")
        else:
            conn.execute(
                "INSERT INTO ingest_runs VALUES (?,?,?,?,?,?,?,?,?,?)",
                (st.run_id, datetime.utcnow().isoformat(), datetime.utcnow().isoformat(),
                 amc_code, st.files_seen, st.sheets_parsed, st.accepted, st.rejected,
                 st.rows_written, "ok"))
            conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()
    return st
