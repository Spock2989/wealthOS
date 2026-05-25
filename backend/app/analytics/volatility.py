
from typing import List, Dict
from app.normalizer.canonical_schema import CanonicalHolding

VOL = {"equity":{"large_cap":12.0,"mid_cap":18.0,"small_cap":24.0,"n_a":15.0},
       "debt":{"n_a":4.0},"hybrid":{"n_a":10.0},"cash":{"n_a":1.0},
       "international":{"n_a":16.0},"alternate":{"n_a":14.0}}
CORR = {"equity":{"equity":0.85,"debt":-0.1,"hybrid":0.6,"cash":0.0,"international":0.5,"alternate":0.3},
        "debt":{"debt":0.7,"hybrid":0.2,"cash":0.1,"international":0.0,"alternate":0.1},
        "hybrid":{"hybrid":0.75,"cash":0.05,"international":0.4,"alternate":0.25},
        "cash":{"cash":0.9,"international":0.0,"alternate":0.0},
        "international":{"international":0.8,"alternate":0.2},"alternate":{"alternate":0.7}}

def _vol(h):
    return VOL.get(h.asset_class, {}).get(h.market_cap or "n_a", VOL.get(h.asset_class, {}).get("n_a", 15.0))

def _corr(a, b):
    ac, bc = a.asset_class, b.asset_class
    return CORR.get(ac, {}).get(bc) or CORR.get(bc, {}).get(ac) or (0.5 if ac == bc else 0.1)

def run(holdings: List[CanonicalHolding], total: float) -> Dict:
    if not holdings or not total:
        return {}
    ws = [h.current_value / total for h in holdings]
    vs = [_vol(h) / 100 for h in holdings]
    var = sum(ws[i]**2 * vs[i]**2 for i in range(len(holdings)))
    for i in range(len(holdings)):
        for j in range(i+1, len(holdings)):
            var += 2 * ws[i] * ws[j] * vs[i] * vs[j] * _corr(holdings[i], holdings[j])
    vol = round((var**0.5) * 100, 2)
    if vol < 8: band = "Low"
    elif vol < 15: band = "Moderate"
    elif vol < 22: band = "High"
    else: band = "Very High"
    return {"estimated_annual_volatility_pct": vol, "volatility_band": band,
            "note": "Proxy estimate using asset-class parameters. Not based on historical NAV data."}
