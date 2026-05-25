import re
from typing import List, Dict, Any

try:
    import fitz
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False

def parse_cas_pdf(filepath: str) -> List[Dict[str, Any]]:
    text = _extract_text(filepath)
    if not text:
        return []
    rta = _detect_rta(text)
    if rta == "cams":
        return _parse_cams(text)
    elif rta == "kfin":
        return _parse_kfin(text)
    return _parse_cams(text) or _parse_kfin(text)

def _extract_text(filepath: str) -> str:
    if PYMUPDF_AVAILABLE:
        doc = fitz.open(filepath)
        text = "\n".join(page.get_text() for page in doc)
        doc.close()
        return text
    raise RuntimeError("Install PyMuPDF: pip install pymupdf")

def _detect_rta(text: str) -> str:
    t = text.lower()
    if "computer age management" in t or "cams" in t[:500]:
        return "cams"
    if "kfintech" in t or "karvy" in t or "kfin" in t[:500]:
        return "kfin"
    return "unknown"

def _parse_cams(text: str) -> List[Dict[str, Any]]:
    holdings = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        fund_match = re.search(
            r"(HDFC|ICICI|SBI|Axis|Kotak|Nippon|Mirae|Parag|Motilal|Tata|UTI|DSP|Franklin|Aditya|PGIM|Invesco|Edelweiss|Sundaram|Quant|WhiteOak|PPFAS|360 ONE|Bandhan|Canara|Union|IDFC|BOI|LIC|Baroda)",
            line, re.IGNORECASE
        )
        if fund_match and "fund" in line.lower():
            fund_name = line
            scheme_name = ""
            folio = ""
            isin = ""
            units = nav = value = None
            j = i + 1
            while j < min(i + 25, len(lines)):
                l = lines[j].strip()
                if not scheme_name and l and not re.search(r"folio|pan:|mobile|email", l, re.IGNORECASE):
                    scheme_name = l
                isin_m = re.search(r"\bIN[A-Z0-9]{10}\b", l)
                if isin_m:
                    isin = isin_m.group(0)
                folio_m = re.search(r"folio\s*(?:no\.?)?[:.\s]*(\S+)", l, re.IGNORECASE)
                if folio_m:
                    folio = folio_m.group(1).strip("/")
                cb_m = re.search(
                    r"closing\s+balance\s*[:\-]?\s*([\d,]+\.?\d*)\s*[Uu]nits?(?:\s*[@x]\s*(?:₹|Rs\.?|INR)?\s*([\d,]+\.?\d*))?(?:\s*=\s*(?:₹|Rs\.?|INR)?\s*([\d,]+\.?\d*))?",
                    l, re.IGNORECASE
                )
                if cb_m:
                    units = float(cb_m.group(1).replace(",", "")) if cb_m.group(1) else None
                    nav   = float(cb_m.group(2).replace(",", "")) if cb_m.group(2) else None
                    value = float(cb_m.group(3).replace(",", "")) if cb_m.group(3) else None
                    if units and nav and not value:
                        value = units * nav
                    break
                j += 1
            if value and value > 0:
                holdings.append({
                    "name": scheme_name or fund_name,
                    "fund_house": fund_name,
                    "isin": isin or None,
                    "amfi_code": None,
                    "folio": folio,
                    "units": units,
                    "nav": nav,
                    "value": value,
                    "asset_class": _infer_asset_class(scheme_name or fund_name),
                    "source_rta": "cams",
                })
            i = j
        else:
            i += 1
    return holdings

def _parse_kfin(text: str) -> List[Dict[str, Any]]:
    holdings = []
    lines = text.splitlines()
    i = 0
    cb_pat  = re.compile(r"(?:closing\s+unit\s+balance|balance\s+units?)\s*[:\-]?\s*([\d,]+\.?\d*)", re.IGNORECASE)
    val_pat = re.compile(r"(?:market\s+value|current\s+value)\s*[:\-]?\s*(?:₹|Rs\.?)?\s*([\d,]+\.?\d*)", re.IGNORECASE)
    nav_pat = re.compile(r"(?:nav)\s*[:\-]?\s*(?:₹|Rs\.?)?\s*([\d,]+\.?\d*)", re.IGNORECASE)
    while i < len(lines):
        line = lines[i].strip()
        if re.search(r"mutual\s+fund|asset\s+management", line, re.IGNORECASE) and len(line) < 100:
            fund_name = line
            scheme_name = folio = isin = ""
            units = nav = value = None
            j = i + 1
            while j < min(i + 30, len(lines)):
                l = lines[j].strip()
                if not scheme_name and l and not re.search(r"folio|pan:|address", l, re.IGNORECASE):
                    scheme_name = l
                isin_m = re.search(r"\bIN[A-Z0-9]{10}\b", l)
                if isin_m:
                    isin = isin_m.group(0)
                folio_m = re.search(r"folio\s*(?:no\.?)?[:.\s]*(\S+)", l, re.IGNORECASE)
                if folio_m:
                    folio = folio_m.group(1).strip("/")
                cb_m = cb_pat.search(l)
                if cb_m:
                    units = float(cb_m.group(1).replace(",", ""))
                nav_m = nav_pat.search(l)
                if nav_m:
                    nav = float(nav_m.group(1).replace(",", ""))
                val_m = val_pat.search(l)
                if val_m:
                    value = float(val_m.group(1).replace(",", ""))
                    break
                j += 1
            if units and nav and not value:
                value = units * nav
            if value and value > 0:
                holdings.append({
                    "name": scheme_name or fund_name,
                    "fund_house": fund_name,
                    "isin": isin or None,
                    "amfi_code": None,
                    "folio": folio,
                    "units": units,
                    "nav": nav,
                    "value": value,
                    "asset_class": _infer_asset_class(scheme_name or fund_name),
                    "source_rta": "kfin",
                })
            i = j
        else:
            i += 1
    return holdings

def _infer_asset_class(name: str) -> str:
    s = name.lower()
    if any(k in s for k in ["debt","bond","liquid","overnight","gilt","money market","short duration","credit risk","corporate bond","floater","ultra short"]):
        return "debt"
    if any(k in s for k in ["hybrid","balanced","arbitrage","multi asset","equity savings"]):
        return "hybrid"
    if any(k in s for k in ["global","international","overseas","nasdaq"]):
        return "international"
    if any(k in s for k in ["etf","index fund","nifty","sensex"]):
        return "passive_equity"
    return "equity"