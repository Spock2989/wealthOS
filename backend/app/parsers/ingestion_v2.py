"""
WealthOS ingestion — Universal Ingestion Orchestrator (v2).

Single entry point for ALL file uploads. Detects format from magic bytes,
dispatches to the right adapter, returns a uniform `IngestionResult`.

Supported today:
  - xlsx (broker holdings exports: Zerodha Console, Groww, ICICI Direct,
    HDFC Securities, Kuvera, Coin, AngelOne, Upstox CSV)
  - csv  (same fuzzy schema inference as xlsx)
  - pdf  (CAS CAMS/KFin via regex + pdfplumber table fallback)
  - docx (table extraction via python-docx)

methodology_version: ingestion_v2@1.0.0

Output contract (strict, JSON-serialisable):
{
  "ingestion_version":  "1.0.0",
  "format":             "xlsx" | "pdf" | ...,
  "broker_detected":    "zerodha_console" | None,
  "client_id":          "ZC0726" | None,
  "statement_date":     "2026-05-28" | None,
  "holdings_count":     N,
  "total_value":        float,
  "holdings":           [ ParsedHolding.to_dict(), ... ],
  "sheets_or_pages":    [ {...}, ... ],
  "warnings":           [ str, ... ],
  "parsers_used":       [ "excel_v2@2.0.0", ... ],
}
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, asdict, field
from typing import Any, Dict, List, Optional

from app.parsers.format_detector import detect
from app.parsers.excel_parser_v2 import parse as parse_excel, parse_csv as parse_csv_v2

logger = logging.getLogger(__name__)

INGESTION_VERSION = "1.0.0"


@dataclass
class IngestionResult:
    ingestion_version: str = INGESTION_VERSION
    format: str = "unknown"
    broker_detected: Optional[str] = None
    client_id: Optional[str] = None
    statement_date: Optional[str] = None
    holdings_count: int = 0
    total_value: float = 0.0
    holdings: List[Dict[str, Any]] = field(default_factory=list)
    sheets_or_pages: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    parsers_used: List[str] = field(default_factory=list)
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def ingest(content: bytes, filename: str) -> IngestionResult:
    """
    Orchestrate format detection + parser dispatch. Always returns an
    IngestionResult — never raises — so the upload pipeline can surface
    a structured error to the user instead of a 500.
    """
    res = IngestionResult()

    if not content:
        res.error = "empty_file"
        return res

    det = detect(content, filename)
    res.format = det.format

    if det.format == "xlsx" or det.format == "xls":
        holdings, report = parse_excel(content)
        res.parsers_used.append(f"excel_v2@{report.parser_version}")
        res.broker_detected = report.broker_detected
        res.client_id = report.client_id
        res.statement_date = report.statement_date
        res.holdings_count = report.holdings_final
        res.total_value = report.total_value
        res.holdings = [h.to_dict() for h in holdings]
        res.sheets_or_pages = report.sheets
        res.warnings = list(report.warnings)
        if res.holdings_count == 0:
            res.warnings.append("no_holdings_detected_in_any_sheet")
        return res

    if det.format == "csv":
        holdings, report = parse_csv_v2(content)
        res.parsers_used.append(f"excel_v2@{report.parser_version}(csv)")
        res.holdings_count = report.holdings_final
        res.total_value = report.total_value
        res.holdings = [h.to_dict() for h in holdings]
        res.sheets_or_pages = report.sheets
        res.warnings = list(report.warnings)
        return res

    if det.format == "pdf":
        # Lazy import — pdf parser pulls heavy deps.
        try:
            from app.parsers.cas_parser import CASParser
            raw = CASParser().parse(content) or []
            res.parsers_used.append("cas_parser@1.0.0")
            # Best-effort pdfplumber table fallback when regex finds nothing.
            if not raw:
                raw = _pdf_table_fallback(content)
                if raw:
                    res.parsers_used.append("pdfplumber_table_fallback@1.0.0")
                    res.warnings.append("cas_regex_miss_used_table_fallback")
            res.holdings_count = len(raw)
            res.holdings = raw
            res.total_value = round(sum(float(r.get("current_value") or 0) for r in raw), 4)
            if not raw:
                res.warnings.append("no_holdings_detected_in_pdf")
        except Exception as e:
            logger.exception("pdf_ingestion_failed")
            res.error = f"pdf_ingestion_failed:{e}"
        return res

    if det.format == "docx":
        try:
            raw = _docx_table_extract(content)
            res.parsers_used.append("docx_table_extract@1.0.0")
            res.holdings = raw
            res.holdings_count = len(raw)
            res.total_value = round(sum(float(r.get("current_value") or 0) for r in raw), 4)
            if not raw:
                res.warnings.append("no_table_rows_detected_in_docx")
        except Exception as e:
            logger.exception("docx_ingestion_failed")
            res.error = f"docx_ingestion_failed:{e}"
        return res

    res.error = f"unsupported_format:{det.format} reason={det.reason}"
    return res


# --- helpers --------------------------------------------------------------

def _pdf_table_fallback(content: bytes) -> List[Dict[str, Any]]:
    """
    Generic table extraction for PDFs whose layout the regex doesn't catch
    (broker statements that aren't CAMS/KFin CAS). Re-uses the Excel-side
    header inference to map columns.
    """
    try:
        import pdfplumber, io
        from app.parsers.excel_parser_v2 import _parse_sheet
    except Exception as e:
        logger.warning("pdfplumber unavailable: %s", e)
        return []

    out: List[Dict[str, Any]] = []
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        for page_idx, page in enumerate(pdf.pages, start=1):
            try:
                tables = page.extract_tables() or []
            except Exception:
                continue
            for tbl in tables:
                rows = [tuple(c if c is not None else "" for c in row) for row in tbl]
                holdings, _status = _parse_sheet(f"pdf_page_{page_idx}", rows)
                for h in holdings:
                    out.append(h.to_dict())
    return out


def _docx_table_extract(content: bytes) -> List[Dict[str, Any]]:
    """Extract any tables in a DOCX and reuse Excel header inference."""
    try:
        from docx import Document
        from app.parsers.excel_parser_v2 import _parse_sheet
    except Exception as e:
        logger.warning("python-docx unavailable: %s", e)
        return []

    import io
    doc = Document(io.BytesIO(content))
    out: List[Dict[str, Any]] = []
    for t_idx, tbl in enumerate(doc.tables, start=1):
        rows = [tuple(cell.text for cell in row.cells) for row in tbl.rows]
        holdings, _status = _parse_sheet(f"docx_table_{t_idx}", rows)
        for h in holdings:
            out.append(h.to_dict())
    return out
