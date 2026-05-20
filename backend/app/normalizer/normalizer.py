
from typing import List, Dict, Any
from app.normalizer.canonical_schema import CanonicalHolding
from app.normalizer.sector_mapper import classify_asset_class, classify_sector, classify_market_cap, get_risk_score, get_liquidity_score
from app.normalizer.deduplicator import deduplicate

class PortfolioNormalizer:
    def normalize(self, raw: List[Dict[str, Any]]) -> List[CanonicalHolding]:
        holdings = []
        for r in raw:
            name = str(r.get("instrument_name") or r.get("name") or r.get("fund_name") or "Unknown")
            value = float(r.get("current_value") or r.get("value") or r.get("amount") or 0)
            if value <= 0:
                continue
            ac = str(r.get("asset_class") or classify_asset_class(name))
            mc = str(r.get("market_cap") or classify_market_cap(name))
            sec = str(r.get("sector") or classify_sector(name))
            holdings.append(CanonicalHolding(
                instrument_name=name,
                isin=r.get("isin") or None,
                folio_number=r.get("folio_number") or None,
                asset_class=ac, sub_asset_class=r.get("sub_asset_class"),
                sector=sec, market_cap=mc,
                geography=r.get("geography") or "India",
                quantity=r.get("quantity") or None,
                nav=r.get("nav") or None,
                current_value=value,
                risk_score=get_risk_score(ac, mc),
                liquidity_score=get_liquidity_score(ac),
            ))
        return deduplicate(holdings)
