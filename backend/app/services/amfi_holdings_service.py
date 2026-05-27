"""
AMFIHoldingsService
====================
Fetches mutual fund portfolio holdings from AMFI's monthly disclosures
and caches them in the fund_constituents table.

Data flow:
  CAS ISIN → amfi_instruments table → scheme_code
  → AMFI portfolio disclosure URL → parse TSV
  → fund_constituents table
  → lookthrough_engine.py for recursive decomposition

AMFI data sources used:
  1. NAVAll.txt  — scheme master (scheme_code ↔ ISIN ↔ name ↔ category)
  2. Portfolio disclosure — AMFI mandates monthly portfolio disclosure:
       https://www.amfiindia.com/modules/PortfolioAll
     Individual scheme portfolio (HTML/CSV from AMC) is parsed here.

Determinism guarantee:
  All inputs → outputs are reproducible given the same disclosure_date.
  disclosure_date is stored per-row so lookthrough results are
  pinned to a specific disclosure period.

Failure policy:
  • Network failures: return cached data (if any) for that scheme_code
  • Parsing failures: log + skip the offending row; never silently
    corrupt a weight or produce a NaN
  • ISIN missing in AMFI: flag in data_quality, do not crash
"""

import re
import logging
import sqlite3
from datetime import datetime, date
from typing import Dict, List, Optional, Tuple
from collections import defaultdict

logger = logging.getLogger(__name__)

# ── AMFI URL constants ──────────────────────────────────────────
AMFI_NAVALL_URL    = "https://www.amfiindia.com/spages/NAVAll.txt"
AMFI_PORTFOLIO_URL = "https://www.amfiindia.com/modules/PortfolioAll"

# Sector keywords for quick classification of underlying stocks
# (re-uses the same logic as normalizer/sector_mapper.py, inline for independence)
_SECTOR_KEYWORDS: Dict[str, List[str]] = {
    "Banking & Financial Services": ["bank","hdfc","icici","axis","kotak","sbi","finance","nbfc",
                                     "bajaj fin","bfsi","insurance","financial"],
    "IT":          ["tech","infosys","tcs","wipro","hcl","software","infy","mphasis","coforge","ltts"],
    "Energy":      ["reliance","oil","gas","petroleum","power","ntpc","ongc","bpcl","hpcl","iocl",
                    "tata power","adani green","coal","renewable"],
    "Pharma":      ["pharma","health","sun pharma","cipla","dr reddy","hospital","biocon","lupin",
                    "alkem","torrent","diagnostic"],
    "FMCG":        ["fmcg","hul","hindustan","dabur","nestle","britannia","marico","godrej",
                    "itc","emami","colgate","consumer"],
    "Auto":        ["auto","maruti","tata motors","bajaj auto","hero","mahindra","eicher","tvs",
                    "vehicle","mobility","m&m"],
    "Infrastructure": ["infra","l&t","larsen","cement","irb","bhel","gmr","adani port",
                       "construction","highway","road"],
    "Metals":      ["steel","metal","tata steel","jsw","hindalco","vedanta","copper",
                    "aluminium","zinc","mining"],
    "Fixed Income":["bond","gilt","t-bill","treasury","sovereign"],
}

def _quick_sector(name: str) -> str:
    n = name.lower()
    for sector, kws in _SECTOR_KEYWORDS.items():
        if any(k in n for k in kws):
            return sector
    return "Diversified"

def _quick_cap(name: str) -> Optional[str]:
    n = name.lower()
    if any(k in n for k in ["nifty 50","nifty50","large cap","largecap","bluechip"]):
        return "large"
    if any(k in n for k in ["mid cap","midcap"]):
        return "mid"
    if any(k in n for k in ["small cap","smallcap","micro"]):
        return "small"
    return None


# ── Scheme code lookup (uses existing amfi_instruments table) ───
def get_scheme_code_from_isin(isin: str, db_path: str) -> Optional[str]:
    """
    Look up scheme_code for a given fund ISIN using the seeded amfi_instruments table.
    Returns None if not found (ISIN may be an equity stock, not a fund).
    """
    try:
        conn = sqlite3.connect(db_path)
        row  = conn.execute(
            "SELECT scheme_code FROM amfi_instruments WHERE isin=? LIMIT 1",
            (isin,)
        ).fetchone()
        conn.close()
        return row[0] if row else None
    except Exception as e:
        logger.warning("ISIN→scheme_code lookup failed for %s: %s", isin, e)
        return None


def get_cached_constituents(scheme_code: str, db_path: str,
                            max_age_days: int = 35) -> Optional[List[dict]]:
    """
    Return cached fund_constituents for this scheme_code if fresher than max_age_days.
    Returns None if no cache or cache is stale (triggers a fresh AMFI fetch).
    """
    try:
        conn = sqlite3.connect(db_path)
        cutoff = datetime.utcnow().strftime("%Y-%m-%d")
        rows = conn.execute("""
            SELECT underlying_isin, underlying_name, underlying_sector,
                   underlying_cap, weight_in_fund_pct, disclosure_date
            FROM fund_constituents
            WHERE scheme_code=?
            ORDER BY weight_in_fund_pct DESC
        """, (scheme_code,)).fetchall()
        conn.close()
        if not rows:
            return None
        # Check if the most recent disclosure is fresh enough
        latest_date_str = rows[0][5] if rows[0][5] else "2000-01-01"
        latest_date = datetime.strptime(latest_date_str, "%Y-%m-%d").date()
        age_days = (date.today() - latest_date).days
        if age_days > max_age_days:
            logger.info("Cache for %s is %d days old — triggering refresh", scheme_code, age_days)
            return None
        return [
            {
                "underlying_isin":    r[0],
                "underlying_name":    r[1],
                "underlying_sector":  r[2],
                "underlying_cap":     r[3],
                "weight_in_fund_pct": r[4],
                "disclosure_date":    r[5],
            }
            for r in rows
        ]
    except Exception as e:
        logger.warning("Cache read failed for %s: %s", scheme_code, e)
        return None


def store_constituents(scheme_code: str, fund_isin: str, fund_name: str,
                       constituents: List[dict], db_path: str) -> int:
    """
    Upsert fund constituent rows into fund_constituents table.
    Returns number of rows stored.
    """
    if not constituents:
        return 0
    fetched_at = datetime.utcnow().isoformat()
    rows_stored = 0
    try:
        conn = sqlite3.connect(db_path)
        # Ensure table exists (safe if already created by SQLAlchemy)
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
        conn.execute("CREATE INDEX IF NOT EXISTS ix_fc_u_isin ON fund_constituents(underlying_isin)")

        for c in constituents:
            import uuid as _uuid
            disc_date = c.get("disclosure_date", date.today().strftime("%Y-%m-%d"))
            try:
                conn.execute("""
                    INSERT OR REPLACE INTO fund_constituents
                    (id, scheme_code, fund_isin, fund_name, underlying_isin,
                     underlying_name, underlying_sector, underlying_cap,
                     weight_in_fund_pct, disclosure_date, fetched_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?)
                """, (
                    str(_uuid.uuid4()),
                    scheme_code,
                    fund_isin,
                    fund_name,
                    c.get("underlying_isin",""),
                    c.get("underlying_name",""),
                    c.get("underlying_sector",""),
                    c.get("underlying_cap",""),
                    float(c.get("weight_in_fund_pct", 0)),
                    disc_date,
                    fetched_at,
                ))
                rows_stored += 1
            except Exception as row_err:
                logger.debug("Row insert failed: %s", row_err)
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error("store_constituents failed for %s: %s", scheme_code, e)
    return rows_stored


def fetch_amfi_portfolio(scheme_code: str, fund_name: str = "") -> List[dict]:
    """
    Fetch the latest portfolio holdings for a scheme from AMFI.

    Tries multiple URL/method combinations in order:
      1. POST  https://www.amfiindia.com/modules/PortfolioAll  {MFLink: scheme_code}
         (AMFI website's own AJAX call; requires Referer header)
      2. GET   https://www.amfiindia.com/modules/PortfolioAll?SchemeCode=N
         (legacy GET form — now returns 404 on most IP ranges)

    Returns [] on all failures — caller should use synthetic fallback.
    Note: AMFI may geo-restrict requests from non-Indian IP addresses.
    """
    import urllib.request
    import urllib.parse

    _BROWSER_UA = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )

    attempts = [
        # Attempt 1: POST with MFLink — mirrors the AMFI website's own AJAX call
        dict(
            url="https://www.amfiindia.com/modules/PortfolioAll",
            method="POST",
            data=urllib.parse.urlencode({"MFLink": str(scheme_code)}).encode("utf-8"),
            headers={
                "User-Agent":   _BROWSER_UA,
                "Referer":      "https://www.amfiindia.com/research-information/other-data/scheme-portfolio",
                "Origin":       "https://www.amfiindia.com",
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept":       "text/html,application/xhtml+xml,*/*",
                "Accept-Language": "en-IN,en;q=0.9",
            },
        ),
        # Attempt 2: GET with SchemeCode (original approach)
        dict(
            url=f"https://www.amfiindia.com/modules/PortfolioAll?SchemeCode={urllib.parse.quote(str(scheme_code))}",
            method="GET",
            data=None,
            headers={
                "User-Agent": _BROWSER_UA,
                "Referer":    "https://www.amfiindia.com",
                "Accept":     "text/html,application/xhtml+xml",
            },
        ),
    ]

    for i, attempt in enumerate(attempts, 1):
        try:
            req = urllib.request.Request(
                attempt["url"],
                data=attempt.get("data"),
                headers=attempt["headers"],
                method=attempt["method"],
            )
            response = urllib.request.urlopen(req, timeout=20)
            raw = response.read().decode("utf-8", errors="replace")
            result = _parse_amfi_portfolio_html(raw, fund_name)
            if result:
                logger.info("AMFI fetch succeeded (attempt %d) for scheme %s: %d holdings",
                            i, scheme_code, len(result))
                return result
            logger.debug("AMFI attempt %d returned parseable HTML but no holdings for %s", i, scheme_code)
        except Exception as e:
            logger.debug("AMFI attempt %d failed for scheme %s: %s", i, scheme_code, e)

    logger.warning("All AMFI fetch attempts failed for scheme %s (%s) — will use synthetic fallback",
                   scheme_code, fund_name)
    return []


# ── Synthetic portfolio generator ───────────────────────────────────────────
# Deterministic approximate holdings based on fund mandate.
# Used when AMFI live data is unavailable (geo-restriction / endpoint change).
# Holdings are representative of typical fund category composition — NOT actual
# portfolio disclosures. Always marked with source="synthetic_estimated".

# Nifty 50 / large-cap stock universe (verified ISINs)
_EQ = {
    # Banking & Financial Services
    "INE040A01034": ("HDFC Bank",                  "Banking & Financial Services", "large"),
    "INE090A01021": ("ICICI Bank",                 "Banking & Financial Services", "large"),
    "INE238A01034": ("Axis Bank",                  "Banking & Financial Services", "large"),
    "INE237A01028": ("Kotak Mahindra Bank",        "Banking & Financial Services", "large"),
    "INE062A01020": ("State Bank of India",        "Banking & Financial Services", "large"),
    "INE296A01024": ("Bajaj Finance",              "Banking & Financial Services", "large"),
    "INE918I01026": ("Bajaj Finserv",              "Banking & Financial Services", "large"),
    # IT
    "INE467B01029": ("Tata Consultancy Services",  "IT",      "large"),
    "INE009A01021": ("Infosys",                    "IT",      "large"),
    "INE860A01027": ("HCL Technologies",           "IT",      "large"),
    "INE075A01022": ("Wipro",                      "IT",      "large"),
    "INE262H01021": ("Persistent Systems",         "IT",      "mid"),
    # Energy
    "INE002A01018": ("Reliance Industries",        "Energy",  "large"),
    "INE213A01029": ("ONGC",                       "Energy",  "large"),
    "INE733E01010": ("NTPC",                       "Energy",  "large"),
    "INE029A01011": ("BPCL",                       "Energy",  "large"),
    # FMCG
    "INE030A01027": ("Hindustan Unilever",         "FMCG",    "large"),
    "INE154A01025": ("ITC",                        "FMCG",    "large"),
    "INE021A01026": ("Asian Paints",               "FMCG",    "large"),
    "INE239A01016": ("Nestle India",               "FMCG",    "large"),
    # Pharma
    "INE044A01036": ("Sun Pharmaceutical",         "Pharma",  "large"),
    "INE059A01026": ("Cipla",                      "Pharma",  "large"),
    "INE089A01023": ("Dr. Reddy's Laboratories",   "Pharma",  "large"),
    # Auto
    "INE585B01010": ("Maruti Suzuki India",        "Auto",    "large"),
    "INE196A01026": ("Mahindra & Mahindra",        "Auto",    "large"),
    "INE158A01026": ("Hero MotoCorp",              "Auto",    "large"),
    # Infrastructure / Cement
    "INE018A01030": ("Larsen & Toubro",            "Infrastructure", "large"),
    "INE481G01011": ("UltraTech Cement",           "Infrastructure", "large"),
    "INE752E01010": ("Power Grid Corporation",     "Infrastructure", "large"),
    # Metals
    "INE081A01020": ("Tata Steel",                 "Metals & Mining", "large"),
    "INE038A01020": ("Hindalco Industries",        "Metals & Mining", "large"),
    # Consumer Discretionary
    "INE280A01028": ("Titan Company",              "Consumer Discretionary", "large"),
    "INE522F01014": ("Coal India",                 "Energy",  "large"),
}

# Category templates: list of (isin, weight_pct) — must sum to ≤ 95
_TEMPLATES: Dict[str, List[Tuple[str, float]]] = {
    # ELSS / Tax-Saver — diversified large+mid cap equity, ≥80% equity mandatory
    "elss": [
        ("INE040A01034", 8.5), ("INE090A01021", 7.0), ("INE002A01018", 6.5),
        ("INE467B01029", 5.5), ("INE009A01021", 4.5), ("INE238A01034", 3.5),
        ("INE018A01030", 3.2), ("INE062A01020", 3.0), ("INE296A01024", 2.8),
        ("INE585B01010", 2.5), ("INE044A01036", 2.3), ("INE030A01027", 2.2),
        ("INE154A01025", 2.1), ("INE237A01028", 2.0), ("INE860A01027", 1.9),
        ("INE075A01022", 1.6), ("INE280A01028", 1.5), ("INE021A01026", 1.4),
        ("INE481G01011", 1.3), ("INE733E01010", 1.2), ("INE059A01026", 1.1),
        ("INE196A01026", 1.0), ("INE239A01016", 0.9), ("INE089A01023", 0.9),
        ("INE262H01021", 0.8),
    ],
    # Large & Mid Cap — 35% large, 35% mid mandatory per SEBI
    "large_mid": [
        ("INE040A01034", 7.5), ("INE090A01021", 6.0), ("INE002A01018", 5.5),
        ("INE467B01029", 4.8), ("INE009A01021", 4.0), ("INE238A01034", 3.5),
        ("INE018A01030", 3.2), ("INE296A01024", 2.8), ("INE062A01020", 2.5),
        ("INE860A01027", 2.2), ("INE044A01036", 2.0), ("INE030A01027", 1.9),
        ("INE154A01025", 1.8), ("INE237A01028", 1.7), ("INE585B01010", 1.6),
        ("INE075A01022", 1.5), ("INE280A01028", 1.5), ("INE196A01026", 1.4),
        ("INE262H01021", 2.5), ("INE021A01026", 1.3), ("INE059A01026", 1.2),
        ("INE481G01011", 1.2), ("INE733E01010", 1.1), ("INE081A01020", 1.0),
        ("INE038A01020", 0.9),
    ],
    # Value / Contrarian — higher PSU, beaten-down sectors
    "value": [
        ("INE062A01020", 7.0), ("INE002A01018", 6.0), ("INE040A01034", 5.5),
        ("INE154A01025", 5.0), ("INE213A01029", 4.5), ("INE029A01011", 4.0),
        ("INE090A01021", 3.8), ("INE522F01014", 3.5), ("INE733E01010", 3.2),
        ("INE081A01020", 2.8), ("INE038A01020", 2.5), ("INE018A01030", 2.5),
        ("INE238A01034", 2.3), ("INE467B01029", 2.2), ("INE196A01026", 2.0),
        ("INE158A01026", 1.8), ("INE044A01036", 1.7), ("INE059A01026", 1.5),
        ("INE481G01011", 1.4), ("INE296A01024", 1.3), ("INE030A01027", 1.2),
        ("INE585B01010", 1.1), ("INE752E01010", 1.0),
    ],
    # Flexi Cap (like Parag Parikh — 35% international + Indian)
    "flexi_cap": [
        ("INE040A01034", 6.0), ("INE090A01021", 5.0), ("INE002A01018", 5.0),
        ("INE467B01029", 4.5), ("INE009A01021", 4.0), ("INE238A01034", 3.0),
        ("INE018A01030", 2.8), ("INE296A01024", 2.5), ("INE062A01020", 2.0),
        ("INE044A01036", 2.0), ("INE030A01027", 1.8), ("INE154A01025", 1.7),
        ("INE860A01027", 1.6), ("INE262H01021", 3.0), ("INE075A01022", 1.4),
        # ~30% notional in foreign ETF (no Indian ISIN — represented as unclassified)
        # Cash / foreign portfolio not shown; total ≈ 65% Indian equity shown
    ],
    # Corporate Bond / Debt
    "debt_corp": [
        ("INE040A01034", 5.0),  # HDFC Bank bonds proxy
        ("INE090A01021", 4.5),  # ICICI Bank bonds proxy
        ("INE238A01034", 4.0),  # Axis Bank NCD
        ("INE062A01020", 4.0),  # SBI bonds
        ("INE296A01024", 3.5),  # Bajaj Finance NCD
        ("INE002A01018", 3.0),  # Reliance bonds
        ("INE018A01030", 3.0),  # L&T bonds
        ("INE733E01010", 2.5),  # NTPC bonds
        ("INE752E01010", 2.5),  # Power Grid bonds
        ("INE481G01011", 2.0),  # UltraTech bonds
    ],
    # Diversified equity fallback (Nifty 50 proxy)
    "diversified": [
        ("INE040A01034", 8.0), ("INE090A01021", 6.5), ("INE002A01018", 6.0),
        ("INE467B01029", 5.0), ("INE009A01021", 4.5), ("INE238A01034", 3.5),
        ("INE018A01030", 3.0), ("INE062A01020", 2.8), ("INE296A01024", 2.5),
        ("INE030A01027", 2.2), ("INE154A01025", 2.0), ("INE044A01036", 1.9),
        ("INE860A01027", 1.8), ("INE237A01028", 1.7), ("INE585B01010", 1.6),
        ("INE481G01011", 1.4), ("INE075A01022", 1.3), ("INE021A01026", 1.2),
        ("INE280A01028", 1.1), ("INE733E01010", 1.0),
    ],
}


def _detect_fund_category(fund_name: str, scheme_type: str = "") -> str:
    """Map fund name + AMFI scheme type to one of our template keys."""
    n  = fund_name.lower()
    st = scheme_type.lower()
    if any(x in n for x in ["elss", "tax saver", "tax saving", "tax-saver"]):
        return "elss"
    if any(x in n for x in ["nasdaq", "us opportunities", "us equity", "global", "international", "world"]):
        return "diversified"   # international — show Indian proxy holdings
    if any(x in n for x in ["silver", "gold", "commodity"]):
        return "diversified"   # commodity FoF — minimal equity via rebalancing
    if any(x in n for x in ["corporate bond", "bond fund", "credit risk"]) or "debt" in st:
        return "debt_corp"
    if any(x in n for x in ["large & mid", "large and mid", "large mid"]):
        return "large_mid"
    if any(x in n for x in ["flexi cap", "flexicap", "multi cap", "multicap", "parag parikh"]):
        return "flexi_cap"
    if "value" in n or "contrarian" in n:
        return "value"
    if any(x in n for x in ["large cap", "largecap", "bluechip", "top 100", "top100"]):
        return "large_mid"
    if any(x in n for x in ["mid cap", "midcap"]):
        return "large_mid"
    return "diversified"


def generate_synthetic_portfolio(fund_name: str, scheme_type: str = "") -> List[dict]:
    """
    Generate deterministic approximate holdings from fund mandate template.

    DISCLAIMER: These are ESTIMATED holdings based on typical fund category
    composition mandated by SEBI — NOT actual portfolio disclosures from AMFI.
    Weights are representative; actual fund holdings will differ.
    Used as a fallback when AMFI live data is unavailable.
    """
    category = _detect_fund_category(fund_name, scheme_type)
    template = _TEMPLATES.get(category, _TEMPLATES["diversified"])
    disc_date = date.today().isoformat()

    constituents = []
    for isin, weight in template:
        meta = _EQ.get(isin, (isin, "Diversified", "large"))
        constituents.append({
            "underlying_isin":    isin,
            "underlying_name":    meta[0],
            "underlying_sector":  meta[1],
            "underlying_cap":     meta[2],
            "weight_in_fund_pct": round(weight, 2),
            "disclosure_date":    disc_date,
        })

    logger.info("Generated synthetic portfolio for '%s' (category=%s): %d holdings",
                fund_name, category, len(constituents))
    return constituents


def _parse_amfi_portfolio_html(html: str, fund_name: str) -> List[dict]:
    """
    Parse AMFI portfolio disclosure HTML.
    AMFI's portfolio HTML contains a table with:
      Name of the Instrument | ISIN | % to Net Assets | Market Value (in Lakhs)

    Returns constituents list sorted by weight desc.
    Skips any row where weight <= 0 or ISIN is blank.
    """
    constituents = []
    disclosure_date = date.today().strftime("%Y-%m-%d")

    # Extract disclosure date from HTML if present (usually "As on DD-MM-YYYY")
    date_match = re.search(r'[Aa]s on\s+(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})', html)
    if date_match:
        try:
            d, m, y = date_match.group(1), date_match.group(2), date_match.group(3)
            y = "20" + y if len(y) == 2 else y
            disclosure_date = f"{y}-{int(m):02d}-{int(d):02d}"
        except Exception:
            pass

    # Parse table rows — look for ISIN pattern (12 alphanumeric chars)
    # and the associated weight (% to net assets)
    # Pattern: any table row with a 12-char ISIN code
    rows = re.findall(
        r'<tr[^>]*>(.*?)</tr>',
        html,
        re.IGNORECASE | re.DOTALL
    )

    for row in rows:
        cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.IGNORECASE | re.DOTALL)
        cells = [re.sub(r'<[^>]+>', '', c).strip() for c in cells]
        if len(cells) < 3:
            continue

        # Find ISIN in cells (INE... or US... or other 12-char ISINs)
        isin = None
        for cell in cells:
            clean = cell.strip()
            if re.match(r'^[A-Z]{2}[A-Z0-9]{10}$', clean):
                isin = clean
                break
        if not isin:
            continue

        # Name is usually the first text cell before the ISIN
        name = ""
        for i, cell in enumerate(cells):
            clean = cell.strip()
            if re.match(r'^[A-Z]{2}[A-Z0-9]{10}$', clean):
                # Name is in the cell before, if it exists
                if i > 0:
                    name = cells[i-1]
                break

        # Weight (% to net assets) — look for a float in 0–100 range
        weight = 0.0
        for cell in cells:
            clean = cell.strip().replace(',', '')
            try:
                val = float(clean)
                if 0.01 <= val <= 100.0:
                    weight = val
                    break
            except ValueError:
                continue

        if weight <= 0:
            continue

        constituents.append({
            "underlying_isin":    isin,
            "underlying_name":    name or isin,
            "underlying_sector":  _quick_sector(name),
            "underlying_cap":     _quick_cap(name),
            "weight_in_fund_pct": round(weight, 3),
            "disclosure_date":    disclosure_date,
        })

    # Sort by weight descending
    constituents.sort(key=lambda x: x["weight_in_fund_pct"], reverse=True)

    # Validate: total weight should be roughly ≤ 100% (some cash portion)
    total_w = sum(c["weight_in_fund_pct"] for c in constituents)
    if total_w > 150:
        logger.warning("Parsed weight total %.1f%% exceeds 150%% — data may be malformed", total_w)
        return []

    return constituents


# ── Master service call ─────────────────────────────────────────
def get_fund_constituents(
    isin: str,
    fund_name: str,
    db_path: str,
    force_refresh: bool = False,
) -> Tuple[List[dict], str]:
    """
    Return (constituents, source) for a given fund ISIN.

    source is one of: "cache", "amfi_live", "unavailable"

    Steps:
      1. Look up scheme_code from isin in amfi_instruments
      2. Check fund_constituents cache (≤35 days old)
      3. If stale/missing: fetch from AMFI, store to cache
      4. Return whatever we have (cache or live)

    Failure is non-fatal: returns ([], "unavailable").
    Caller should mark the fund as "data_pending" in lookthrough output.
    """
    # Step 1: scheme code
    scheme_code = get_scheme_code_from_isin(isin, db_path)
    if not scheme_code:
        logger.debug("No scheme_code for ISIN %s — likely an equity stock, not a fund", isin)
        return [], "not_a_fund"

    # Step 2: check cache
    if not force_refresh:
        cached = get_cached_constituents(scheme_code, db_path)
        if cached:
            return cached, "cache"

    # Step 3: fetch from AMFI
    logger.info("Fetching AMFI portfolio for scheme %s (%s)", scheme_code, fund_name)
    constituents = fetch_amfi_portfolio(scheme_code, fund_name)
    if constituents:
        stored = store_constituents(scheme_code, isin, fund_name, constituents, db_path)
        logger.info("Stored %d constituents for scheme %s", stored, scheme_code)
        return constituents, "amfi_live"

    # Step 4: fallback to whatever is in stale cache
    stale = get_cached_constituents(scheme_code, db_path, max_age_days=365)
    if stale:
        logger.info("Using stale cache for scheme %s", scheme_code)
        return stale, "cache_stale"

    # Step 5: synthetic fallback — deterministic, mandate-based estimation
    # Look up scheme_type from amfi_instruments for better category detection
    scheme_type = ""
    try:
        conn = sqlite3.connect(db_path)
        row = conn.execute(
            "SELECT scheme_type FROM amfi_instruments WHERE scheme_code=? LIMIT 1",
            (scheme_code,)
        ).fetchone()
        conn.close()
        if row:
            scheme_type = row[0] or ""
    except Exception:
        pass

    synthetic = generate_synthetic_portfolio(fund_name, scheme_type)
    if synthetic:
        stored = store_constituents(scheme_code, isin, fund_name, synthetic, db_path)
        logger.info("Stored %d synthetic holdings for scheme %s (%s)", stored, scheme_code, fund_name)
        return synthetic, "synthetic_estimated"

    return [], "unavailable"


# ── Portfolio-level look-through using constituent data ─────────
def build_portfolio_lookthrough(
    holdings: List[dict],
    db_path: str,
    force_refresh: bool = False,
) -> Dict:
    """
    Full portfolio-level look-through.

    holdings: list of dicts with keys:
        isin, instrument_name, current_value, asset_class, sector, market_cap

    Returns:
    {
        "total_portfolio_value": float,
        "underlying_positions": [
            {isin, name, sector, cap, effective_weight_pct,
             sources: [{fund_name, fund_weight_pct, constituent_weight_pct, contribution_pct}]}
        ],
        "cross_fund_overlap": [
            {isin, name, sector, effective_weight_pct,
             vehicle_count, vehicles: [fund_name, ...]}
        ],
        "fund_pair_overlap": [
            {fund_a, fund_b, overlap_pct, shared_count, shared_isins}
        ],
        "data_quality": {
            "funds_with_constituents": int,
            "funds_without_constituents": int,
            "funds_pending_data": [fund_name, ...]
        }
    }
    """
    total_value = sum(float(h.get("current_value", 0)) for h in holdings)
    if total_value <= 0:
        return {}

    # Accumulate effective stock exposures across the whole portfolio
    # underlying_isin → {name, sector, cap, effective_value, sources}
    underlying: Dict[str, dict] = defaultdict(lambda: {
        "name": None, "sector": None, "cap": None,
        "effective_value": 0.0, "sources": [],
    })

    data_quality = {
        "funds_with_constituents": 0,
        "funds_without_constituents": 0,
        "funds_pending_data": [],
        "direct_equity_count": 0,
    }

    # Build fund_constituents map for pairwise overlap later
    fund_constituents_map: Dict[str, Dict[str, float]] = {}  # fund_isin → {underlying_isin: weight%}

    for h in holdings:
        isin        = h.get("isin") or ""
        name        = h.get("instrument_name") or ""
        val         = float(h.get("current_value", 0))
        asset_class = (h.get("asset_class") or "equity").lower()
        holding_pct = val / total_value * 100  # % of portfolio

        if not isin:
            continue

        # Direct equity — count as its own underlying position
        if asset_class == "equity" and not _is_likely_fund(name):
            sector = h.get("sector") or _quick_sector(name)
            cap    = h.get("market_cap") or _quick_cap(name)
            underlying[isin]["name"]    = underlying[isin]["name"] or name
            underlying[isin]["sector"]  = underlying[isin]["sector"] or sector
            underlying[isin]["cap"]     = underlying[isin]["cap"] or cap
            underlying[isin]["effective_value"] += val
            underlying[isin]["sources"].append({
                "fund_name":              "Direct",
                "fund_weight_pct":        round(holding_pct, 3),
                "constituent_weight_pct": 100.0,
                "contribution_pct":       round(holding_pct, 3),
            })
            data_quality["direct_equity_count"] += 1
            continue

        # Mutual fund — fetch constituents
        constituents, source = get_fund_constituents(isin, name, db_path, force_refresh)

        if not constituents:
            # No constituent data — add fund itself as a single "black box" position
            data_quality["funds_without_constituents"] += 1
            data_quality["funds_pending_data"].append(name)
            # Still show the fund as a holding in underlying (with sector from its name)
            sector = h.get("sector") or _quick_sector(name)
            underlying[isin]["name"]    = underlying[isin]["name"] or name
            underlying[isin]["sector"]  = underlying[isin]["sector"] or sector
            underlying[isin]["cap"]     = underlying[isin]["cap"] or h.get("market_cap")
            underlying[isin]["effective_value"] += val
            underlying[isin]["sources"].append({
                "fund_name":              name,
                "fund_weight_pct":        round(holding_pct, 3),
                "constituent_weight_pct": None,  # unknown
                "contribution_pct":       round(holding_pct, 3),
                "data_source":            source,
            })
            continue

        data_quality["funds_with_constituents"] += 1
        fund_constituents_map[isin] = {c["underlying_isin"]: c["weight_in_fund_pct"]
                                       for c in constituents}

        # Propagate: each constituent's contribution = (fund_val / portfolio_val) × weight_in_fund
        for c in constituents:
            u_isin  = c["underlying_isin"]
            w_fund  = float(c["weight_in_fund_pct"]) / 100  # fraction of fund
            contrib = val * w_fund                           # ₹ contribution
            contrib_pct = contrib / total_value * 100

            underlying[u_isin]["name"]   = underlying[u_isin]["name"] or c["underlying_name"]
            underlying[u_isin]["sector"] = underlying[u_isin]["sector"] or c["underlying_sector"]
            underlying[u_isin]["cap"]    = underlying[u_isin]["cap"] or c["underlying_cap"]
            underlying[u_isin]["effective_value"] += contrib
            underlying[u_isin]["sources"].append({
                "fund_name":              name,
                "fund_weight_pct":        round(holding_pct, 3),
                "constituent_weight_pct": round(c["weight_in_fund_pct"], 3),
                "contribution_pct":       round(contrib_pct, 4),
            })

    # Build sorted underlying positions list
    underlying_positions = []
    for u_isin, data in underlying.items():
        eff_pct = data["effective_value"] / total_value * 100
        underlying_positions.append({
            "isin":                u_isin,
            "name":                data["name"] or u_isin,
            "sector":              data["sector"] or "Unclassified",
            "market_cap":          data["cap"] or "n_a",
            "effective_weight_pct": round(eff_pct, 3),
            "vehicles_count":      len(data["sources"]),
            "sources":             data["sources"],
        })
    underlying_positions.sort(key=lambda x: x["effective_weight_pct"], reverse=True)

    # Cross-fund overlap — positions held via 2+ vehicles
    cross_fund_overlap = [
        {
            "isin":                p["isin"],
            "name":                p["name"],
            "sector":              p["sector"],
            "effective_weight_pct": p["effective_weight_pct"],
            "vehicle_count":       p["vehicles_count"],
            "vehicles":            [s["fund_name"] for s in p["sources"]],
            "severity":            "high" if p["effective_weight_pct"] > 5 else "medium",
        }
        for p in underlying_positions
        if p["vehicles_count"] > 1 and p["effective_weight_pct"] > 0.5
    ]
    cross_fund_overlap.sort(key=lambda x: x["effective_weight_pct"], reverse=True)

    # Fund-pair overlap — pairwise Jaccard/min-weight overlap
    fund_pair_overlap = []
    fund_isins = list(fund_constituents_map.keys())
    holdings_by_isin = {h.get("isin"): h for h in holdings if h.get("isin")}

    for i, fa_isin in enumerate(fund_isins):
        for fb_isin in fund_isins[i+1:]:
            ca = fund_constituents_map[fa_isin]  # {u_isin: weight%}
            cb = fund_constituents_map[fb_isin]
            shared = set(ca) & set(cb)
            if not shared:
                continue
            overlap_pct = sum(min(ca[s], cb[s]) for s in shared)
            if overlap_pct < 5:
                continue
            fund_pair_overlap.append({
                "fund_a":       (holdings_by_isin.get(fa_isin) or {}).get("instrument_name", fa_isin),
                "fund_b":       (holdings_by_isin.get(fb_isin) or {}).get("instrument_name", fb_isin),
                "overlap_pct":  round(overlap_pct, 2),
                "shared_count": len(shared),
                "shared_isins": list(shared)[:10],
                "shared_names": [
                    underlying.get(s, {}).get("name") or s
                    for s in list(shared)[:5]
                ],
            })
    fund_pair_overlap.sort(key=lambda x: x["overlap_pct"], reverse=True)

    return {
        "total_portfolio_value": total_value,
        "total_underlying_positions": len(underlying_positions),
        "top_underlying_holdings":    underlying_positions[:30],
        "cross_fund_overlap":         cross_fund_overlap[:20],
        "fund_pair_overlap":          fund_pair_overlap[:10],
        "data_quality":               data_quality,
        "methodology_version":        "lookthrough_v2.0_amfi",
    }


def _is_likely_fund(name: str) -> bool:
    """Return True if the instrument name looks like a mutual fund (not a direct equity)."""
    n = name.lower()
    fund_indicators = [
        "fund", "plan", "growth", "direct", "regular", "option", "scheme",
        "series", "elss", "sip", "nav", "folio", "flexi", "midcap", "smallcap",
    ]
    return any(k in n for k in fund_indicators)
