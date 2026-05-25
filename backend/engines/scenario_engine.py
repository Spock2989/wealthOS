from typing import Dict

SCENARIOS = [
    {
        "id": "market_crash_20", "name": "20% Market Crash",
        "sector_shocks": {
            "Banking & Financial Services": -0.22, "Technology": -0.20,
            "Healthcare": -0.12, "FMCG": -0.10, "Auto": -0.24,
            "Infrastructure": -0.26, "Energy": -0.18,
            "Fixed Income": -0.02, "Diversified": -0.20,
        },
        "small_cap_amplifier": -0.08, "horizon": "1-3 months", "severity": "critical",
    },
    {
        "id": "smallcap_correction_25", "name": "25% Small-Cap Correction",
        "sector_shocks": {
            "Banking & Financial Services": -0.08, "Technology": -0.10,
            "Healthcare": -0.06, "FMCG": -0.04, "Auto": -0.12,
            "Infrastructure": -0.14, "Energy": -0.08, "Fixed Income": 0.01,
        },
        "small_cap_amplifier": -0.18, "horizon": "1-6 months", "severity": "high",
    },
    {
        "id": "rbi_rate_hike_100bps", "name": "RBI Rate Hike 100bps",
        "sector_shocks": {
            "Banking & Financial Services": 0.05, "Technology": -0.04,
            "Healthcare": -0.02, "FMCG": -0.03, "Auto": -0.06,
            "Infrastructure": -0.09, "Real Estate": -0.12,
            "Energy": -0.02, "Fixed Income": -0.07,
        },
        "small_cap_amplifier": -0.02, "horizon": "3-6 months", "severity": "medium",
    },
    {
        "id": "oil_spike_30pct", "name": "Oil Price Spike +30%",
        "sector_shocks": {
            "Banking & Financial Services": -0.03, "Technology": -0.02,
            "FMCG": -0.06, "Auto": -0.09, "Infrastructure": -0.04,
            "Energy": 0.10, "Fixed Income": -0.02,
        },
        "small_cap_amplifier": -0.03, "horizon": "1-3 months", "severity": "medium",
    },
    {
        "id": "inr_depreciation_10pct", "name": "INR Depreciation 10%",
        "sector_shocks": {
            "Technology": 0.07, "Healthcare": 0.04,
            "Banking & Financial Services": -0.03, "FMCG": -0.04,
            "Auto": -0.05, "Infrastructure": -0.02,
            "Energy": -0.05, "Fixed Income": -0.03,
        },
        "small_cap_amplifier": -0.02, "horizon": "3-12 months", "severity": "medium",
    },
    {
        "id": "us_recession", "name": "US Recession",
        "sector_shocks": {
            "Technology": -0.16, "Banking & Financial Services": -0.07,
            "Healthcare": -0.05, "FMCG": -0.04, "Auto": -0.10,
            "Infrastructure": -0.06, "Energy": -0.08, "Fixed Income": 0.02,
        },
        "small_cap_amplifier": -0.05, "horizon": "6-18 months", "severity": "high",
    },
    {
        "id": "global_liquidity_crisis", "name": "Global Liquidity Crisis",
        "sector_shocks": {
            "Banking & Financial Services": -0.18, "Technology": -0.14,
            "Healthcare": -0.09, "FMCG": -0.08, "Auto": -0.16,
            "Infrastructure": -0.20, "Energy": -0.12, "Fixed Income": -0.05,
        },
        "small_cap_amplifier": -0.12, "horizon": "1-6 months", "severity": "critical",
    },
]

def run_scenarios(
    sector_exp: Dict[str, float],
    cap_split: Dict[str, float],
    total_value: float
) -> list:
    results = []
    small_pct = cap_split.get("small", 0) / 100

    for s in SCENARIOS:
        portfolio_impact = 0.0
        affected = []

        for sector, weight_pct in sector_exp.items():
            shock = s["sector_shocks"].get(sector, s["sector_shocks"].get("Diversified", -0.05))
            contribution    = (weight_pct / 100) * shock * 100
            portfolio_impact += contribution
            if abs(shock) >= 0.05:
                affected.append({
                    "sector":       sector,
                    "weight_pct":   round(weight_pct, 1),
                    "shock_pct":    round(shock * 100, 1),
                    "contribution": round(contribution, 2),
                })

        portfolio_impact += small_pct * s.get("small_cap_amplifier", 0) * 100
        affected.sort(key=lambda x: abs(x["contribution"]), reverse=True)

        results.append({
            "id":            s["id"],
            "name":          s["name"],
            "estimated_pct": round(portfolio_impact, 2),
            "estimated_inr": round(total_value * portfolio_impact / 100, 0),
            "severity":      s["severity"],
            "horizon":       s["horizon"],
            "affected":      affected[:5],
            "methodology":   "macro_sector_propagation_v1",
        })

    return results