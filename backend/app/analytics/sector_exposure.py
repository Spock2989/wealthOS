
from typing import List, Dict
from app.normalizer.canonical_schema import CanonicalHolding
from collections import defaultdict

def run(holdings: List[CanonicalHolding], total: float) -> Dict:
    by_sector = defaultdict(float)
    for h in holdings:
        sec = h.sector or "Unclassified"
        by_sector[sec] += h.current_value
    pct = dict(sorted({k: round(v/total*100, 2) for k, v in by_sector.items()}.items(), key=lambda x: -x[1]))
    top = max(pct, key=pct.get) if pct else None
    flags = [s for s, p in pct.items() if p > 30]
    return {"by_sector": pct, "top_sector": top, "concentration_flags": flags,
            "sector_count": len(pct)}
