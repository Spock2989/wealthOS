
from typing import List, Dict
from app.normalizer.canonical_schema import CanonicalHolding
from collections import defaultdict

def run(holdings: List[CanonicalHolding], total: float) -> Dict:
    by_class = defaultdict(float)
    for h in holdings:
        by_class[h.asset_class] += h.current_value
    pct = {k: round(v / total * 100, 2) for k, v in by_class.items()} if total else {}
    target = {"equity": 60.0, "debt": 30.0, "hybrid": 5.0, "cash": 5.0}
    drift = {k: round(pct.get(k, 0) - target.get(k, 0), 2) for k in set(list(pct.keys()) + list(target.keys()))}
    return {"by_class": pct, "by_class_inr": {k: round(v, 2) for k, v in by_class.items()},
            "drift_from_moderate": drift, "total_inr": round(total, 2)}
