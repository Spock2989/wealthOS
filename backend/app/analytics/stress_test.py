
from typing import List, Dict
from app.normalizer.canonical_schema import CanonicalHolding

SCENARIOS = [
    {"scenario":"india_recession","label":"India Growth Slowdown","description":"GDP contracts 2%, corporate earnings fall, FII outflows","shocks":{"equity":{"large_cap":-25,"mid_cap":-35,"small_cap":-45,"n_a":-30},"debt":{"n_a":3},"hybrid":{"n_a":-15},"cash":{"n_a":1},"international":{"n_a":-20},"alternate":{"n_a":-10}},"severity":"high"},
    {"scenario":"rate_hike_300bps","label":"RBI Rate Hike +300bps","description":"Aggressive rate tightening, bond yields spike, equity re-rating","shocks":{"equity":{"large_cap":-18,"mid_cap":-25,"small_cap":-30,"n_a":-20},"debt":{"n_a":-12},"hybrid":{"n_a":-14},"cash":{"n_a":2},"international":{"n_a":-15},"alternate":{"n_a":-8}},"severity":"moderate"},
    {"scenario":"fii_selloff","label":"FII Mass Selloff","description":"Foreign investors pull $20B from Indian markets in 3 months","shocks":{"equity":{"large_cap":-22,"mid_cap":-30,"small_cap":-35,"n_a":-25},"debt":{"n_a":-2},"hybrid":{"n_a":-13},"cash":{"n_a":0},"international":{"n_a":-18},"alternate":{"n_a":-5}},"severity":"high"},
    {"scenario":"stagflation","label":"Stagflation","description":"High inflation + low growth. RBI caught between rate hikes and growth support","shocks":{"equity":{"large_cap":-30,"mid_cap":-38,"small_cap":-45,"n_a":-33},"debt":{"n_a":-8},"hybrid":{"n_a":-20},"cash":{"n_a":0},"international":{"n_a":-25},"alternate":{"n_a":5}},"severity":"severe"},
    {"scenario":"credit_crisis","label":"NBFC / Credit Crisis","description":"Major NBFC default triggers credit freeze, financial stocks collapse","shocks":{"equity":{"large_cap":-20,"mid_cap":-32,"small_cap":-40,"n_a":-25},"debt":{"n_a":-6},"hybrid":{"n_a":-16},"cash":{"n_a":1},"international":{"n_a":-10},"alternate":{"n_a":-5}},"severity":"high"},
    {"scenario":"inr_depreciation","label":"INR Depreciation -20%","description":"Rupee weakens sharply, import costs spike, inflation surge","shocks":{"equity":{"large_cap":-15,"mid_cap":-20,"small_cap":-25,"n_a":-17},"debt":{"n_a":-5},"hybrid":{"n_a":-10},"cash":{"n_a":-3},"international":{"n_a":15},"alternate":{"n_a":8}},"severity":"moderate"},
    {"scenario":"geopolitical_shock","label":"Geopolitical Shock","description":"Regional conflict disrupts trade routes, oil spikes to $150","shocks":{"equity":{"large_cap":-20,"mid_cap":-28,"small_cap":-33,"n_a":-22},"debt":{"n_a":-4},"hybrid":{"n_a":-13},"cash":{"n_a":1},"international":{"n_a":-15},"alternate":{"n_a":12}},"severity":"high"},
    {"scenario":"equity_bull_run","label":"Equity Bull Run","description":"Strong earnings growth, FII inflows, Nifty rallies 40%","shocks":{"equity":{"large_cap":35,"mid_cap":45,"small_cap":55,"n_a":38},"debt":{"n_a":2},"hybrid":{"n_a":20},"cash":{"n_a":1},"international":{"n_a":25},"alternate":{"n_a":18}},"severity":"positive"},
]

def run(holdings: List[CanonicalHolding], total: float) -> Dict:
    results = []
    for sc in SCENARIOS:
        shocks = sc["shocks"]
        impact = 0.0
        top_impacted = []
        for h in holdings:
            shock_pct = shocks.get(h.asset_class, {}).get(h.market_cap or "n_a",
                        shocks.get(h.asset_class, {}).get("n_a", 0))
            holding_impact = h.current_value * shock_pct / 100
            impact += holding_impact
            top_impacted.append({"name": h.instrument_name, "shock_pct": shock_pct, "impact_inr": round(holding_impact, 2)})
        top_impacted.sort(key=lambda x: abs(x["impact_inr"]), reverse=True)
        pct_impact = round(impact / total * 100, 2) if total else 0
        results.append({**sc, "portfolio_impact_pct": pct_impact, "portfolio_impact_inr": round(impact, 2),
                        "post_stress_value_inr": round(total + impact, 2), "top_impacted_holdings": top_impacted[:5]})
    negative = [r for r in results if r["portfolio_impact_pct"] < 0]
    positive = [r for r in results if r["portfolio_impact_pct"] > 0]
    worst = min(negative, key=lambda r: r["portfolio_impact_pct"]) if negative else results[0]
    best  = max(positive, key=lambda r: r["portfolio_impact_pct"]) if positive else results[-1]
    avg_neg = sum(r["portfolio_impact_pct"] for r in negative) / len(negative) if negative else 0
    resilience = round(max(0, min(100, 100 + avg_neg * 2)), 1)
    if resilience >= 80: rgrade = "A"
    elif resilience >= 65: rgrade = "B"
    elif resilience >= 50: rgrade = "C"
    else: rgrade = "D"
    return {"scenarios": results,
            "summary": {"worst_scenario": worst["scenario"], "worst_impact_pct": worst["portfolio_impact_pct"],
                        "worst_impact_inr": worst["portfolio_impact_inr"],
                        "best_scenario": best["scenario"], "best_impact_pct": best["portfolio_impact_pct"],
                        "resilience_score": resilience, "resilience_grade": rgrade}}
