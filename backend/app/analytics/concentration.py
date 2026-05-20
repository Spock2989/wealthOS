
from typing import List, Dict
from app.normalizer.canonical_schema import CanonicalHolding

def run(holdings: List[CanonicalHolding], total: float) -> Dict:
    if not holdings or not total:
        return {}
    sorted_h = sorted(holdings, key=lambda h: h.current_value, reverse=True)
    weights = [h.current_value / total * 100 for h in sorted_h]
    hhi = round(sum(w**2 for w in weights), 2)
    top3  = round(sum(weights[:3]),  2)
    top5  = round(sum(weights[:5]),  2)
    top10 = round(sum(weights[:10]), 2)
    if hhi < 1000: interp = "well_diversified"
    elif hhi < 1800: interp = "moderately_concentrated"
    else: interp = "highly_concentrated"
    return {"hhi": hhi, "hhi_interpretation": interp,
            "top3_weight_pct": top3, "top5_weight_pct": top5, "top10_weight_pct": top10,
            "largest_holding_name": sorted_h[0].instrument_name,
            "largest_holding_pct": round(weights[0], 2)}
