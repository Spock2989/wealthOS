"""
Deduplication: ISIN is primary key. Different ISINs = different instruments, never merged.
"""
from typing import List, Dict
from collections import defaultdict
from app.normalizer.canonical_schema import CanonicalHolding
import re

def _base_name(name):
    return re.sub(r'\s*[-–—(]\s*(growth|dividend|idcw|direct|regular|payout|reinvest|bonus|sweep|option|plan|gr|div|quarterly|monthly|annual)\b.*','',name.strip(),flags=re.IGNORECASE).strip().lower()

def deduplicate(holdings: List[CanonicalHolding]) -> List[CanonicalHolding]:
    isin_groups: Dict[str, List[CanonicalHolding]] = defaultdict(list)
    no_isin = []
    for h in holdings:
        (isin_groups[h.isin] if h.isin else no_isin).append(h)
    isin_by_base = {_base_name(h.instrument_name): h.isin for h in holdings if h.isin}
    for h in no_isin:
        ri = isin_by_base.get(_base_name(h.instrument_name))
        if ri:
            d = h.model_dump(); d["isin"] = ri; isin_groups[ri].append(CanonicalHolding(**d))
        else:
            isin_groups[f"__noISIN__{h.instrument_name}"].append(h)
    return [_merge(g) for g in isin_groups.values()]

def _merge(group: List[CanonicalHolding]) -> CanonicalHolding:
    if len(group) == 1: return group[0]
    total = sum(g.current_value for g in group)
    qty = sum(g.quantity or 0 for g in group) or None
    folios = [g.folio_number for g in group if g.folio_number]
    fs = f"Multiple ({len(folios)} folios)" if len(folios)>1 else (folios[0] if folios else None)
    b = group[0]
    return CanonicalHolding(instrument_name=b.instrument_name,isin=b.isin,folio_number=fs,
        asset_class=b.asset_class,sub_asset_class=b.sub_asset_class,sector=b.sector,
        market_cap=b.market_cap,geography=b.geography,quantity=qty,nav=b.nav,
        current_value=total,risk_score=b.risk_score,liquidity_score=b.liquidity_score)
