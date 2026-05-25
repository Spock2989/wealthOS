import urllib.request
import sqlite3

DB = "/Users/user/wealthos/backend/wealthos.db"
URL = "https://www.amfiindia.com/spages/NAVAll.txt"

print("Downloading AMFI data...")
req = urllib.request.Request(URL, headers={"User-Agent": "WealthOS/1.0"})
content = urllib.request.urlopen(req, timeout=60).read().decode("utf-8", errors="replace")
print(f"Downloaded {len(content):,} bytes")

schemes = []
amc = ""
stype = ""

for line in content.splitlines():
    line = line.strip()
    if not line:
        continue
    if ";" not in line:
        if "Open Ended" in line or "Close Ended" in line:
            s = line.find("(")
            e = line.rfind(")")
            stype = line[s+1:e] if s != -1 else line
        elif line and not line.startswith("Scheme"):
            amc = line
        continue
    p = line.split(";")
    if len(p) < 6 or not p[0].isdigit():
        continue
    isin = p[1].strip() if p[1].strip() not in ("-", "") else None
    sn = p[3].strip().lower()
    st = stype.lower()
    if any(x in st for x in ["debt", "liquid", "bond", "gilt"]):
        ac = "debt"
    elif any(x in st for x in ["hybrid", "balanced"]):
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
    schemes.append((p[0].strip(), isin, p[3].strip(), amc, stype, ac, plan, nav))

print(f"Parsed {len(schemes):,} schemes")

conn = sqlite3.connect(DB)
conn.execute("""
CREATE TABLE IF NOT EXISTS amfi_instruments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scheme_code TEXT UNIQUE,
    isin TEXT,
    scheme_name TEXT,
    amc_name TEXT,
    scheme_type TEXT,
    asset_class TEXT,
    plan TEXT,
    nav REAL
)
""")
conn.execute("CREATE INDEX IF NOT EXISTS ix_isin ON amfi_instruments(isin)")

ins = 0
for s in schemes:
    try:
        conn.execute(
            "INSERT OR REPLACE INTO amfi_instruments VALUES (NULL,?,?,?,?,?,?,?,?)", s
        )
        ins += 1
    except Exception:
        pass

conn.commit()
total = conn.execute("SELECT COUNT(*) FROM amfi_instruments").fetchone()[0]
conn.close()
print(f"Inserted: {ins:,}  Total in DB: {total:,}")
print("AMFI master seeded successfully!")
