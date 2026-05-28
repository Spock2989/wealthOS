"""
WealthOS ingestion — format detector.

Identifies the true file format from magic bytes + extension, so the
orchestrator can dispatch to the correct parser even when the extension is
wrong (e.g. broker exports occasionally mislabel xlsx as xls or csv).

methodology_version: format_detector@1.0.0
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Format = Literal["xlsx", "xls", "csv", "pdf", "docx", "unknown"]


@dataclass(frozen=True)
class DetectedFormat:
    format: Format
    confidence: float           # 1.0 = magic-bytes match; 0.6 = extension only
    reason: str
    detector_version: str = "1.0.0"


_MAGIC = {
    # xlsx/docx/pptx are all zip; we disambiguate by sniffing the first directory entry
    b"PK\x03\x04": "zip",
    b"\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1": "ole",       # legacy xls
    b"%PDF-": "pdf",
}


def detect(content: bytes, filename: str) -> DetectedFormat:
    """Return the detected format. Magic bytes take precedence over extension."""
    name = (filename or "").lower()
    head = content[:8] if content else b""

    if head.startswith(b"%PDF-"):
        return DetectedFormat("pdf", 1.0, "magic:%PDF-")

    if head.startswith(b"\xD0\xCF\x11\xE0"):
        return DetectedFormat("xls", 1.0, "magic:OLE2")

    if head.startswith(b"PK\x03\x04"):
        # zip-based: xlsx vs docx vs pptx — look for signature inside the zip
        try:
            import zipfile, io
            with zipfile.ZipFile(io.BytesIO(content)) as z:
                names = z.namelist()
                if any(n.startswith("xl/") for n in names):
                    return DetectedFormat("xlsx", 1.0, "magic:zip+xl/")
                if any(n.startswith("word/") for n in names):
                    return DetectedFormat("docx", 1.0, "magic:zip+word/")
        except Exception as e:
            return DetectedFormat("unknown", 0.0, f"zip_read_error:{e}")
        return DetectedFormat("unknown", 0.3, "zip_unrecognized_payload")

    # Extension fallback
    if name.endswith(".csv") or (content and b"," in head and b"PK" not in head and b"%PDF" not in head):
        # crude CSV sniff — fine because the parser will validate
        if name.endswith(".csv"):
            return DetectedFormat("csv", 0.8, "extension:.csv")
        return DetectedFormat("csv", 0.5, "heuristic:comma_present")

    if name.endswith((".xlsx",)):
        return DetectedFormat("xlsx", 0.6, "extension:.xlsx_no_magic")
    if name.endswith(".xls"):
        return DetectedFormat("xls", 0.6, "extension:.xls_no_magic")
    if name.endswith(".pdf"):
        return DetectedFormat("pdf", 0.6, "extension:.pdf_no_magic")
    if name.endswith(".docx"):
        return DetectedFormat("docx", 0.6, "extension:.docx_no_magic")

    return DetectedFormat("unknown", 0.0, "no_match")
