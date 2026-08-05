"""
WealthOS — production ingestion verification (no auth required).

Runs the new Universal Ingestion v2 engine directly against the deployed test
fixture and prints a one-page receipt. Use this to prove the parser works in
production without needing to log in through the HTTP layer.

Usage on the server:
    cd /opt/wlthos/backend
    source venv/bin/activate
    PYTHONPATH=. python3 scripts/verify_prod_ingestion.py
"""
from __future__ import annotations

import sys
from pathlib import Path

FIXTURE = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "holdings-ZC0726.xlsx"


def main() -> int:
    if not FIXTURE.exists():
        print(f"FIXTURE NOT FOUND: {FIXTURE}", file=sys.stderr)
        return 2

    from app.parsers.ingestion_v2 import ingest

    content = FIXTURE.read_bytes()
    result = ingest(content, FIXTURE.name).to_dict()

    bar = "=" * 60
    print(bar)
    print("WEALTHOS INGESTION v2 — PRODUCTION VERIFICATION")
    print(bar)
    print(f"file              : {FIXTURE.name}")
    print(f"format            : {result['format']}")
    print(f"broker_detected   : {result['broker_detected']}")
    print(f"client_id         : {result['client_id']}")
    print(f"statement_date    : {result['statement_date']}")
    print(f"holdings_count    : {result['holdings_count']}")
    print(f"total_value (INR) : {result['total_value']:,.2f}")
    print(f"parsers_used      : {result['parsers_used']}")
    print(f"warnings          : {result['warnings']}")
    print(f"error             : {result['error']}")
    print()
    print("First 3 holdings:")
    for h in result["holdings"][:3]:
        name = (h["instrument_name"] or "")[:42]
        val = h["current_value"]
        print(f"  {h['isin']}  {name:<42}  INR {val:>14,.2f}")
    print()

    expected_count = 12
    expected_total = 1_272_437.18
    ok_count = result["holdings_count"] == expected_count
    ok_total = abs(result["total_value"] - expected_total) < 1.0
    ok_broker = result["broker_detected"] == "zerodha_console"
    ok_error = result["error"] is None

    print(bar)
    print("ASSERTIONS")
    print(bar)
    print(f"  holdings_count == 12          : {'PASS' if ok_count else 'FAIL'}")
    print(f"  total_value   ~= 1,272,437.18 : {'PASS' if ok_total else 'FAIL'}")
    print(f"  broker        == zerodha      : {'PASS' if ok_broker else 'FAIL'}")
    print(f"  no error                      : {'PASS' if ok_error else 'FAIL'}")

    all_ok = ok_count and ok_total and ok_broker and ok_error
    print()
    print(bar)
    print("DEPLOYMENT RECEIPT: " + ("PASS — ingestion v2 is live" if all_ok else "FAIL"))
    print(bar)
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
