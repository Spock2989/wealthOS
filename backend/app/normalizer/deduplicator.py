
from typing import List, Dict
from collections import defaultdict
from app.normalizer.canonical_schema import CanonicalHolding
import re

def _base_name(name: str) -> str:
    cleaned = name.strip()
    pattern = r"\s*[-–—(]\s*(growth|dividend|idcw|direct|regular|payout|reinvest|bonus|sweep|option|plan|gr|div|quarterly|monthly|annual)\b.*"
    return re.sub(pattern, "", cleaned, flags=re.IGNORECASE).strip().lower()

def deduplicate(holdings: List[CanonicalHolding]) -> List[CanonicalHolding]:
    name_groups: Dict[str, List[CanonicalHolding]] = defaultdict(list)
    for h in holdings:
        name_groups[_base_name(h.instrument_name)].append(h)
    merged = []
    for group in name_groups.values():
        best_isin = next((h.isin for h in group if h.isin), None)
        resolved = []
        for h in group:
            if best_isin and not h.isin:
                d = h.model_dump(); d["isin"] = best_isin
                resolved.append(CanonicalHolding(**d))
            else:
                resolved.append(h)
        merged.append(_merge(resolved))
    return merged

def _merge(group: List[CanonicalHolding]) -> CanonicalHolding:
    if len(group) == 1:
        return group[0]
    total = sum(g.current_value for g in group)
    qty = sum(g.quantity or 0 for g in group) or None
    base = group[0]
    return CanonicalHolding(instrument_name=base.instrument_name, isin=base.isin,
        folio_number=f"Multiple ({len(group)} folios)", asset_class=base.asset_class,
        sub_asset_class=base.sub_asset_class, sector=base.sector, market_cap=base.market_cap,
        geography=base.geography, quantity=qty, nav=base.nav, current_value=total,
        risk_score=base.risk_score, liquidity_score=base.liquidity_score)
