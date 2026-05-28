"""
Regression tests for the Universal Ingestion Engine v2.

These tests pin the determinism contract: same bytes → same output, every time.
Run with: cd backend && PYTHONPATH=. pytest tests/test_ingestion_v2.py -v
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from app.parsers.ingestion_v2 import ingest

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def _hash_holdings(result_dict: dict) -> str:
    """Deterministic hash of the canonical (ISIN, name, value) triplets."""
    blob = json.dumps(
        [
            {"isin": h["isin"], "name": h["instrument_name"], "val": h["current_value"]}
            for h in result_dict["holdings"]
        ],
        sort_keys=True,
    ).encode()
    return hashlib.sha256(blob).hexdigest()


# --- Zerodha Console xlsx ------------------------------------------------

def test_zerodha_console_xlsx_parses():
    content = _load("holdings-ZC0726.xlsx")
    r = ingest(content, "holdings-ZC0726.xlsx").to_dict()
    assert r["error"] is None
    assert r["format"] == "xlsx"
    assert r["broker_detected"] == "zerodha_console"
    assert r["client_id"] == "ZC0726"
    assert r["statement_date"] == "2026-05-28"
    assert r["holdings_count"] == 12
    # Total must match the workbook's own Present Value (1272437.1809) to ₹1
    assert abs(r["total_value"] - 1_272_437.18) < 1.0


def test_zerodha_console_xlsx_is_deterministic():
    """Reproducibility: 5 runs must produce byte-identical canonical hashes."""
    content = _load("holdings-ZC0726.xlsx")
    hashes = {_hash_holdings(ingest(content, "x.xlsx").to_dict()) for _ in range(5)}
    assert len(hashes) == 1, f"Non-deterministic ingestion: {hashes}"


def test_zerodha_console_isins_are_valid():
    content = _load("holdings-ZC0726.xlsx")
    r = ingest(content, "holdings-ZC0726.xlsx").to_dict()
    import re
    for h in r["holdings"]:
        assert re.match(r"^IN[A-Z0-9]{10}$", h["isin"]), f"bad ISIN: {h['isin']}"


def test_zerodha_console_dedup_prefers_segregated_over_combined():
    """
    Workbook has 12 MF rows in 'Mutual Funds' and the same 12 in 'Combined'.
    Dedup must keep the segregated rows and flag the dedup.
    """
    content = _load("holdings-ZC0726.xlsx")
    r = ingest(content, "holdings-ZC0726.xlsx").to_dict()
    assert r["holdings_count"] == 12
    for h in r["holdings"]:
        assert h["provenance"]["source_sheet"] in ("Mutual Funds", "Equity"), \
            f"Should not have survived from Combined: {h['provenance']}"
        assert any(f.startswith("DEDUPED_FROM_") for f in h["provenance"]["flags"])


def test_zerodha_console_computed_value_flag():
    """No 'current value' column in the file → value must be computed AND flagged."""
    content = _load("holdings-ZC0726.xlsx")
    r = ingest(content, "holdings-ZC0726.xlsx").to_dict()
    for h in r["holdings"]:
        assert "COMPUTED_VALUE_QTY_x_CLOSE" in h["provenance"]["flags"]


# --- Edge cases ----------------------------------------------------------

def test_empty_bytes():
    r = ingest(b"", "x.xlsx").to_dict()
    assert r["error"] == "empty_file"
    assert r["holdings_count"] == 0


def test_unsupported_format():
    r = ingest(b"random garbage that is not any known format", "x.bin").to_dict()
    assert r["error"] is not None
    assert r["holdings_count"] == 0
