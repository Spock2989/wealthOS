
from typing import List, Dict
from app.normalizer.canonical_schema import CanonicalHolding

def run(holdings: List[CanonicalHolding], total: float) -> Dict:
    liquid = semi = illiquid = 0.0
    for h in holdings:
        ac = h.asset_class
        if ac in ("cash",): liquid += h.current_value
        elif ac in ("equity", "debt"): liquid += h.current_value
        elif ac in ("hybrid",): semi += h.current_value
        elif ac in ("alternate",): illiquid += h.current_value
        else: semi += h.current_value
    def pct(v): return round(v / total * 100, 2) if total else 0
    return {"liquid_pct": pct(liquid), "semi_liquid_pct": pct(semi),
            "illiquid_pct": pct(illiquid), "liquid_inr": round(liquid, 2),
            "t_plus_1_redeemable_pct": pct(liquid),
            "note": "Liquid = equity MF + debt MF + cash. Semi = hybrid. Illiquid = alternates/REITs."}
