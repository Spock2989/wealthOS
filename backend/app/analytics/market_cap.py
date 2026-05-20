
from typing import List, Dict
from app.normalizer.canonical_schema import CanonicalHolding
from collections import defaultdict

def run(holdings: List[CanonicalHolding], total: float) -> Dict:
    equity_total = sum(h.current_value for h in holdings if h.asset_class == "equity")
    by_cap = defaultdict(float)
    for h in holdings:
        if h.asset_class == "equity":
            by_cap[h.market_cap or "n_a"] += h.current_value
    pct_of_equity   = {k: round(v/equity_total*100, 2) for k, v in by_cap.items()} if equity_total else {}
    pct_of_portfolio= {k: round(v/total*100, 2) for k, v in by_cap.items()} if total else {}
    return {"by_cap_pct_of_equity": pct_of_equity, "by_cap_pct_of_portfolio": pct_of_portfolio,
            "equity_total_inr": round(equity_total, 2)}
