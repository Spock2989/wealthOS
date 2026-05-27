"""
CAMS/KFintech Consolidated Account Statement (CAS) PDF parser.
"""
from typing import List, Dict, Any
from app.parsers.base_parser import BaseParser
import re, io, logging

logger = logging.getLogger(__name__)

HOLDING_RE = re.compile(
    r'([0-9]+(?:/\d+)?)\s*'
    r'(IN[A-Z0-9]{10})\s+'
    r'(.+?)\s+'
    r'([\d,]+\.\d{3})\s+'
    r'([\d,]+\.\d{3})\s+'
    r'(\d{2}-[A-Za-z]{3}-\d{4})\s+'
    r'([\d,]+\.\d{2,4})\s+'
    r'([\d,]+\.\d{2})\s+'
    r'(CAMS|KFINTECH)'
)

def _clean_num(s): return float(s.replace(",",""))
def _clean_scheme_name(raw):
    cleaned = re.sub(r'^[A-Z0-9]+\s*-\s*', '', raw.strip())
    return cleaned.strip() or raw.strip()

class CASParser(BaseParser):
    def can_parse(self, content, filename): return filename.lower().endswith(".pdf")
    def parse(self, content):
        try:
            import pdfplumber
            with pdfplumber.open(io.BytesIO(content)) as pdf:
                full_text = "\n".join(page.extract_text() or "" for page in pdf.pages)
            h = self._parse_cams_cas(full_text)
            logger.info(f"CASParser: {len(h)} holdings")
            return h or self._parse_isin_scan(full_text)
        except Exception as e:
            logger.exception(f"CASParser failed: {e}"); return []

    def _parse_cams_cas(self, text):
        lines = text.splitlines()
        matched = [(i, HOLDING_RE.search(l)) for i, l in enumerate(lines) if HOLDING_RE.search(l)]
        if not matched: return []
        holdings, seen = [], set()
        holding_idxs = {i for i,_ in matched}
        for j,(line_idx,m) in enumerate(matched):
            folio,isin,scheme_raw,cost_s,units_s,nav_date,nav_s,mv_s,registrar = m.groups()
            key = f"{folio}|{isin}"
            if key in seen: continue
            seen.add(key)
            next_idx = matched[j+1][0] if j+1<len(matched) else len(lines)
            cont = []
            for k in range(line_idx+1, min(line_idx+4, next_idx)):
                l = lines[k].strip()
                if not l or l.startswith("Total") or l.startswith("Page") or l.startswith("7101") or l.startswith("Folio") or k in holding_idxs or re.search(r'IN[A-Z0-9]{10}',l): break
                cont.append(l)
            name = _clean_scheme_name(scheme_raw)
            if cont:
                name = re.sub(r'\s*\(Non-Demat\)\s*$','', name+" "+" ".join(cont)).strip()
                name = re.sub(r'\s*-\s*$','',name).strip()
            try:
                holdings.append({"instrument_name":name,"isin":isin,"folio_number":folio,
                    "quantity":_clean_num(units_s),"nav":_clean_num(nav_s),"nav_date":nav_date,
                    "cost_value":_clean_num(cost_s),"current_value":_clean_num(mv_s),
                    "registrar":registrar,"source_parser":"CASParser.v2",
                    "methodology_version":"cams_cas_v2","calculation_step":"raw_extraction"})
            except Exception as e: logger.warning(f"Parse error line {line_idx}: {e}")
        return holdings

    def _parse_isin_scan(self, text):
        holdings, isin_re, val_re = [], re.compile(r"(IN[A-Z0-9]{10})"), re.compile(r"(?:INR|Rs\.?|₹)\s*([\d,]+\.\d{2})")
        lines = text.splitlines()
        for i,line in enumerate(lines):
            im,vm = isin_re.search(line), val_re.search(line)
            if im and vm:
                try: holdings.append({"instrument_name":lines[i-1].strip() if i>0 else "Unknown","isin":im.group(1),"current_value":_clean_num(vm.group(1)),"source_parser":"CASParser.v2.fallback","methodology_version":"isin_scan_v1"})
                except: pass
        return holdings
