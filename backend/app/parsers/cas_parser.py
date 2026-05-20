
from typing import List, Dict, Any
from app.parsers.base_parser import BaseParser
import re

class CASParser(BaseParser):
    def can_parse(self, content: bytes, filename: str) -> bool:
        return filename.lower().endswith(".pdf")

    def parse(self, content: bytes) -> List[Dict[str, Any]]:
        try:
            import pdfplumber, io
            holdings = []
            with pdfplumber.open(io.BytesIO(content)) as pdf:
                full_text = "\n".join(page.extract_text() or "" for page in pdf.pages)
            holdings = self._parse_cas_text(full_text)
            if not holdings:
                holdings = self._parse_generic_pdf(full_text)
            return holdings
        except Exception as e:
            return []

    def _parse_cas_text(self, text: str) -> List[Dict[str, Any]]:
        holdings = []
        folio_pattern = re.compile(r"Folio No[:\.\s]+(\S+)", re.IGNORECASE)
        scheme_pattern = re.compile(r"([A-Z][\w\s&\-]+(?:Fund|ETF|FoF|Plan)[\w\s\-]*)\s*(?:ISIN[:\s]*(IN\w{10}))?", re.IGNORECASE)
        value_pattern  = re.compile(r"(?:Market Value|Current Value|Value)[:\s]+(?:INR|Rs\.?|₹)?\s*([\d,]+\.?\d*)", re.IGNORECASE)
        units_pattern  = re.compile(r"(?:Units?|Balance)[:\s]+([\d,]+\.?\d*)", re.IGNORECASE)

        current_folio = None
        for line in text.split("\n"):
            fm = folio_pattern.search(line)
            if fm: current_folio = fm.group(1)
            sm = scheme_pattern.search(line)
            vm = value_pattern.search(line)
            if sm and vm:
                try:
                    val = float(vm.group(1).replace(",",""))
                    um  = units_pattern.search(line)
                    holdings.append({
                        "instrument_name": sm.group(1).strip(),
                        "isin": sm.group(2) if sm.lastindex >= 2 and sm.group(2) else None,
                        "folio_number": current_folio,
                        "current_value": val,
                        "quantity": float(um.group(1).replace(",","")) if um else None,
                    })
                except: pass
        return holdings

    def _parse_generic_pdf(self, text: str) -> List[Dict[str, Any]]:
        holdings = []
        isin_re = re.compile(r"(IN[A-Z0-9]{10})")
        value_re = re.compile(r"(?:INR|Rs\.?|₹)\s*([\d,]+\.\d{2})")
        lines = text.split("\n")
        for i, line in enumerate(lines):
            isin_m = isin_re.search(line)
            val_m  = value_re.search(line)
            if isin_m and val_m:
                name = lines[i-1].strip() if i > 0 else "Unknown Fund"
                try:
                    holdings.append({
                        "instrument_name": name,
                        "isin": isin_m.group(1),
                        "current_value": float(val_m.group(1).replace(",","")),
                    })
                except: pass
        return holdings
