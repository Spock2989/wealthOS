"""
WealthOS Master Analytics Core
Orchestrates all engines into a single unified output for the dashboard.
"""

import numpy as np
import pandas as pd
from typing import List, Dict, Any
from collections import defaultdict
from sqlalchemy.orm import Session

from models import Holding
from engines.scenario_engine     import run_scenarios
from engines.statistical_engine  import compute_statistical_summary
from engines.risk_engine         import compute_risk_summary
from engines.performance_engine  import compute_performance_summary
from engines.factor_engine       import multifactor_regression, capm_regression
from engines.lookthrough_engine  import compute_lookthrough_report
from engines.price_provider      import (
    get_portfolio_returns, get_benchmark_returns, get_factor_returns,
)


def compute_portfolio_analytics(holdings: List[Holding], db: Session) -> Dict[str, Any]:
    if not holdings:
        return {}
    total_value = sum(h.value for h in holdings)
    if total_value == 0:
        return {}

    weights     = {h.id: h.value / total_value for h in holdings}
    asset_alloc = _asset_allocation(holdings, weights)
    sector_exp  = _sector_exposure(holdings, weights)
    cap_split   = _market_cap_split(holdings, weights)
    top_h       = _top_holdings(holdings, weights)

    hhi  = sum(w ** 2 for w in weights.values())
    neff = round(1 / hhi, 2) if hhi > 0 else 0

    # Time-series analytics
    portfolio_returns = get_portfolio_returns(holdings, days=252)
    benchmark_returns = get_benchmark_returns("NIFTY50", days=252)

    stat_summary = compute_statistical_summary(portfolio_returns)
    risk_summary = compute_risk_summary(portfolio_returns, benchmark_returns)
    perf_summary = compute_performance_summary(portfolio_returns, benchmark_returns)

    # Factor decomposition
    factor_returns = get_factor_returns(days=252)
    capm           = capm_regression(portfolio_returns, benchmark_returns)
    multifactor    = multifactor_regression(portfolio_returns, factor_returns)

    # Look-through (only meaningful when fund_constituents are populated)
    lookthrough = compute_lookthrough_report(holdings)

    # Scenarios
    scenarios = run_scenarios(sector_exp, cap_split, total_value)

    # Risk explainability
    drivers = _risk_drivers(sector_exp, cap_split, hhi)
    risk_score = _composite_risk_score(hhi, cap_split, sector_exp,
                                       risk_summary, perf_summary)

    return {
        "total_value":         total_value,
        "holdings_count":      len(holdings),
        "asset_allocation":    asset_alloc,
        "sector_exposure":     sector_exp,
        "market_cap_split":    cap_split,
        "top_holdings":        top_h,
        "hhi":                 round(hhi, 4),
        "neff":                neff,
        "concentration_score": min(100, int(hhi * 200)),
        "risk_score":          risk_score,
        "risk_drivers":        drivers,
        "statistical_summary": stat_summary,
        "risk_metrics":        risk_summary,
        "performance":         perf_summary,
        "capm":                capm,
        "factor_decomposition":multifactor,
        "lookthrough":         lookthrough,
        "scenarios":           scenarios,
        "methodology_version": "wealthos_v2.0",
    }


def _asset_allocation(holdings, weights):
    alloc = defaultdict(float)
    for h in holdings:
        ac = (h.instrument.asset_class if h.instrument else None) or "unknown"
        alloc[ac] += weights[h.id] * 100
    return {
        "equity":        round(alloc.get("equity", 0) + alloc.get("passive_equity", 0), 2),
        "debt":          round(alloc.get("debt", 0), 2),
        "hybrid":        round(alloc.get("hybrid", 0), 2),
        "international": round(alloc.get("international", 0), 2),
        "liquid":        round(alloc.get("liquid", 0), 2),
        "other":         round(alloc.get("unknown", 0), 2),
    }


def _sector_exposure(holdings, weights):
    sec = defaultdict(float)
    for h in holdings:
        s = (h.instrument.sector if h.instrument else None) or "Unclassified"
        sec[s] += weights[h.id] * 100
    return dict(sorted(sec.items(), key=lambda x: x[1], reverse=True))


def _market_cap_split(holdings, weights):
    cap = defaultdict(float)
    for h in holdings:
        b = (h.instrument.market_cap_bucket if h.instrument else None) or "unclassified"
        cap[b] += weights[h.id] * 100
    return {
        "large": round(cap.get("large", 0), 2),
        "mid":   round(cap.get("mid", 0), 2),
        "small": round(cap.get("small", 0), 2),
        "multi": round(cap.get("multi", 0), 2),
        "other": round(cap.get("unclassified", 0), 2),
    }


def _top_holdings(holdings, weights):
    sorted_h = sorted(holdings, key=lambda h: weights[h.id], reverse=True)
    return [{
        "name":        h.instrument.name if h.instrument else "Unknown",
        "isin":        h.instrument.isin if h.instrument else None,
        "sector":      h.instrument.sector if h.instrument else None,
        "asset_class": h.instrument.asset_class if h.instrument else None,
        "market_cap":  h.instrument.market_cap_bucket if h.instrument else None,
        "value":       round(h.value, 2),
        "weight":      round(weights[h.id] * 100, 2),
    } for h in sorted_h[:15]]


def _composite_risk_score(hhi, cap_split, sector_exp, risk_summary, perf_summary):
    conc    = min(30, hhi * 60)
    small   = cap_split.get("small", 0) * 0.4
    top_sec = max(sector_exp.values()) * 0.25 if sector_exp else 0
    mdd_contrib = 0
    if isinstance(risk_summary, dict) and "expected_shortfall_1d" in risk_summary:
        es = abs(risk_summary["expected_shortfall_1d"])
        mdd_contrib = min(20, es * 3)
    sharpe_penalty = 0
    if isinstance(perf_summary, dict) and "sharpe_ratio" in perf_summary:
        sr = perf_summary["sharpe_ratio"]
        if sr < 0.5: sharpe_penalty = 10
        elif sr < 1.0: sharpe_penalty = 5
    return min(100, max(0, int(conc + small + top_sec + mdd_contrib + sharpe_penalty)))


def _risk_drivers(sector_exp, cap_split, hhi):
    drivers = []
    if sector_exp:
        top_s = max(sector_exp, key=sector_exp.get)
        top_p = sector_exp[top_s]
        if top_p > 30:
            drivers.append({"driver": f"{round(top_p,1)}% concentration in {top_s}",
                            "severity": "high" if top_p > 45 else "medium",
                            "method": "sector_weight_sum"})
    small = cap_split.get("small", 0)
    if small > 20:
        drivers.append({"driver": f"{round(small,1)}% small-cap exposure amplifies tail risk",
                        "severity": "high" if small > 35 else "medium",
                        "method": "market_cap_bucket_sum"})
    if hhi > 0.15:
        drivers.append({"driver": f"Low diversification — HHI {round(hhi,3)}",
                        "severity": "high" if hhi > 0.25 else "medium",
                        "method": "herfindahl_hirschman_index"})
    return drivers
