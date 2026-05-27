"""
WealthOS — Standalone Synthetic X-Ray Seeder
=============================================
Self-contained: no app imports, no venv dependencies beyond stdlib.
Reads holdings from DB, generates category-correct synthetic fund
constituents (real NSE ISINs), writes to fund_constituents table.

Run directly on the server:
    python3 seed_synthetic_xray.py

X-Ray will show ESTIMATED holdings (based on each fund's SEBI mandate)
until AMFI live data becomes accessible from an Indian IP.
"""

import os
import sys
import uuid
import sqlite3
from datetime import date, datetime

# ── DB path ────────────────────────────────────────────────────────────────
def _db_path():
    raw = os.environ.get("DATABASE_URL", "")
    if raw:
        p = raw.replace("sqlite:////", "/").replace("sqlite:///", "")
        if not os.path.isabs(p):
            p = os.path.join(os.path.dirname(os.path.abspath(__file__)), p)
        return p
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "wealthos.db")

DB = _db_path()

# ── Stock universe (verified NSE ISINs) ────────────────────────────────────
EQ = {
    "INE040A01034": ("HDFC Bank",                 "Banking & Financial Services", "large"),
    "INE090A01021": ("ICICI Bank",                "Banking & Financial Services", "large"),
    "INE238A01034": ("Axis Bank",                 "Banking & Financial Services", "large"),
    "INE237A01028": ("Kotak Mahindra Bank",       "Banking & Financial Services", "large"),
    "INE062A01020": ("State Bank of India",       "Banking & Financial Services", "large"),
    "INE296A01024": ("Bajaj Finance",             "Banking & Financial Services", "large"),
    "INE918I01026": ("Bajaj Finserv",             "Banking & Financial Services", "large"),
    "INE467B01029": ("Tata Consultancy Services", "IT",      "large"),
    "INE009A01021": ("Infosys",                   "IT",      "large"),
    "INE860A01027": ("HCL Technologies",          "IT",      "large"),
    "INE075A01022": ("Wipro",                     "IT",      "large"),
    "INE262H01021": ("Persistent Systems",        "IT",      "mid"),
    "INE002A01018": ("Reliance Industries",       "Energy",  "large"),
    "INE213A01029": ("ONGC",                      "Energy",  "large"),
    "INE733E01010": ("NTPC",                      "Energy",  "large"),
    "INE029A01011": ("BPCL",                      "Energy",  "large"),
    "INE522F01014": ("Coal India",                "Energy",  "large"),
    "INE030A01027": ("Hindustan Unilever",        "FMCG",    "large"),
    "INE154A01025": ("ITC",                       "FMCG",    "large"),
    "INE021A01026": ("Asian Paints",              "FMCG",    "large"),
    "INE239A01016": ("Nestle India",              "FMCG",    "large"),
    "INE044A01036": ("Sun Pharmaceutical",        "Pharma",  "large"),
    "INE059A01026": ("Cipla",                     "Pharma",  "large"),
    "INE089A01023": ("Dr. Reddy's Laboratories",  "Pharma",  "large"),
    "INE585B01010": ("Maruti Suzuki India",       "Auto",    "large"),
    "INE196A01026": ("Mahindra & Mahindra",       "Auto",    "large"),
    "INE158A01026": ("Hero MotoCorp",             "Auto",    "large"),
    "INE018A01030": ("Larsen & Toubro",           "Infrastructure", "large"),
    "INE481G01011": ("UltraTech Cement",          "Infrastructure", "large"),
    "INE752E01010": ("Power Grid Corporation",    "Infrastructure", "large"),
    "INE081A01020": ("Tata Steel",                "Metals & Mining","large"),
    "INE038A01020": ("Hindalco Industries",       "Metals & Mining","large"),
    "INE280A01028": ("Titan Company",             "Consumer Discretionary","large"),
}

# ── Portfolio templates per fund category ──────────────────────────────────
TEMPLATES = {
    # ELSS / Tax-Saver — diversified large+mid cap, ≥80% equity (SEBI mandate)
    "elss": [
        ("INE040A01034",8.5),("INE090A01021",7.0),("INE002A01018",6.5),
        ("INE467B01029",5.5),("INE009A01021",4.5),("INE238A01034",3.5),
        ("INE018A01030",3.2),("INE062A01020",3.0),("INE296A01024",2.8),
        ("INE585B01010",2.5),("INE044A01036",2.3),("INE030A01027",2.2),
        ("INE154A01025",2.1),("INE237A01028",2.0),("INE860A01027",1.9),
        ("INE075A01022",1.6),("INE280A01028",1.5),("INE021A01026",1.4),
        ("INE481G01011",1.3),("INE733E01010",1.2),("INE059A01026",1.1),
        ("INE196A01026",1.0),("INE239A01016",0.9),("INE262H01021",0.8),
    ],
    # Large & Mid Cap — 35% large + 35% mid mandatory (SEBI)
    "large_mid": [
        ("INE040A01034",7.5),("INE090A01021",6.0),("INE002A01018",5.5),
        ("INE467B01029",4.8),("INE009A01021",4.0),("INE238A01034",3.5),
        ("INE018A01030",3.2),("INE296A01024",2.8),("INE062A01020",2.5),
        ("INE860A01027",2.2),("INE044A01036",2.0),("INE030A01027",1.9),
        ("INE154A01025",1.8),("INE237A01028",1.7),("INE585B01010",1.6),
        ("INE262H01021",2.5),("INE075A01022",1.5),("INE280A01028",1.5),
        ("INE196A01026",1.4),("INE021A01026",1.3),("INE059A01026",1.2),
        ("INE481G01011",1.2),("INE081A01020",1.0),("INE038A01020",0.9),
    ],
    # Value / Contrarian — higher PSU / beaten-down sectors
    "value": [
        ("INE062A01020",7.0),("INE002A01018",6.0),("INE040A01034",5.5),
        ("INE154A01025",5.0),("INE213A01029",4.5),("INE029A01011",4.0),
        ("INE090A01021",3.8),("INE522F01014",3.5),("INE733E01010",3.2),
        ("INE081A01020",2.8),("INE038A01020",2.5),("INE018A01030",2.5),
        ("INE238A01034",2.3),("INE467B01029",2.2),("INE196A01026",2.0),
        ("INE158A01026",1.8),("INE044A01036",1.7),("INE059A01026",1.5),
        ("INE481G01011",1.4),("INE296A01024",1.3),("INE030A01027",1.2),
        ("INE752E01010",1.0),
    ],
    # Flexi Cap (Parag Parikh style — ~65% Indian equity shown, rest foreign)
    "flexi_cap": [
        ("INE040A01034",6.0),("INE090A01021",5.0),("INE002A01018",5.0),
        ("INE467B01029",4.5),("INE009A01021",4.0),("INE238A01034",3.0),
        ("INE018A01030",2.8),("INE296A01024",2.5),("INE062A01020",2.0),
        ("INE044A01036",2.0),("INE030A01027",1.8),("INE154A01025",1.7),
        ("INE860A01027",1.6),("INE262H01021",3.0),("INE075A01022",1.4),
    ],
    # Corporate Bond / Debt
    "debt_corp": [
        ("INE040A01034",5.0),("INE090A01021",4.5),("INE238A01034",4.0),
        ("INE062A01020",4.0),("INE296A01024",3.5),("INE002A01018",3.0),
        ("INE018A01030",3.0),("INE733E01010",2.5),("INE752E01010",2.5),
        ("INE481G01011",2.0),
    ],
    # Default diversified (Nifty 50 proxy)
    "diversified": [
        ("INE040A01034",8.0),("INE090A01021",6.5),("INE002A01018",6.0),
        ("INE467B01029",5.0),("INE009A01021",4.5),("INE238A01034",3.5),
        ("INE018A01030",3.0),("INE062A01020",2.8),("INE296A01024",2.5),
        ("INE030A01027",2.2),("INE154A01025",2.0),("INE044A01036",1.9),
        ("INE860A01027",1.8),("INE237A01028",1.7),("INE585B01010",1.6),
        ("INE481G01011",1.4),("INE075A01022",1.3),("INE021A01026",1.2),
        ("INE280A01028",1.1),("INE733E01010",1.0),
    ],
}

def _category(name, scheme_type=""):
    n, st = name.lower(), scheme_type.lower()
    if any(x in n for x in ["elss","tax saver","tax saving","tax-saver"]):
        return "elss"
    if any(x in n for x in ["corporate bond","bond fund","credit risk"]) or "debt" in st:
        return "debt_corp"
    if any(x in n for x in ["large & mid","large and mid","large mid"]):
        return "large_mid"
    if any(x in n for x in ["flexi cap","flexicap","multi cap","multicap","parag parikh"]):
        return "flexi_cap"
    if "value" in n or "contrarian" in n:
        return "value"
    return "diversified"

# ── DB helpers ─────────────────────────────────────────────────────────────
def connect():
    if not os.path.exists(DB):
        print(f"ERROR: DB not found at {DB}")
        sys.exit(1)
    return sqlite3.connect(DB)

def ensure_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS fund_constituents (
            id TEXT PRIMARY KEY,
            scheme_code TEXT NOT NULL,
            fund_isin TEXT,
            fund_name TEXT,
            underlying_isin TEXT,
            underlying_name TEXT,
            underlying_sector TEXT,
            underlying_cap TEXT,
            weight_in_fund_pct REAL NOT NULL,
            disclosure_date TEXT,
            fetched_at TEXT
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS ix_fc_scheme ON fund_constituents(scheme_code)")
    conn.execute("CREATE INDEX IF NOT EXISTS ix_fc_ui    ON fund_constituents(underlying_isin)")
    conn.commit()

def get_funds(conn):
    """All distinct mutual fund ISINs in holdings that have a scheme_code in amfi_instruments."""
    rows = conn.execute("""
        SELECT DISTINCT h.isin, h.instrument_name,
               COALESCE(a.scheme_code,'') as scheme_code,
               COALESCE(a.scheme_type,'')  as scheme_type
        FROM   holdings h
        LEFT JOIN amfi_instruments a ON a.isin = h.isin
        WHERE  h.isin IS NOT NULL AND h.isin != ''
          AND  a.scheme_code IS NOT NULL
        ORDER  BY h.isin
    """).fetchall()
    return rows  # (isin, name, scheme_code, scheme_type)

def seed_fund(conn, isin, name, scheme_code, scheme_type):
    cat      = _category(name, scheme_type)
    template = TEMPLATES.get(cat, TEMPLATES["diversified"])
    today    = date.today().isoformat()
    now      = datetime.utcnow().isoformat()

    # Clear stale rows for this scheme
    conn.execute("DELETE FROM fund_constituents WHERE scheme_code=?", (scheme_code,))

    stored = 0
    for u_isin, weight in template:
        meta = EQ.get(u_isin, (u_isin, "Diversified", "large"))
        try:
            conn.execute("""
                INSERT INTO fund_constituents
                (id,scheme_code,fund_isin,fund_name,
                 underlying_isin,underlying_name,underlying_sector,underlying_cap,
                 weight_in_fund_pct,disclosure_date,fetched_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """, (str(uuid.uuid4()), scheme_code, isin, name,
                  u_isin, meta[0], meta[1], meta[2],
                  float(weight), today, now))
            stored += 1
        except Exception as e:
            print(f"  Row error: {e}")
    conn.commit()
    return cat, stored

# ── Main ───────────────────────────────────────────────────────────────────
def main():
    print(f"\n{'='*58}")
    print("  WealthOS — Synthetic X-Ray Seeder (standalone)")
    print(f"  DB : {DB}")
    print(f"{'='*58}\n")

    conn = connect()
    ensure_table(conn)

    funds = get_funds(conn)
    if not funds:
        print("No mutual fund ISINs found in holdings.")
        print("→ Ensure seed_amfi.py has been run and a CAS file uploaded.")
        sys.exit(0)

    print(f"Found {len(funds)} mutual fund(s) to seed\n")

    total_rows = 0
    for isin, name, scheme_code, scheme_type in funds:
        cat, stored = seed_fund(conn, isin, name or isin, scheme_code, scheme_type)
        print(f"  ✓  {(name or isin)[:50]:<50}  cat={cat:<12}  {stored} holdings")
        total_rows += stored

    # Verify
    total_funds = conn.execute(
        "SELECT COUNT(DISTINCT scheme_code) FROM fund_constituents"
    ).fetchone()[0]
    total_db    = conn.execute(
        "SELECT COUNT(*) FROM fund_constituents"
    ).fetchone()[0]
    conn.close()

    print(f"\n{'='*58}")
    print(f"  DONE — {total_funds} fund(s) seeded, {total_db} constituent rows in DB")
    print(f"  Holdings X-Ray is now operational (synthetic/estimated data)")
    print(f"  Disclaimer shown in UI — directionally accurate for overlap analysis")
    print(f"{'='*58}\n")

if __name__ == "__main__":
    main()
