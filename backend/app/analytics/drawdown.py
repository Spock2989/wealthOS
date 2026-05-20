
from typing import List, Dict
from app.normalizer.canonical_schema import CanonicalHolding

HISTORICAL = {
    "2008_global_financial_crisis": {"equity":{"large_cap":-55,"mid_cap":-65,"small_cap":-75,"n_a":-60},"debt":{"n_a":-5},"hybrid":{"n_a":-35},"cash":{"n_a":2},"international":{"n_a":-50},"alternate":{"n_a":-20}},
    "2020_covid_crash":             {"equity":{"large_cap":-38,"mid_cap":-45,"small_cap":-50,"n_a":-40},"debt":{"n_a":-3},"hybrid":{"n_a":-22},"cash":{"n_a":1},"international":{"n_a":-35},"alternate":{"n_a":-15}},
    "2015_china_slowdown":          {"equity":{"large_cap":-22,"mid_cap":-30,"small_cap":-38,"n_a":-25},"debt":{"n_a":-1},"hybrid":{"n_a":-12},"cash":{"n_a":1},"international":{"n_a":-18},"alternate":{"n_a":-8}},
}

def run(holdings: List[CanonicalHolding], total: float) -> Dict:
    scenarios = {}
    for sc_name, shocks in HISTORICAL.items():
        impact = sum(h.current_value * (shocks.get(h.asset_class, {}).get(h.market_cap or "n_a", shocks.get(h.asset_class, {}).get("n_a", -20)) / 100) for h in holdings)
        scenarios[sc_name] = {"pct": round(impact / total * 100, 2) if total else 0, "inr": round(impact, 2)}
    worst = min(scenarios, key=lambda s: scenarios[s]["pct"])
    return {"scenarios": scenarios, "worst_case_drawdown_pct": scenarios[worst]["pct"],
            "worst_case_scenario": worst,
            "note": "Based on actual India market peak-to-trough drawdowns."}
