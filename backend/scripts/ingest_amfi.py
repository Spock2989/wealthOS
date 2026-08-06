#!/usr/bin/env python3
"""
Ingest AMFI monthly portfolio disclosures into fund_constituents.

  python3 scripts/ingest_amfi.py --amc icici --dir /path/to/files [--dry-run]

Dry-run parses and validates but writes nothing — the primary tool for adapter
development. Nothing reaches the database unless every gate passes.
"""
import argparse, os, sys, glob
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.crawler.ingest import ingest_paths
from app.crawler.adapters import ADAPTERS

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--amc", required=True, choices=sorted(ADAPTERS))
    ap.add_argument("--dir", required=True)
    ap.add_argument("--glob", default="*")
    ap.add_argument("--db", default=os.environ.get("DATABASE_URL", "wealthos.db").replace("sqlite:///", "").replace("./", ""))
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    paths = sorted(p for p in glob.glob(os.path.join(a.dir, a.glob))
                   if os.path.isfile(p) and not os.path.basename(p).startswith("."))
    if not paths:
        print("no files matched"); return 1
    print(f"amc={a.amc} files={len(paths)} db={a.db} dry_run={a.dry_run}")
    st = ingest_paths(paths, a.amc, a.db, dry_run=a.dry_run)
    print(f"\n  files_seen     {st.files_seen}")
    print(f"  sheets_parsed  {st.sheets_parsed}")
    print(f"  ACCEPTED       {st.accepted}")
    print(f"  rejected       {st.rejected}")
    print(f"  rows_written   {st.rows_written}")
    if st.rejections:
        from collections import Counter
        print("\n  rejections by gate:")
        for g, n in Counter(r[2] for r in st.rejections).most_common():
            print(f"    {g:<22} {n}")
        print("\n  first few:")
        for r in st.rejections[:6]:
            print(f"    [{r[2]}] {r[1][:44]:<46} {r[3][:44]}")
    return 0
sys.exit(main())
