"""
WealthOS — AMFI Scheme Master Seeder
=====================================
Downloads NAVAll.txt from AMFI and upserts all scheme records into
the amfi_instruments table.

Run from /opt/wlthos/backend with venv active:
    python3 seed_amfi.py

DB path resolution (first match wins):
  1. DATABASE_URL env var  (sqlite:///wealthos.db  or  sqlite:////abs/path)
  2. wealthos.db in the same directory as this script
"""

import os
import sys
import sqlite3
import urllib.request

# ── DB path ────────────────────────────────────────────────────────────────
def _resolve_db() -> str:
    raw = os.environ.get("DATABASE_URL", "")
    if raw:
        path = raw.replace("sqlite:////", "/").replace("sqlite:///", "")
        if not os.path.isabs(path):
            path = os.path.join(os.path.dirname(os.path.abspath(__file__)), path)
        return path
    # Default: wealthos.db next to this script
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "wealthos.db")

DB  = _resolve_db()
URL = "https://www.amfiindia.com/spages/NAVAll.txt"

print(f"DB path : {DB}")

# ── Download AMFI NAVAll.txt ───────────────────────────────────────────────
print("Downloading AMFI scheme master...")
req = urllib.request.Request(URL, headers={"User-Agent": "WealthOS/2.0 (wlthos.in)"})
try:
    content = urllib.request.urlopen(req, timeout=60).read().decode("utf-8", errors="replace")
except Exception as e:
    print(f"ERROR: Could not download AMFI data: {e}", file=sys.stderr)
    sys.exit(1)

print(f"Downloaded {len(content):,} bytes")

# ── Parse NAVAll.txt ───────────────────────────────────────────────────────
# Format:
#   Blank line or AMC name line (no semicolons)
#   Open Ended Schemes(category) — category header
#   scheme_code;isin_growth;isin_div_reinvest;scheme_name;nav;nav_date
schemes = []
amc   = ""
stype = ""

for line in content.splitlines():
    line = line.strip()
    if not line:
        continue
    if ";" not in line:
        if "Open Ended" in line or "Close Ended" in line or "Interval" in line:
            s = line.find("(")
            e = line.rfind(")")
            stype = line[s+1:e] if s != -1 else line
        elif not line.startswith("Scheme"):
            amc = line
        continue

    p = line.split(";")
    if len(p) < 6 or not p[0].strip().isdigit():
        continue

    isin = p[1].strip() if p[1].strip() not in ("-", "", "N.A.") else None
    # p[2] = ISIN (Div Reinvestment) — we prefer the growth ISIN (p[1])
    sn = p[3].strip().lower()
    st = stype.lower()

    if any(x in st for x in ["debt", "liquid", "bond", "gilt", "money market", "overnight", "ultra short"]):
        ac = "debt"
    elif any(x in st for x in ["hybrid", "balanced", "conservative", "aggressive"]):
        ac = "hybrid"
    elif "fund of fund" in st:
        ac = "fof"
    elif any(x in sn for x in ["gold", "silver"]):
        ac = "commodity"
    else:
        ac = "equity"

    plan = "direct" if "direct" in sn else "regular"
    try:
        nav = float(p[4].strip())
    except Exception:
        nav = None

    schemes.append((
        p[0].strip(),   # scheme_code
        isin,           # isin
        p[3].strip(),   # scheme_name
        amc,            # amc_name
        stype,          # scheme_type
        ac,             # asset_class
        plan,           # plan
        nav,            # nav
    ))

print(f"Parsed {len(schemes):,} schemes")

# ── Upsert into DB ────────────────────────────────────────────────────────
try:
    conn = sqlite3.connect(DB)
except Exception as e:
    print(f"ERROR: Cannot open DB at {DB}: {e}", file=sys.stderr)
    sys.exit(1)

conn.execute("""
CREATE TABLE IF NOT EXISTS amfi_instruments (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    scheme_code TEXT UNIQUE NOT NULL,
    isin        TEXT,
    scheme_name TEXT,
    amc_name    TEXT,
    scheme_type TEXT,
    asset_class TEXT,
    plan        TEXT,
    nav         REAL
)
""")
conn.execute("CREATE INDEX IF NOT EXISTS ix_amfi_isin ON amfi_instruments(isin)")
conn.execute("CREATE INDEX IF NOT EXISTS ix_amfi_scheme ON amfi_instruments(scheme_code)")

inserted = 0
skipped  = 0
for s in schemes:
    try:
        conn.execute(
            """INSERT OR REPLACE INTO amfi_instruments
               (scheme_code, isin, scheme_name, amc_name, scheme_type, asset_class, plan, nav)
               VALUES (?,?,?,?,?,?,?,?)""",
            s,
        )
        inserted += 1
    except Exception:
        skipped += 1

conn.commit()
total = conn.execute("SELECT COUNT(*) FROM amfi_instruments").fetchone()[0]
isin_count = conn.execute(
    "SELECT COUNT(*) FROM amfi_instruments WHERE isin IS NOT NULL"
).fetchone()[0]
conn.close()

print(f"Inserted/replaced : {inserted:,}")
print(f"Skipped           : {skipped}")
print(f"Total in DB       : {total:,}  ({isin_count:,} with ISIN)")
print("✓ AMFI scheme master seeded — ready for fund constituent seeding")
