
from typing import List, Dict, Any
from app.parsers.base_parser import BaseParser
import io

class ExcelParser(BaseParser):
    def can_parse(self, content: bytes, filename: str) -> bool:
        return filename.lower().endswith((".xlsx", ".xls", ".csv"))

    def parse(self, content: bytes) -> List[Dict[str, Any]]:
        filename = getattr(content, "name", "file.csv")
        if isinstance(content, bytes):
            try:
                text = content.decode("utf-8", errors="ignore")
                return self._parse_csv(text)
            except:
                return self._parse_excel(content)
        return []

    def _parse_csv(self, text: str) -> List[Dict[str, Any]]:
        import csv
        reader = csv.DictReader(io.StringIO(text))
        results = []
        col_map = {"instrument_name":["instrument","fund","name","scheme","security"],
                   "isin":["isin"],"current_value":["value","amount","current","market value","nav value"],
                   "quantity":["quantity","units","shares"],"nav":["nav","price"],
                   "asset_class":["asset","class","type"],"sector":["sector"]}
        for row in reader:
            mapped = {}
            for target, aliases in col_map.items():
                for col in row:
                    if any(a in col.lower() for a in aliases):
                        val = row[col].strip().replace(",","").replace("₹","")
                        mapped[target] = val
                        break
            if mapped.get("instrument_name") and mapped.get("current_value"):
                try:
                    mapped["current_value"] = float(mapped["current_value"])
                    results.append(mapped)
                except:
                    pass
        return results

    def _parse_excel(self, content: bytes) -> List[Dict[str, Any]]:
        try:
            import openpyxl
            wb = openpyxl.load_workbook(io.BytesIO(content))
            ws = wb.active
            rows = list(ws.iter_rows(values_only=True))
            if not rows: return []
            headers = [str(h).lower() if h else "" for h in rows[0]]
            results = []
            for row in rows[1:]:
                d = dict(zip(headers, row))
                name = d.get("instrument") or d.get("fund") or d.get("name") or d.get("scheme")
                val  = d.get("value") or d.get("amount") or d.get("current value")
                if name and val:
                    try: results.append({"instrument_name": str(name), "current_value": float(str(val).replace(",",""))})
                    except: pass
            return results
        except:
            return []
