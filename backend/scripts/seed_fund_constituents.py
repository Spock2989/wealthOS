"""
WealthOS — Fund Constituent Seeder  v1.0
=========================================
Fetches AMFI monthly portfolio disclosures for every mutual fund held
in the holdings table and caches stock-level constituents in fund_constituents.

This is the data prerequisite for Holdings X-Ray look-through.

Run on production (internet access required):
    cd /opt/wlthos/backend && source venv/bin/activate
    python3 scripts/seed_fund_constituents.py

Options:
    --force    Force-refresh even if cache is fresh (re-fetches from AMFI)
    --dry-run  Show which funds would be seeded without actually fetching
    --limit N  Process only the first N funds (for testing)

DB path resolution (first match wins):
  1. DATABASE_URL env var
  2. wealthos.db in the parent directory of this script (backend/)
"""

import os
import sys
import time
import sqlite3
import argparse
import logging
import urllib.request
import urllib.parse
import re
from datetime import datetime, date
from typing import List, Optional, Dict, Tuple

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("seed_constituents")


# ── DB path ────────────────────────────────────────────────────────────────
def _resolve_db() -> str:
    raw = os.environ.get("DATABASE_URL", "")
    if raw:
        path = raw.replace("sqlite:////", "/").replace("sqlite:///", "")
        if not os.path.isabs(path):
            # relative → anchor to backend dir (parent of scripts/)
            backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            path = os.path.join(backend_dir, path)
        return path
    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(backend_dir, "wealthos.db")


DB = _resolve_db()

# ── AMFI URL ───────────────────────────────────────────────────────────────
AMFI_PORTFOLIO_URL = "https://www.amfiindia.com/modules/PortfolioAll"
REQUEST_DELAY_SEC  = 2.0   # polite delay between AMFI requests


# ── Sector / cap quick-classifiers (independent of normalizer module) ──────
_SECTOR_KW: Dict[str, List[str]] = {
    "Banking & Financial Services": [
        "bank","hdfc","icici","axis","kotak","sbi","finance","nbfc",
        "bajaj fin","bfsi","insurance","financial","muthoot","shriram",
        "pnb","canara","iob","uco","union bank","federal bank","idfc",
    ],
    "IT": [
        "infosys","tcs","wipro","hcl","software","infy","mphasis","coforge",
        "ltts","hexaware","persistent","tech mahindra","oracle","sap","zensar",
    ],
    "Energy": [
        "reliance","oil","gas","petroleum","power","ntpc","ongc","bpcl",
        "hpcl","iocl","tata power","adani green","coal","renewable","gail",
        "petronet","mrpl","cesc","torrent power",
    ],
    "Pharma": [
        "pharma","health","sun pharma","cipla","dr reddy","hospital","biocon",
        "lupin","alkem","torrent","diagnostic","divi","mankind","zydus","pfizer",
    ],
    "FMCG": [
        "fmcg","hul","hindustan","dabur","nestle","britannia","marico",
        "godrej consumer","itc","emami","colgate","consumer goods","tata consumer",
    ],
    "Auto": [
        "maruti","tata motors","bajaj auto","hero","mahindra","eicher","tvs",
        "vehicle","mobility","m&m","ashok leyland","sona blt","minda","bosch",
    ],
    "Infrastructure": [
        "infra","l&t","larsen","cement","irb","bhel","gmr","adani port",
        "construction","highway","road","abb","siemens","kalpataru","kec",
    ],
    "Metals & Mining": [
        "steel","metal","tata steel","jsw","hindalco","vedanta","copper",
        "aluminium","zinc","mining","coalindia","nmdc","sail","nalco",
    ],
    "Real Estate": [
        "realty","real estate","dlf","godrej properties","oberoi","brigade",
        "prestige","sobha","lodha","macrotech",
    ],
    "Telecom": [
        "telecom","bharti","airtel","vodafone","idea","jio","indus tower",
    ],
    "Fixed Income": [
        "bond","gilt","t-bill","treasury","sovereign","debenture","ncd",
    ],
    "Consumer Discretionary": [
        "retail","trent","avenue supermarts","dmart","titan","tanishq","kalyan",
        "jubilant","dominos","restaurant","hotel","leisure",
    ],
}

def _quick_sector(name: str) -> str:
    n = name.lower()
    for sector, kws in _SECTOR_KW.items():
        if any(k in n for k in kws):
            return sector
    return "Diversified"

def _quick_cap(name: str) -> Optional[str]:
    n = name.lower()
    if any(k in n for k in ["nifty 50","nifty50","large cap","largecap","bluechip","sensex"]):
        return "large"
    if any(k in n for k in ["mid cap","midcap","nifty midcap"]):
        return "mid"
    if any(k in n for k in ["small cap","smallcap","micro cap","nifty smallcap"]):
        return "small"
    return None


# ── DB helpers ─────────────────────────────────────────────────────────────
def db_connect() -> sqlite3.Connection:
    try:
        conn = sqlite3.connect(DB)
        conn.row_factory = sqlite3.Row
        return conn
    except Exception as e:
        log.error("Cannot connect to DB at %s: %s", DB, e)
        sys.exit(1)


def ensure_table(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS fund_constituents (
            id                 TEXT PRIMARY KEY,
            scheme_code        TEXT NOT NULL,
            fund_isin          TEXT,
            fund_name          TEXT,
            underlying_isin    TEXT,
            underlying_name    TEXT,
            underlying_sector  TEXT,
            underlying_cap     TEXT,
            weight_in_fund_pct REAL NOT NULL,
            disclosure_date    TEXT,
            fetched_at         TEXT
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS ix_fc_scheme   ON fund_constituents(scheme_code)")
    conn.execute("CREATE INDEX IF NOT EXISTS ix_fc_u_isin   ON fund_constituents(underlying_isin)")
    conn.execute("CREATE INDEX IF NOT EXISTS ix_fc_fund_isin ON fund_constituents(fund_isin)")
    conn.commit()


def get_fund_isins_from_holdings(conn: sqlite3.Connection) -> List[Tuple[str, str]]:
    """
    Return all unique (isin, instrument_name) pairs from holdings that look like
    mutual funds. Filters out direct equities by checking if a scheme_code exists
    in amfi_instruments for that ISIN.
    """
    rows = conn.execute("""
        SELECT DISTINCT h.isin, h.instrument_name
        FROM   holdings h
        WHERE  h.isin IS NOT NULL
          AND  h.isin != ''
          AND  EXISTS (
              SELECT 1 FROM amfi_instruments a WHERE a.isin = h.isin
          )
        ORDER BY h.isin
    """).fetchall()
    return [(r["isin"], r["instrument_name"] or "") for r in rows]


def get_scheme_code(conn: sqlite3.Connection, isin: str) -> Optional[str]:
    row = conn.execute(
        "SELECT scheme_code FROM amfi_instruments WHERE isin=? LIMIT 1", (isin,)
    ).fetchone()
    return row["scheme_code"] if row else None


def is_cache_fresh(conn: sqlite3.Connection, scheme_code: str, max_age_days: int = 35) -> bool:
    row = conn.execute("""
        SELECT disclosure_date FROM fund_constituents
        WHERE  scheme_code=?
        ORDER  BY fetched_at DESC
        LIMIT  1
    """, (scheme_code,)).fetchone()
    if not row or not row["disclosure_date"]:
        return False
    try:
        d = datetime.strptime(row["disclosure_date"], "%Y-%m-%d").date()
        return (date.today() - d).days <= max_age_days
    except Exception:
        return False


def store_constituents(conn: sqlite3.Connection,
                       scheme_code: str, fund_isin: str, fund_name: str,
                       constituents: List[dict]) -> int:
    import uuid
    fetched_at = datetime.utcnow().isoformat()
    # Delete stale rows for this scheme before inserting fresh data
    conn.execute("DELETE FROM fund_constituents WHERE scheme_code=?", (scheme_code,))
    stored = 0
    for c in constituents:
        try:
            conn.execute("""
                INSERT INTO fund_constituents
                (id, scheme_code, fund_isin, fund_name, underlying_isin,
                 underlying_name, underlying_sector, underlying_cap,
                 weight_in_fund_pct, disclosure_date, fetched_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """, (
                str(uuid.uuid4()),
                scheme_code, fund_isin, fund_name,
                c.get("underlying_isin", ""),
                c.get("underlying_name", ""),
                c.get("underlying_sector", ""),
                c.get("underlying_cap", ""),
                float(c.get("weight_in_fund_pct", 0)),
                c.get("disclosure_date", date.today().isoformat()),
                fetched_at,
            ))
            stored += 1
        except Exception as e:
            log.debug("Row insert failed: %s", e)
    conn.commit()
    return stored


# ── AMFI fetch + parse ─────────────────────────────────────────────────────
def fetch_and_parse(scheme_code: str, fund_name: str) -> List[dict]:
    """
    GET AMFI portfolio disclosure for this scheme_code.
    Returns list of constituent dicts sorted by weight desc, or [] on failure.
    """
    url = f"{AMFI_PORTFOLIO_URL}?SchemeCode={urllib.parse.quote(str(scheme_code))}"
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "WealthOS/2.0 (Analytics; wlthos.in)",
                "Accept":     "text/html,application/xhtml+xml,text/plain",
            }
        )
        resp = urllib.request.urlopen(req, timeout=20)
        html = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        log.warning("  AMFI fetch failed for scheme %s: %s", scheme_code, e)
        return []

    return _parse_html(html, fund_name)


def _parse_html(html: str, fund_name: str) -> List[dict]:
    """
    Parse AMFI portfolio HTML.
    Expected table structure:
      Name of Instrument | ISIN | Rating/Industry | Quantity | Market Value | % to NAV
    We extract rows that contain a 12-char ISIN (INE...) and a numeric weight.
    """
    constituents: List[dict] = []
    disclosure_date = date.today().isoformat()

    # Try to extract the disclosure date from the HTML ("As on DD-MM-YYYY" / "As on DD/MM/YYYY")
    dm = re.search(r'[Aa]s\s+on\s+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', html)
    if dm:
        try:
            d, m, y = dm.group(1), dm.group(2), dm.group(3)
            y = "20" + y if len(y) == 2 else y
            disclosure_date = f"{y}-{int(m):02d}-{int(d):02d}"
        except Exception:
            pass

    # Parse <tr> rows
    rows = re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.IGNORECASE | re.DOTALL)
    for row in rows:
        cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.IGNORECASE | re.DOTALL)
        cells = [re.sub(r'<[^>]+>', '', c).strip() for c in cells]
        if len(cells) < 3:
            continue

        # Find a valid ISIN (two uppercase letters + 10 alphanumeric chars)
        isin = None
        isin_idx = -1
        for i, cell in enumerate(cells):
            if re.match(r'^[A-Z]{2}[A-Z0-9]{10}$', cell.strip()):
                isin = cell.strip()
                isin_idx = i
                break
        if not isin:
            continue

        # Name: cell immediately before ISIN (usually), else first non-empty cell
        name = ""
        if isin_idx > 0:
            name = cells[isin_idx - 1].strip()
        if not name or re.match(r'^[A-Z]{2}[A-Z0-9]{10}$', name):
            # Try first text cell
            for c in cells:
                if c and not re.match(r'^[A-Z]{2}[A-Z0-9]{10}$', c) and not c.replace('.','').replace(',','').replace('-','').isdigit():
                    name = c
                    break

        # Weight: find a float between 0.01 and 100 in the remaining cells
        # Skip the ISIN cell and name cell — look for the rightmost numeric value ≤ 100
        weight = 0.0
        for cell in reversed(cells):
            clean = cell.replace(',', '').strip()
            try:
                val = float(clean)
                if 0.01 <= val <= 100.0:
                    weight = val
                    break
            except ValueError:
                continue
        if weight <= 0:
            continue

        sector = _quick_sector(name)
        cap    = _quick_cap(fund_name)  # cap hint from fund name if stock name doesn't say

        constituents.append({
            "underlying_isin":    isin,
            "underlying_name":    name or isin,
            "underlying_sector":  sector,
            "underlying_cap":     cap,
            "weight_in_fund_pct": round(weight, 3),
            "disclosure_date":    disclosure_date,
        })

    # Sanity check: total weight ≤ 130% (accounting for cash + derivatives)
    total_w = sum(c["weight_in_fund_pct"] for c in constituents)
    if constituents and total_w > 150:
        log.warning("  Weight total %.1f%% > 150%% for scheme — data suspect, discarding", total_w)
        return []

    constituents.sort(key=lambda x: x["weight_in_fund_pct"], reverse=True)
    return constituents


# ── Main ───────────────────────────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(description="Seed fund_constituents from AMFI")
    parser.add_argument("--force",   action="store_true", help="Re-fetch even if cache is fresh")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be fetched, no writes")
    parser.add_argument("--limit",   type=int, default=0, help="Process at most N funds")
    args = parser.parse_args()

    print(f"\n{'='*60}")
    print("  WealthOS — Fund Constituent Seeder")
    print(f"  DB      : {DB}")
    print(f"  Force   : {args.force}")
    print(f"  Dry-run : {args.dry_run}")
    print(f"{'='*60}\n")

    conn = db_connect()
    ensure_table(conn)

    # Discover all fund ISINs in holdings that have a scheme_code in amfi_instruments
    fund_list = get_fund_isins_from_holdings(conn)
    if not fund_list:
        print("No mutual fund ISINs found in holdings table.")
        print("Have you run seed_amfi.py and uploaded at least one CAS file?")
        conn.close()
        sys.exit(0)

    if args.limit:
        fund_list = fund_list[:args.limit]

    print(f"Found {len(fund_list)} distinct mutual fund ISINs in holdings\n")

    stats = {
        "fetched":    0,
        "cached":     0,
        "no_data":    0,
        "no_scheme":  0,
        "total_rows": 0,
    }

    for idx, (isin, name) in enumerate(fund_list, 1):
        scheme_code = get_scheme_code(conn, isin)
        if not scheme_code:
            log.info("[%2d/%d] %-45s ISIN=%s → no scheme_code (equity?)",
                     idx, len(fund_list), name[:45], isin)
            stats["no_scheme"] += 1
            continue

        if not args.force and is_cache_fresh(conn, scheme_code):
            log.info("[%2d/%d] %-45s scheme=%-8s → cache fresh ✓",
                     idx, len(fund_list), name[:45], scheme_code)
            stats["cached"] += 1
            continue

        log.info("[%2d/%d] %-45s scheme=%-8s → fetching AMFI...",
                 idx, len(fund_list), name[:45], scheme_code)

        if args.dry_run:
            print(f"         DRY-RUN: would fetch scheme {scheme_code}")
            continue

        constituents = fetch_and_parse(scheme_code, name)

        if not constituents:
            log.warning("         No constituent data returned — fund may be FoF or AMFI not disclosing")
            stats["no_data"] += 1
        else:
            stored = store_constituents(conn, scheme_code, isin, name, constituents)
            log.info("         Stored %d rows  (top: %s %.1f%%)",
                     stored,
                     constituents[0]["underlying_name"][:30] if constituents else "",
                     constituents[0]["weight_in_fund_pct"] if constituents else 0)
            stats["fetched"]    += 1
            stats["total_rows"] += stored

        # Polite delay — don't hammer AMFI
        time.sleep(REQUEST_DELAY_SEC)

    # ── Summary ────────────────────────────────────────────────────────────
    total_funds = conn.execute(
        "SELECT COUNT(DISTINCT scheme_code) FROM fund_constituents"
    ).fetchone()[0]
    total_rows = conn.execute(
        "SELECT COUNT(*) FROM fund_constituents"
    ).fetchone()[0]
    conn.close()

    print(f"\n{'='*60}")
    print("  SEEDING COMPLETE")
    print(f"  Funds fetched this run : {stats['fetched']}")
    print(f"  Funds from cache       : {stats['cached']}")
    print(f"  Funds with no AMFI data: {stats['no_data']}")
    print(f"  Not a fund (equity)    : {stats['no_scheme']}")
    print(f"  Rows stored this run   : {stats['total_rows']}")
    print(f"  Total funds in DB      : {total_funds}")
    print(f"  Total constituent rows : {total_rows}")
    print(f"{'='*60}")
    print()

    if stats["no_data"] > 0:
        print(f"  ⚠  {stats['no_data']} fund(s) returned no constituent data from AMFI.")
        print("     These will show as 'data_pending' in Holdings X-Ray.")
        print("     Re-run with --force in 2-3 days if AMFI hasn't published yet.")

    if total_funds > 0:
        print(f"\n  ✓ Holdings X-Ray is ready — {total_funds} fund(s) decomposed to stock level.")
    print()


if __name__ == "__main__":
    main()
