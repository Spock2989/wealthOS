"""
WealthOS Scenario Simulation Engine
20 Institutional Scenarios + 11-Variable Macro Sensitivity Matrix
Indian market calibrated — Aladdin/Citadel grade.

References:
  - WealthOS Definitive Builder Document v4.0 — Sections 6.12, 6.13
  - WealthOS North Star Analytics — Part 14
  - BlackRock Aladdin scenario framework
"""

from typing import Dict, List, Optional
from datetime import datetime, timezone

# ════════════════════════════════════════════════════════════════
# 11-VARIABLE MACRO SENSITIVITY MATRIX (India-Calibrated)
# ════════════════════════════════════════════════════════════════

MACRO_SENSITIVITY = {
    "RBI_rate_hike_100bps": {
        "Banking & Financial Services": -0.15,
        "BFSI_insurance": +0.08,
        "Real Estate": -0.22,
        "Auto": -0.12,
        "Infrastructure": -0.18,
        "IT": -0.05,
        "FMCG": -0.04,
        "Pharma": -0.02,
        "Metals": -0.06,
        "Energy": -0.03,
        "Consumer Durables": -0.10,
        "Fixed Income": -0.07,
        "Telecom": -0.05,
        "Healthcare": -0.02,
    },
    "RBI_rate_cut_75bps": {
        "Banking & Financial Services": +0.12,
        "Real Estate": +0.18,
        "Infrastructure": +0.15,
        "Auto": +0.10,
        "Consumer Durables": +0.08,
        "FMCG": +0.04,
        "IT": +0.03,
        "Fixed Income": +0.06,
        "Pharma": +0.02,
        "Metals": +0.04,
        "Energy": +0.02,
        "Telecom": +0.04,
    },
    "oil_price_up_20pct": {
        "Aviation": -0.25,
        "Logistics": -0.15,
        "Energy": +0.30,
        "Paints & Chemicals": -0.12,
        "Auto": -0.10,
        "FMCG": -0.06,
        "Tyres": -0.08,
        "Fertilisers": -0.09,
        "Infrastructure": -0.05,
        "IT": -0.02,
        "Banking & Financial Services": -0.03,
        "Pharma": -0.04,
        "Fixed Income": -0.03,
        "Textiles": -0.06,
    },
    "oil_price_down_30pct": {
        "Aviation": +0.20,
        "Logistics": +0.12,
        "Energy": -0.25,
        "Paints & Chemicals": +0.10,
        "Auto": +0.08,
        "FMCG": +0.05,
        "Tyres": +0.07,
        "Fertilisers": +0.08,
        "Infrastructure": +0.04,
        "IT": +0.02,
        "Banking & Financial Services": +0.03,
        "Fixed Income": +0.02,
    },
    "INR_depreciation_10pct": {
        "IT": +0.15,
        "Pharma": +0.12,
        "Metals": +0.08,
        "Energy": -0.18,
        "Consumer Durables": -0.10,
        "Textiles": +0.06,
        "Banking & Financial Services": -0.03,
        "Auto": -0.05,
        "FMCG": -0.04,
        "Real Estate": -0.02,
        "Fixed Income": -0.05,
        "Chemicals": +0.04,
        "Telecom": -0.03,
    },
    "US_recession_moderate": {
        "IT": -0.25,
        "Metals": -0.20,
        "Pharma": -0.10,
        "Domestic Consumption": -0.05,
        "Banking & Financial Services": -0.07,
        "Real Estate": -0.08,
        "Auto": -0.10,
        "Fixed Income": +0.02,
        "Energy": -0.08,
        "FMCG": -0.04,
        "Infrastructure": -0.06,
        "Chemicals": -0.08,
    },
    "India_GDP_slowdown": {
        "Banking & Financial Services": -0.12,
        "Real Estate": -0.15,
        "Auto": -0.14,
        "Infrastructure": -0.10,
        "Consumer Durables": -0.12,
        "FMCG": -0.06,
        "IT": -0.05,
        "Metals": -0.08,
        "Pharma": -0.02,
        "Energy": -0.05,
        "Fixed Income": +0.04,
        "Telecom": -0.04,
    },
    "CPI_inflation_surge": {
        "Banking & Financial Services": -0.08,
        "Real Estate": -0.10,
        "Auto": -0.08,
        "Consumer Durables": -0.10,
        "FMCG": +0.04,
        "IT": -0.03,
        "Pharma": -0.02,
        "Infrastructure": -0.07,
        "Fixed Income": -0.10,
        "Energy": +0.03,
        "Agriculture": +0.08,
        "Telecom": -0.03,
    },
    "global_liquidity_crisis": {
        "Banking & Financial Services": -0.20,
        "Real Estate": -0.22,
        "IT": -0.15,
        "Metals": -0.20,
        "Infrastructure": -0.18,
        "Auto": -0.16,
        "Consumer Durables": -0.18,
        "FMCG": -0.08,
        "Pharma": -0.08,
        "Energy": -0.12,
        "Fixed Income": -0.05,
        "Telecom": -0.10,
    },
    "India_10Y_yield_up_50bps": {
        "Banking & Financial Services": -0.08,
        "Real Estate": -0.12,
        "Infrastructure": -0.10,
        "Fixed Income": -0.06,
        "Auto": -0.06,
        "Consumer Durables": -0.06,
        "IT": -0.03,
        "FMCG": -0.02,
        "Pharma": -0.01,
    },
    "VIX_spike_to_40": {
        "Banking & Financial Services": -0.15,
        "IT": -0.12,
        "Auto": -0.14,
        "Real Estate": -0.16,
        "Metals": -0.18,
        "Infrastructure": -0.14,
        "Consumer Durables": -0.15,
        "FMCG": -0.06,
        "Pharma": -0.06,
        "Energy": -0.10,
        "Fixed Income": +0.02,
    },
}

# ════════════════════════════════════════════════════════════════
# 20 STANDARD SCENARIOS
# ════════════════════════════════════════════════════════════════

SCENARIOS = [
    {
        "id": "market_crash_30",
        "name": "Market Crash −30%",
        "category": "equity",
        "macro_driver": "VIX_spike_to_40",
        "severity": "critical",
        "horizon": "1–3 months",
        "historical_analog": "COVID crash March 2020, GFC 2008",
        "sector_shocks": {
            "Banking & Financial Services": -0.30, "IT": -0.28, "Auto": -0.33,
            "Infrastructure": -0.35, "Real Estate": -0.38, "Metals": -0.35,
            "Consumer Durables": -0.30, "FMCG": -0.15, "Pharma": -0.12,
            "Energy": -0.25, "Fixed Income": -0.03, "Diversified": -0.28,
            "Telecom": -0.20, "Chemicals": -0.25,
        },
        "small_cap_amplifier": -0.12,
    },
    {
        "id": "smallcap_crash_45",
        "name": "Small-Cap Crash −45%",
        "category": "equity",
        "macro_driver": "global_liquidity_crisis",
        "severity": "critical",
        "horizon": "3–12 months",
        "historical_analog": "IL&FS crisis 2018, NBFC crisis",
        "sector_shocks": {
            "Banking & Financial Services": -0.12, "IT": -0.14, "Auto": -0.18,
            "Infrastructure": -0.20, "Real Estate": -0.22, "Metals": -0.20,
            "FMCG": -0.08, "Pharma": -0.08, "Energy": -0.12,
            "Fixed Income": 0.01, "Consumer Durables": -0.18, "Diversified": -0.15,
        },
        "small_cap_amplifier": -0.30,
    },
    {
        "id": "largecap_correction_20",
        "name": "Large-Cap Correction −20%",
        "category": "equity",
        "macro_driver": "US_recession_moderate",
        "severity": "high",
        "horizon": "2–6 months",
        "historical_analog": "2015–16 China slowdown sell-off",
        "sector_shocks": {
            "Banking & Financial Services": -0.22, "IT": -0.22, "Auto": -0.22,
            "Infrastructure": -0.24, "Real Estate": -0.26, "Metals": -0.24,
            "FMCG": -0.12, "Pharma": -0.10, "Energy": -0.18,
            "Fixed Income": -0.01, "Consumer Durables": -0.20, "Diversified": -0.20,
        },
        "small_cap_amplifier": -0.05,
    },
    {
        "id": "sector_rotation_it_bfsi",
        "name": "Sector Rotation: IT −15%, BFSI +5%",
        "category": "sector",
        "macro_driver": "US_recession_moderate",
        "severity": "medium",
        "horizon": "3–9 months",
        "historical_analog": "2022 rate hike cycle",
        "sector_shocks": {
            "IT": -0.15, "Banking & Financial Services": +0.05,
            "FMCG": +0.03, "Pharma": +0.02, "Infrastructure": -0.03,
            "Real Estate": -0.05, "Auto": -0.03, "Fixed Income": +0.02,
        },
        "small_cap_amplifier": -0.02,
    },
    {
        "id": "rbi_rate_hike_100bps",
        "name": "RBI Rate Hike +100bps",
        "category": "monetary",
        "macro_driver": "RBI_rate_hike_100bps",
        "severity": "medium",
        "horizon": "3–6 months",
        "historical_analog": "RBI 2022–23 rate hike cycle",
        "sector_shocks": MACRO_SENSITIVITY["RBI_rate_hike_100bps"],
        "small_cap_amplifier": -0.02,
    },
    {
        "id": "rbi_rate_cut_75bps",
        "name": "RBI Rate Cut −75bps",
        "category": "monetary",
        "macro_driver": "RBI_rate_cut_75bps",
        "severity": "low",
        "horizon": "3–6 months",
        "historical_analog": "RBI easing 2019–20, COVID accommodation",
        "sector_shocks": MACRO_SENSITIVITY["RBI_rate_cut_75bps"],
        "small_cap_amplifier": +0.03,
    },
    {
        "id": "oil_spike_40pct",
        "name": "Oil Price Spike +40%",
        "category": "commodity",
        "macro_driver": "oil_price_up_20pct",
        "severity": "high",
        "horizon": "1–3 months",
        "historical_analog": "Russia-Ukraine 2022, Gulf War",
        "sector_shocks": {
            "Aviation": -0.35, "Logistics": -0.22, "Energy": +0.35,
            "Paints & Chemicals": -0.18, "Auto": -0.15, "FMCG": -0.09,
            "Tyres": -0.12, "Fertilisers": -0.14, "Infrastructure": -0.08,
            "Banking & Financial Services": -0.04, "Pharma": -0.06,
            "Fixed Income": -0.04, "IT": -0.03,
        },
        "small_cap_amplifier": -0.04,
    },
    {
        "id": "oil_collapse_40pct",
        "name": "Oil Price Collapse −40%",
        "category": "commodity",
        "macro_driver": "oil_price_down_30pct",
        "severity": "medium",
        "horizon": "3–12 months",
        "historical_analog": "2014–15 oil price collapse",
        "sector_shocks": {
            "Aviation": +0.25, "Logistics": +0.18, "Energy": -0.32,
            "Paints & Chemicals": +0.14, "Auto": +0.10, "FMCG": +0.07,
            "Tyres": +0.10, "Fertilisers": +0.11, "Infrastructure": +0.06,
            "Banking & Financial Services": +0.04, "Fixed Income": +0.03,
        },
        "small_cap_amplifier": +0.02,
    },
    {
        "id": "inflation_surge_cpi_8pct",
        "name": "Inflation Surge (CPI 8%+)",
        "category": "macro",
        "macro_driver": "CPI_inflation_surge",
        "severity": "high",
        "horizon": "6–18 months",
        "historical_analog": "India 2013 inflation crisis",
        "sector_shocks": MACRO_SENSITIVITY["CPI_inflation_surge"],
        "small_cap_amplifier": -0.04,
    },
    {
        "id": "inr_depreciation_15pct",
        "name": "INR Depreciation −15%",
        "category": "macro",
        "macro_driver": "INR_depreciation_10pct",
        "severity": "high",
        "horizon": "3–12 months",
        "historical_analog": "INR crisis 2013, 2018",
        "sector_shocks": {
            "IT": +0.18, "Pharma": +0.14, "Metals": +0.10,
            "Energy": -0.22, "Consumer Durables": -0.14, "Textiles": +0.08,
            "Banking & Financial Services": -0.05, "Auto": -0.07,
            "FMCG": -0.06, "Real Estate": -0.04, "Fixed Income": -0.08,
        },
        "small_cap_amplifier": -0.03,
    },
    {
        "id": "us_recession_moderate",
        "name": "US Recession (Moderate)",
        "category": "global",
        "macro_driver": "US_recession_moderate",
        "severity": "high",
        "horizon": "6–18 months",
        "historical_analog": "2001 dotcom, 2008 GFC",
        "sector_shocks": MACRO_SENSITIVITY["US_recession_moderate"],
        "small_cap_amplifier": -0.05,
    },
    {
        "id": "global_liquidity_crisis",
        "name": "Global Liquidity Crisis",
        "category": "global",
        "macro_driver": "global_liquidity_crisis",
        "severity": "critical",
        "horizon": "1–6 months",
        "historical_analog": "Lehman 2008, COVID March 2020",
        "sector_shocks": MACRO_SENSITIVITY["global_liquidity_crisis"],
        "small_cap_amplifier": -0.15,
    },
    {
        "id": "china_slowdown",
        "name": "China Slowdown Impact",
        "category": "global",
        "macro_driver": "India_GDP_slowdown",
        "severity": "medium",
        "horizon": "6–24 months",
        "historical_analog": "2015–16 China hard landing fears",
        "sector_shocks": {
            "Metals": -0.22, "Energy": -0.10, "IT": -0.08,
            "Chemicals": -0.10, "Pharma": -0.05,
            "Banking & Financial Services": -0.07, "Infrastructure": -0.08,
            "Auto": -0.08, "FMCG": -0.03, "Fixed Income": +0.02,
        },
        "small_cap_amplifier": -0.05,
    },
    {
        "id": "india_election_uncertainty",
        "name": "India Election Uncertainty",
        "category": "political",
        "macro_driver": "VIX_spike_to_40",
        "severity": "medium",
        "horizon": "3–6 months",
        "historical_analog": "2004 Vajpayee loss, 2019 pre-election volatility",
        "sector_shocks": {
            "Banking & Financial Services": -0.08, "Infrastructure": -0.12,
            "IT": -0.05, "Real Estate": -0.10, "Energy": -0.06,
            "Auto": -0.07, "FMCG": -0.04, "Pharma": -0.03,
            "Metals": -0.08, "Fixed Income": +0.02, "Consumer Durables": -0.06,
        },
        "small_cap_amplifier": -0.07,
    },
    {
        "id": "it_sector_correction_25pct",
        "name": "IT Sector Correction −25%",
        "category": "sector",
        "macro_driver": "US_recession_moderate",
        "severity": "high",
        "horizon": "3–9 months",
        "historical_analog": "2022 Nasdaq correction spillover",
        "sector_shocks": {
            "IT": -0.25, "Banking & Financial Services": -0.03,
            "Telecom": -0.08, "Consumer Durables": -0.05,
            "FMCG": +0.02, "Pharma": +0.01, "Infrastructure": -0.02,
            "Real Estate": -0.03, "Fixed Income": +0.01,
        },
        "small_cap_amplifier": -0.04,
    },
    {
        "id": "bfsi_crisis_npa_spike",
        "name": "BFSI Crisis — NPA Spike",
        "category": "sector",
        "macro_driver": "India_GDP_slowdown",
        "severity": "critical",
        "horizon": "6–24 months",
        "historical_analog": "Indian banking NPA crisis 2015–18, YES Bank 2020",
        "sector_shocks": {
            "Banking & Financial Services": -0.35, "Real Estate": -0.25,
            "Infrastructure": -0.18, "FMCG": -0.05, "IT": -0.05,
            "Auto": -0.10, "Metals": -0.10, "Fixed Income": -0.08,
            "Consumer Durables": -0.12, "Energy": -0.06,
        },
        "small_cap_amplifier": -0.10,
    },
    {
        "id": "real_estate_collapse",
        "name": "Real Estate Sector Collapse",
        "category": "sector",
        "macro_driver": "RBI_rate_hike_100bps",
        "severity": "high",
        "horizon": "12–36 months",
        "historical_analog": "India real estate 2012–2016 freeze",
        "sector_shocks": {
            "Real Estate": -0.40, "Banking & Financial Services": -0.15,
            "Infrastructure": -0.10, "Consumer Durables": -0.15,
            "Metals": -0.08, "Auto": -0.06, "FMCG": -0.03,
            "Fixed Income": -0.04, "Chemicals": -0.05,
        },
        "small_cap_amplifier": -0.08,
    },
    {
        "id": "infrastructure_boom",
        "name": "Infrastructure Boom",
        "category": "sector",
        "macro_driver": "RBI_rate_cut_75bps",
        "severity": "low",
        "horizon": "12–36 months",
        "historical_analog": "India infra push 2004–2008, NDA capex 2022–24",
        "sector_shocks": {
            "Infrastructure": +0.35, "Metals": +0.20, "Cement": +0.25,
            "Real Estate": +0.15, "Banking & Financial Services": +0.10,
            "Auto": +0.08, "Energy": +0.10, "FMCG": +0.03,
            "IT": +0.02, "Fixed Income": -0.01,
        },
        "small_cap_amplifier": +0.08,
    },
    {
        "id": "geopolitical_escalation",
        "name": "Geopolitical Escalation",
        "category": "geopolitical",
        "macro_driver": "VIX_spike_to_40",
        "severity": "high",
        "horizon": "1–6 months",
        "historical_analog": "Kargil 1999, Russia-Ukraine 2022",
        "sector_shocks": {
            "Banking & Financial Services": -0.12, "IT": -0.10,
            "Auto": -0.12, "Real Estate": -0.14, "Infrastructure": -0.10,
            "Metals": -0.08, "Energy": +0.12, "Defence": +0.20,
            "FMCG": -0.05, "Pharma": -0.04, "Fixed Income": +0.03,
        },
        "small_cap_amplifier": -0.08,
    },
    {
        "id": "covid_pandemic_shock",
        "name": "COVID-Style Pandemic Shock",
        "category": "systemic",
        "macro_driver": "global_liquidity_crisis",
        "severity": "critical",
        "horizon": "3–18 months",
        "historical_analog": "COVID-19 March–April 2020",
        "sector_shocks": {
            "Aviation": -0.60, "Hotels & Tourism": -0.55,
            "Real Estate": -0.30, "Auto": -0.38, "Retail": -0.45,
            "Banking & Financial Services": -0.28, "Infrastructure": -0.30,
            "IT": -0.15, "Pharma": +0.20, "Healthcare": +0.18,
            "FMCG": -0.05, "Telecom": +0.08, "Fixed Income": -0.04,
            "Consumer Durables": -0.32, "Metals": -0.22, "Energy": -0.25,
        },
        "small_cap_amplifier": -0.18,
    },
]

SCENARIO_BY_ID: Dict[str, Dict] = {s["id"]: s for s in SCENARIOS}


# ════════════════════════════════════════════════════════════════
# MACRO SENSITIVITY PROPAGATION
# ════════════════════════════════════════════════════════════════

def compute_macro_sensitivity(
    sector_exposure: Dict[str, float],
    portfolio_value: float,
    macro_event: str,
) -> Dict:
    if macro_event not in MACRO_SENSITIVITY:
        return {"error": f"Unknown macro event: {macro_event}"}

    sensitivity_map = MACRO_SENSITIVITY[macro_event]
    contributions = []
    total_impact_pct = 0.0
    rate_sensitive_pct = 0.0
    rate_beneficiary_pct = 0.0

    for sector, weight_pct in sector_exposure.items():
        coeff = sensitivity_map.get(sector)
        if coeff is None:
            for key, val in sensitivity_map.items():
                if key.lower() in sector.lower() or sector.lower() in key.lower():
                    coeff = val
                    break
        if coeff is None:
            coeff = 0.0

        contribution_pct = (weight_pct / 100.0) * coeff * 100.0
        total_impact_pct += contribution_pct

        if coeff < 0:
            rate_sensitive_pct += weight_pct
        elif coeff > 0:
            rate_beneficiary_pct += weight_pct

        contributions.append({
            "sector": sector,
            "weight_pct": round(weight_pct, 2),
            "sensitivity_coefficient": round(coeff, 3),
            "contribution_pct": round(contribution_pct, 3),
        })

    contributions.sort(key=lambda x: x["contribution_pct"])
    impact_inr = portfolio_value * total_impact_pct / 100.0

    return {
        "macro_event": macro_event,
        "portfolio_sensitivity": f"{'High' if abs(total_impact_pct) > 10 else 'Medium' if abs(total_impact_pct) > 5 else 'Low'} ({total_impact_pct:+.1f}%)",
        "total_impact_pct": round(total_impact_pct, 2),
        "total_impact_inr": round(impact_inr, 0),
        "by_sector": {c["sector"]: round(c["contribution_pct"], 3) for c in contributions if c["contribution_pct"] != 0},
        "effective_exposure": {
            "rate_sensitive_pct": round(rate_sensitive_pct, 1),
            "rate_beneficiary_pct": round(rate_beneficiary_pct, 1),
            "neutral_pct": round(max(0, 100 - rate_sensitive_pct - rate_beneficiary_pct), 1),
        },
        "top_impacted_sectors": contributions[:5],
        "confidence": "High",
        "methodology": "macro_sensitivity_v2.1",
    }


def compute_full_macro_sensitivity_matrix(
    sector_exposure: Dict[str, float],
    portfolio_value: float,
) -> Dict:
    results = {}
    for macro_event in MACRO_SENSITIVITY:
        results[macro_event] = compute_macro_sensitivity(sector_exposure, portfolio_value, macro_event)

    negative_impacts = [
        abs(r["total_impact_pct"])
        for r in results.values()
        if r.get("total_impact_pct", 0) < 0
    ]
    avg_downside = sum(negative_impacts) / len(negative_impacts) if negative_impacts else 0
    macro_vulnerability_score = min(100, avg_downside * 5)

    return {
        "macro_sensitivity_matrix": results,
        "macro_vulnerability_score": round(macro_vulnerability_score, 1),
        "most_sensitive_event": max(results, key=lambda k: abs(results[k].get("total_impact_pct", 0))),
        "least_sensitive_event": min(results, key=lambda k: abs(results[k].get("total_impact_pct", 0))),
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "methodology": "wealthos_macro_sensitivity_v2.1",
    }


# ════════════════════════════════════════════════════════════════
# SCENARIO PROPAGATION ENGINE
# ════════════════════════════════════════════════════════════════

def _apply_scenario(
    scenario: Dict,
    sector_exp: Dict[str, float],
    cap_split: Dict[str, float],
    total_value: float,
) -> Dict:
    sector_shocks = scenario["sector_shocks"]
    small_pct = cap_split.get("small", 0) / 100.0
    portfolio_impact = 0.0
    affected = []

    for sector, weight_pct in sector_exp.items():
        shock = sector_shocks.get(sector)
        if shock is None:
            for key, val in sector_shocks.items():
                if key.lower() in sector.lower() or sector.lower() in key.lower():
                    shock = val
                    break
        if shock is None:
            shock = sector_shocks.get("Diversified", -0.05)

        contribution = (weight_pct / 100.0) * shock * 100.0
        portfolio_impact += contribution

        if abs(shock) >= 0.03:
            affected.append({
                "sector": sector,
                "weight_pct": round(weight_pct, 1),
                "shock_pct": round(shock * 100, 1),
                "contribution_pct": round(contribution, 2),
                "direction": "negative" if shock < 0 else "positive",
            })

    small_amplifier = scenario.get("small_cap_amplifier", 0)
    small_contrib = small_pct * small_amplifier * 100
    portfolio_impact += small_contrib
    affected.sort(key=lambda x: abs(x["contribution_pct"]), reverse=True)

    pct = abs(portfolio_impact)
    risk_band = "Extreme" if pct >= 20 else "High" if pct >= 10 else "Moderate" if pct >= 5 else "Low"

    return {
        "id": scenario["id"],
        "name": scenario["name"],
        "category": scenario.get("category", "unknown"),
        "severity": scenario["severity"],
        "horizon": scenario["horizon"],
        "historical_analog": scenario.get("historical_analog", ""),
        "estimated_impact_pct": round(portfolio_impact, 2),
        "estimated_impact_inr": round(total_value * portfolio_impact / 100.0, 0),
        "risk_band": risk_band,
        "small_cap_contribution_pct": round(small_contrib, 2),
        "affected_sectors": affected[:6],
        "top_risk_sector": affected[0]["sector"] if affected else None,
        "methodology": "wealthos_scenario_propagation_v2.0",
    }


def run_scenarios(
    sector_exp: Dict[str, float],
    cap_split: Dict[str, float],
    total_value: float,
    scenario_ids: Optional[List[str]] = None,
) -> List[Dict]:
    scenarios_to_run = SCENARIOS
    if scenario_ids:
        scenarios_to_run = [s for s in SCENARIOS if s["id"] in scenario_ids]

    results = [_apply_scenario(s, sector_exp, cap_split, total_value) for s in scenarios_to_run]
    results.sort(key=lambda x: abs(x["estimated_impact_pct"]), reverse=True)
    return results


def run_custom_scenario(
    sector_shocks: Dict[str, float],
    sector_exp: Dict[str, float],
    cap_split: Dict[str, float],
    total_value: float,
    scenario_name: str = "Custom Scenario",
) -> Dict:
    custom = {
        "id": "custom",
        "name": scenario_name,
        "category": "custom",
        "severity": "custom",
        "horizon": "user-defined",
        "historical_analog": "Custom",
        "sector_shocks": sector_shocks,
        "small_cap_amplifier": 0.0,
    }
    return _apply_scenario(custom, sector_exp, cap_split, total_value)
