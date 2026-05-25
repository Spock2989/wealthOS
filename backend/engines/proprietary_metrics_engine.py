"""
WealthOS Proprietary Metrics Engine
THE MOAT — Analytics no Indian platform provides today.

Portfolio Health Score · Fragility Score · Diversification Illusion Score
Effective Number of Bets (Meucci 2009) · Diversification Ratio (Choueifady 2008)
Multi-Level HHI · HHI Normalized · Rebalancing Signal Engine

References:
  - Meucci (2009): "Managing Diversification" — Risk Magazine
  - Choueifady & Coignard (2008): "Toward Maximum Diversification" — JPM
  - Herfindahl (1950) / Hirschman (1964): concentration index
  - WealthOS Definitive Builder Document v4.0 — Section 6.15
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timezone


# ════════════════════════════════════════════════════════════════
# HHI ENGINE — Raw, Normalized, Multi-Level
# ════════════════════════════════════════════════════════════════

def hhi_raw(weights: np.ndarray) -> float:
    """
    Herfindahl-Hirschman Index — sum of squared weights.
    Range: [1/N, 1]
    HHI = 1/N → perfectly equal weight
    HHI = 1   → single position
    """
    w = np.asarray(weights, dtype=float)
    w = w[w > 0]
    if len(w) == 0:
        return 1.0
    return float(np.sum(w ** 2))


def hhi_normalized(weights: np.ndarray) -> float:
    """
    Normalized HHI — removes the size artifact from the raw index.
    HHI_N = (HHI - 1/N) / (1 - 1/N)
    Range: [0, 1]
    0 = maximum diversification for N assets
    1 = complete concentration

    Grades (per WealthOS spec):
      < 0.15 → Diversified
      0.15–0.35 → Moderate Concentration
      0.35–0.60 → High Concentration
      > 0.60 → Extreme Concentration
    """
    w = np.asarray(weights, dtype=float)
    w = w[w > 0]
    n = len(w)
    if n <= 1:
        return 1.0
    raw = hhi_raw(w)
    return float((raw - 1 / n) / (1 - 1 / n))


def neff(weights: np.ndarray) -> float:
    """
    Effective number of positions = 1 / HHI_raw.
    N_eff = N → equally weighted portfolio
    N_eff = 1 → concentrated single bet
    """
    raw = hhi_raw(weights)
    return float(1.0 / raw) if raw > 0 else 0.0


def hhi_grade(hhi_norm: float) -> str:
    if hhi_norm < 0.15:
        return "Diversified"
    elif hhi_norm < 0.35:
        return "Moderate Concentration"
    elif hhi_norm < 0.60:
        return "High Concentration"
    return "Extreme Concentration"


def multi_level_hhi(
    stock_weights: Dict[str, float],
    sector_weights: Dict[str, float],
    factor_weights: Optional[Dict[str, float]] = None,
    theme_weights: Optional[Dict[str, float]] = None,
    geography_weights: Optional[Dict[str, float]] = None,
) -> Dict:
    """
    Multi-level HHI computation per WealthOS North Star spec.
    Computes HHI at: stock → sector → factor → theme → geography level.
    Each level gives a different lens on true concentration.
    """
    sw = np.array(list(stock_weights.values()), dtype=float)
    secw = np.array(list(sector_weights.values()), dtype=float)

    result = {
        "stock": {
            "hhi_raw": round(hhi_raw(sw), 4),
            "hhi_normalized": round(hhi_normalized(sw), 4),
            "neff": round(neff(sw), 2),
            "grade": hhi_grade(hhi_normalized(sw)),
            "top_5": _top_contributors(stock_weights, n=5),
        },
        "sector": {
            "hhi_raw": round(hhi_raw(secw), 4),
            "hhi_normalized": round(hhi_normalized(secw), 4),
            "neff": round(neff(secw), 2),
            "grade": hhi_grade(hhi_normalized(secw)),
            "top_3": _top_contributors(sector_weights, n=3),
        },
    }

    if factor_weights:
        fw = np.array(list(factor_weights.values()), dtype=float)
        result["factor"] = {
            "hhi_raw": round(hhi_raw(fw), 4),
            "hhi_normalized": round(hhi_normalized(fw), 4),
            "neff": round(neff(fw), 2),
            "grade": hhi_grade(hhi_normalized(fw)),
        }

    if theme_weights:
        tw = np.array(list(theme_weights.values()), dtype=float)
        result["theme"] = {
            "hhi_raw": round(hhi_raw(tw), 4),
            "hhi_normalized": round(hhi_normalized(tw), 4),
            "neff": round(neff(tw), 2),
        }

    if geography_weights:
        gw = np.array(list(geography_weights.values()), dtype=float)
        result["geography"] = {
            "hhi_raw": round(hhi_raw(gw), 4),
            "hhi_normalized": round(hhi_normalized(gw), 4),
        }

    return result


def _top_contributors(weights: Dict[str, float], n: int = 5) -> List[Dict]:
    sorted_items = sorted(weights.items(), key=lambda x: x[1], reverse=True)
    return [
        {"name": k, "weight_pct": round(v * 100, 2)}
        for k, v in sorted_items[:n]
    ]


# ════════════════════════════════════════════════════════════════
# EFFECTIVE NUMBER OF BETS — Meucci (2009)
# ════════════════════════════════════════════════════════════════

def effective_number_of_bets(
    weights: np.ndarray,
    cov_matrix: np.ndarray,
) -> Dict:
    """
    Effective Number of Bets (ENB) — Meucci (2009).
    Decomposes portfolio into uncorrelated principal portfolios via PCA.
    Measures how many independent risk bets the portfolio is actually taking.

    ENB = 1  → one concentrated bet (most dangerous)
    ENB = N  → N fully independent bets (true diversification)

    This is fundamentally different from N_eff (which only uses weights).
    ENB accounts for correlations — the most important hidden risk source.

    Steps:
      1. Eigendecompose covariance matrix: Σ = E Λ E'
      2. Compute risk allocation of each principal portfolio:
         p_k = (w' e_k)² × λ_k / σ²_portfolio
      3. Shannon entropy: ENB = exp(-Σ p_k ln(p_k))
    """
    w = np.asarray(weights, dtype=float)
    Sigma = np.asarray(cov_matrix, dtype=float)

    if w.shape[0] != Sigma.shape[0]:
        return {"error": "dimension_mismatch"}
    if Sigma.shape[0] < 2:
        return {"error": "insufficient_assets"}

    # Portfolio variance
    port_var = float(w @ Sigma @ w)
    if port_var <= 0:
        return {"error": "zero_portfolio_variance"}

    # Eigendecomposition (eigh for symmetric positive semi-definite)
    eigenvalues, eigenvectors = np.linalg.eigh(Sigma)

    # Risk allocation across principal portfolios
    # p_k = (w' e_k)² × λ_k / σ²_p
    factor_exposures = eigenvectors.T @ w            # e_k' w for each k
    p_k = (factor_exposures ** 2) * eigenvalues / port_var

    # Clip numerical noise — p_k must sum to 1
    p_k = np.clip(p_k, 1e-15, None)
    p_k = p_k / p_k.sum()

    # Shannon entropy
    entropy = -float(np.sum(p_k * np.log(p_k)))
    enb = float(np.exp(entropy))

    # Concentration: what % of risk is in top 1/3 principal portfolios?
    n = len(p_k)
    top_n = max(1, n // 3)
    top_risk_pct = float(np.sort(p_k)[::-1][:top_n].sum() * 100)

    return {
        "enb": round(enb, 3),
        "enb_max_possible": n,
        "enb_utilization_pct": round(enb / n * 100, 1),
        "n_principal_portfolios": n,
        "top_third_risk_concentration_pct": round(top_risk_pct, 1),
        "risk_allocation_by_pc": [round(float(p), 4) for p in sorted(p_k, reverse=True)[:10]],
        "interpretation": _enb_interpretation(enb, n),
        "methodology": "meucci_2009_principal_portfolios_shannon_entropy",
    }


def _enb_interpretation(enb: float, n: int) -> str:
    ratio = enb / n if n > 0 else 0
    if ratio > 0.7:
        return "Genuinely diversified — portfolio takes many independent risk bets"
    elif ratio > 0.4:
        return "Moderate diversification — some hidden correlation clustering present"
    elif ratio > 0.2:
        return "Low effective diversification — appears diversified but highly correlated"
    return "Extremely concentrated — portfolio behaves like a single risk bet"


# ════════════════════════════════════════════════════════════════
# DIVERSIFICATION RATIO — Choueifady & Coignard (2008)
# ════════════════════════════════════════════════════════════════

def diversification_ratio(
    weights: np.ndarray,
    individual_vols: np.ndarray,
    portfolio_vol: float,
) -> Dict:
    """
    Diversification Ratio (DR) — Choueifady & Coignard (2008).
    Measures how much diversification benefit the portfolio captures.

    DR = weighted average of individual vols / portfolio vol
       = (Σ w_i × σ_i) / σ_portfolio

    DR = 1  → zero diversification benefit (fully correlated)
    DR > 1  → genuine diversification benefit exists
    DR < 1  → impossible under correct math (signals data error)

    Maximum DR portfolio = the "most diversified portfolio" (MDP).
    """
    w = np.asarray(weights, dtype=float)
    sigmas = np.asarray(individual_vols, dtype=float)

    if portfolio_vol <= 0:
        return {"error": "zero_portfolio_vol"}

    weighted_avg_vol = float(w @ sigmas)
    dr = float(weighted_avg_vol / portfolio_vol)

    return {
        "diversification_ratio": round(dr, 4),
        "weighted_avg_individual_vol_pct": round(weighted_avg_vol * 100, 3),
        "portfolio_vol_pct": round(portfolio_vol * 100, 3),
        "diversification_benefit_pct": round((dr - 1) * 100, 2),
        "interpretation": _dr_interpretation(dr),
        "methodology": "choueifady_coignard_2008",
    }


def _dr_interpretation(dr: float) -> str:
    if dr >= 1.5:
        return "High diversification benefit — portfolio captures significant correlation reduction"
    elif dr >= 1.2:
        return "Moderate diversification benefit — reasonable correlation reduction present"
    elif dr >= 1.05:
        return "Low diversification benefit — assets are substantially correlated"
    elif dr >= 1.0:
        return "Minimal diversification benefit — portfolio is near-fully correlated"
    return "Data anomaly — portfolio vol exceeds weighted average individual vol"


# ════════════════════════════════════════════════════════════════
# DIVERSIFICATION ILLUSION SCORE — WealthOS Proprietary
# ════════════════════════════════════════════════════════════════

def diversification_illusion_score(
    n_funds: int,
    effective_holdings_neff: float,
) -> Dict:
    """
    Diversification Illusion Score — WealthOS proprietary metric.
    The insight no Indian platform provides today.

    Score = N_funds / N_eff_holdings - 1

    0.0  → efficient fund structure, no redundancy
    0.5  → 50% more funds than effective holdings (moderate overlap)
    1.0+ → severe duplication — 10 funds behaving like 5 holdings
    2.0+ → extreme illusion — fund structure adds no real diversification

    Example: 9 funds with N_eff = 3.2 → illusion = 9/3.2 - 1 = 1.81
    Meaning: client pays for 9 funds but only gets ~3 independent positions.
    """
    if effective_holdings_neff <= 0:
        return {"error": "invalid_neff"}

    score = n_funds / effective_holdings_neff - 1
    score = max(0.0, score)

    return {
        "illusion_score": round(score, 3),
        "n_funds": n_funds,
        "effective_holdings_neff": round(effective_holdings_neff, 2),
        "redundant_fund_equivalent": round(n_funds - effective_holdings_neff, 2),
        "grade": _illusion_grade(score),
        "interpretation": _illusion_interpretation(score, n_funds, effective_holdings_neff),
        "methodology": "wealthos_diversification_illusion_v1.0",
    }


def _illusion_grade(score: float) -> str:
    if score < 0.2:
        return "Efficient"
    elif score < 0.5:
        return "Mild Overlap"
    elif score < 1.0:
        return "Moderate Illusion"
    elif score < 2.0:
        return "High Illusion"
    return "Severe Illusion"


def _illusion_interpretation(score: float, n_funds: int, neff: float) -> str:
    effective_int = max(1, round(neff))
    if score < 0.2:
        return f"Fund structure is efficient — {n_funds} funds provide genuine diversification"
    elif score < 0.5:
        return (f"Mild overlap — {n_funds} funds behave like ~{effective_int} independent positions. "
                f"Minor consolidation possible.")
    elif score < 1.0:
        return (f"Moderate illusion — {n_funds} funds behave like ~{effective_int} positions. "
                f"Several redundant funds in the portfolio.")
    elif score < 2.0:
        return (f"High illusion — {n_funds} funds provide only ~{effective_int} independent positions. "
                f"Significant fund overlap driving hidden concentration.")
    return (f"Severe illusion — {n_funds} funds behave like only ~{effective_int} positions. "
            f"Portfolio is significantly over-diversified on paper but under-diversified in reality.")


# ════════════════════════════════════════════════════════════════
# PORTFOLIO HEALTH SCORE — WealthOS Proprietary (0-100)
# ════════════════════════════════════════════════════════════════

def portfolio_health_score(
    diversification_score: float,       # 0-100, from ENB/DR
    hhi_norm: float,                    # 0-1 normalized HHI
    sortino_ratio: float,               # risk-adjusted return (downside)
    macro_resilience_score: float,      # 0-100
    liquidity_score: float,             # 0-100
    factor_balance_score: float,        # 0-100, from factor HHI
) -> Dict:
    """
    Portfolio Health Score (0-100) — WealthOS flagship proprietary metric.

    Weighted combination per spec Section 6.15:
      25% diversification (ENB/DR-based, normalized)
      20% concentration inverse (1 - HHI_normalized, scaled)
      20% risk-adjusted return (Sortino vs benchmark)
      15% macro resilience (sensitivity to 11 macro variables)
      10% liquidity (weighted days-to-liquidate score)
      10% factor balance (factor concentration HHI)

    Each sub-score normalized 0-100 independently.
    Final output includes top-3 positive and negative drivers.

    Grades: 0-40 Poor | 40-60 Fair | 60-80 Good | 80-100 Excellent
    """
    # Sub-score 1: Diversification (0-100, already normalized)
    s_diversification = float(np.clip(diversification_score, 0, 100))

    # Sub-score 2: Concentration inverse (HHI_norm 0=good → 100 score, 1=bad → 0 score)
    s_concentration = float(np.clip((1.0 - hhi_norm) * 100, 0, 100))

    # Sub-score 3: Risk-adjusted return (Sortino → map to 0-100)
    # Sortino: > 2.0 = 100, 1.0-2.0 = 60-100, 0-1.0 = 20-60, < 0 = 0
    if sortino_ratio >= 2.0:
        s_risk_return = 100.0
    elif sortino_ratio >= 1.0:
        s_risk_return = 60.0 + (sortino_ratio - 1.0) * 40.0
    elif sortino_ratio >= 0.0:
        s_risk_return = 20.0 + sortino_ratio * 40.0
    else:
        s_risk_return = max(0.0, 20.0 + sortino_ratio * 20.0)
    s_risk_return = float(np.clip(s_risk_return, 0, 100))

    # Sub-score 4: Macro resilience (0-100, already normalized)
    s_macro = float(np.clip(macro_resilience_score, 0, 100))

    # Sub-score 5: Liquidity (0-100, already normalized)
    s_liquidity = float(np.clip(liquidity_score, 0, 100))

    # Sub-score 6: Factor balance (0-100, already normalized — higher = more balanced)
    s_factor = float(np.clip(factor_balance_score, 0, 100))

    # Weighted combination
    health = (
        0.25 * s_diversification +
        0.20 * s_concentration +
        0.20 * s_risk_return +
        0.15 * s_macro +
        0.10 * s_liquidity +
        0.10 * s_factor
    )
    health = float(np.clip(health, 0, 100))

    sub_scores = {
        "diversification":      round(s_diversification, 1),
        "concentration_inverse": round(s_concentration, 1),
        "risk_adjusted_return": round(s_risk_return, 1),
        "macro_resilience":     round(s_macro, 1),
        "liquidity":            round(s_liquidity, 1),
        "factor_balance":       round(s_factor, 1),
    }

    return {
        "health_score": round(health, 1),
        "grade": _health_grade(health),
        "sub_scores": sub_scores,
        "drivers": _health_drivers(sub_scores),
        "methodology": "wealthos_health_score_v1.0",
        "computed_at": datetime.now(timezone.utc).isoformat(),
    }


def _health_grade(score: float) -> str:
    if score >= 80:
        return "Excellent"
    elif score >= 60:
        return "Good"
    elif score >= 40:
        return "Fair"
    return "Poor"


def _health_drivers(sub_scores: Dict[str, float]) -> Dict:
    """Return top-3 positive and top-3 negative drivers with explanations."""
    label_map = {
        "diversification":       "Portfolio Diversification",
        "concentration_inverse": "Concentration Risk",
        "risk_adjusted_return":  "Risk-Adjusted Return",
        "macro_resilience":      "Macro Resilience",
        "liquidity":             "Liquidity Profile",
        "factor_balance":        "Factor Balance",
    }
    sorted_scores = sorted(sub_scores.items(), key=lambda x: x[1], reverse=True)
    positive = [
        {"factor": label_map[k], "score": v, "impact": "positive"}
        for k, v in sorted_scores[:3]
        if v >= 50
    ]
    negative = [
        {"factor": label_map[k], "score": v, "impact": "negative"}
        for k, v in sorted_scores[-3:]
        if v < 50
    ]
    negative.reverse()
    return {"positive_drivers": positive, "negative_drivers": negative}


# ════════════════════════════════════════════════════════════════
# PORTFOLIO FRAGILITY SCORE — WealthOS Proprietary (0-100)
# ════════════════════════════════════════════════════════════════

def portfolio_fragility_score(
    tail_risk_score: float,         # 0-100: from EVT VaR / ES at 99%
    enb_utilization_pct: float,     # 0-100: ENB / N_max * 100
    macro_vulnerability_score: float, # 0-100: sum of |macro sensitivities|
    liquidity_stress_score: float,  # 0-100: illiquid % under stress
    regime_downside_prob: float,    # 0-1: HMM probability in bear regime
) -> Dict:
    """
    Portfolio Fragility Score (0-100) — WealthOS proprietary metric.

    Measures how brittle the portfolio is under adverse conditions.
    High fragility = portfolio likely to suffer outsized losses in stress events.

    Components per spec Section 6.15:
      30% tail risk (EVT-based extreme loss probability)
      25% correlation crowding (low ENB = high fragility)
      20% macro vulnerability (sum of absolute macro sensitivities)
      15% liquidity stress (illiquid holdings under stress)
      10% regime vulnerability (HMM bear regime probability)

    0-25  = Low Fragility (resilient portfolio)
    25-50 = Moderate Fragility
    50-75 = High Fragility
    75+   = Extreme Fragility (institutional alarm)
    """
    # Component 1: Tail risk (higher EVT loss → higher fragility)
    c_tail = float(np.clip(tail_risk_score, 0, 100))

    # Component 2: Correlation crowding (low ENB utilization → high fragility)
    # Low ENB = crowded = fragile; invert ENB utilization
    c_crowding = float(np.clip(100.0 - enb_utilization_pct, 0, 100))

    # Component 3: Macro vulnerability (already 0-100)
    c_macro = float(np.clip(macro_vulnerability_score, 0, 100))

    # Component 4: Liquidity stress (already 0-100)
    c_liquidity = float(np.clip(liquidity_stress_score, 0, 100))

    # Component 5: Regime vulnerability (bear prob 0-1 → 0-100)
    c_regime = float(np.clip(regime_downside_prob * 100, 0, 100))

    fragility = (
        0.30 * c_tail +
        0.25 * c_crowding +
        0.20 * c_macro +
        0.15 * c_liquidity +
        0.10 * c_regime
    )
    fragility = float(np.clip(fragility, 0, 100))

    components = {
        "tail_risk":          round(c_tail, 1),
        "correlation_crowding": round(c_crowding, 1),
        "macro_vulnerability": round(c_macro, 1),
        "liquidity_stress":   round(c_liquidity, 1),
        "regime_vulnerability": round(c_regime, 1),
    }

    return {
        "fragility_score": round(fragility, 1),
        "grade": _fragility_grade(fragility),
        "components": components,
        "dominant_risk": max(components, key=components.get),
        "interpretation": _fragility_interpretation(fragility),
        "methodology": "wealthos_fragility_score_v1.0",
        "computed_at": datetime.now(timezone.utc).isoformat(),
    }


def _fragility_grade(score: float) -> str:
    if score < 25:
        return "Low Fragility"
    elif score < 50:
        return "Moderate Fragility"
    elif score < 75:
        return "High Fragility"
    return "Extreme Fragility"


def _fragility_interpretation(score: float) -> str:
    if score < 25:
        return "Portfolio is resilient — low tail risk and well-diversified across regimes"
    elif score < 50:
        return "Moderate fragility — portfolio may experience amplified drawdowns in stress events"
    elif score < 75:
        return "High fragility — portfolio is brittle under stress; review concentration and macro exposure"
    return "Extreme fragility — portfolio is highly vulnerable to market dislocations and regime shifts"


# ════════════════════════════════════════════════════════════════
# REBALANCING SIGNAL ENGINE — WealthOS Proprietary
# ════════════════════════════════════════════════════════════════

def rebalancing_signals(
    current_weights: Dict[str, float],
    target_weights: Dict[str, float],
    drift_threshold: float = 0.05,
    factor_impacts: Optional[Dict[str, float]] = None,
) -> Dict:
    """
    Rebalancing Signal Engine.
    Detects allocation drift vs target and prioritizes rebalancing actions.

    Drift = |w_current - w_target|
    Threshold: 5% absolute drift triggers alert (institutional standard).

    Priority score = drift × factor_impact × macro_environment_multiplier
    """
    all_assets = set(current_weights) | set(target_weights)
    signals = []
    total_drift = 0.0

    for asset in all_assets:
        current = current_weights.get(asset, 0.0)
        target = target_weights.get(asset, 0.0)
        drift = current - target
        abs_drift = abs(drift)
        total_drift += abs_drift

        factor_impact = factor_impacts.get(asset, 1.0) if factor_impacts else 1.0
        priority_score = abs_drift * factor_impact

        if abs_drift >= drift_threshold:
            signals.append({
                "asset": asset,
                "current_weight_pct": round(current * 100, 2),
                "target_weight_pct": round(target * 100, 2),
                "drift_pct": round(drift * 100, 2),
                "abs_drift_pct": round(abs_drift * 100, 2),
                "action": "REDUCE" if drift > 0 else "INCREASE",
                "priority_score": round(priority_score, 4),
                "urgency": "High" if abs_drift > 0.10 else "Medium",
            })

    signals.sort(key=lambda x: x["priority_score"], reverse=True)

    return {
        "rebalancing_required": len(signals) > 0,
        "n_drifted_positions": len(signals),
        "total_drift_pct": round(total_drift * 100, 2),
        "signals": signals,
        "drift_threshold_pct": round(drift_threshold * 100, 1),
        "methodology": "wealthos_drift_detection_v1.0",
        "computed_at": datetime.now(timezone.utc).isoformat(),
    }


# ════════════════════════════════════════════════════════════════
# MASTER PROPRIETARY METRICS REPORT
# ════════════════════════════════════════════════════════════════

def compute_proprietary_metrics(
    # Holdings data
    stock_weights: Dict[str, float],
    sector_weights: Dict[str, float],
    n_funds: int,
    # Covariance-based
    weights_array: np.ndarray,
    cov_matrix: Optional[np.ndarray] = None,
    individual_vols: Optional[np.ndarray] = None,
    portfolio_vol: Optional[float] = None,
    # Performance
    sortino_ratio: float = 1.0,
    # Macro
    macro_resilience_score: float = 50.0,
    macro_vulnerability_score: float = 50.0,
    # Risk
    tail_risk_score: float = 50.0,
    liquidity_score: float = 70.0,
    liquidity_stress_score: float = 30.0,
    # Regime
    regime_downside_prob: float = 0.3,
    # Factor
    factor_balance_score: float = 60.0,
    factor_weights: Optional[Dict[str, float]] = None,
    # Rebalancing
    target_weights: Optional[Dict[str, float]] = None,
) -> Dict:
    """
    Master one-call proprietary metrics computation.
    Produces the full WealthOS signature analytics suite.
    """
    now = datetime.now(timezone.utc).isoformat()

    # ── Multi-Level HHI
    ml_hhi = multi_level_hhi(stock_weights, sector_weights, factor_weights)
    hhi_norm_val = ml_hhi["stock"]["hhi_normalized"]
    neff_val = ml_hhi["stock"]["neff"]

    # ── ENB (needs covariance matrix)
    enb_result = {}
    enb_utilization = 50.0  # default
    if cov_matrix is not None:
        enb_result = effective_number_of_bets(weights_array, cov_matrix)
        if "enb_utilization_pct" in enb_result:
            enb_utilization = enb_result["enb_utilization_pct"]

    # ── Diversification Score (blend ENB utilization with HHI inverse)
    diversification_score = (enb_utilization * 0.6 + (1 - hhi_norm_val) * 100 * 0.4)

    # ── Diversification Ratio (needs individual vols)
    dr_result = {}
    if individual_vols is not None and portfolio_vol is not None and portfolio_vol > 0:
        dr_result = diversification_ratio(weights_array, individual_vols, portfolio_vol)

    # ── Diversification Illusion Score
    illusion = diversification_illusion_score(n_funds, neff_val)

    # ── Portfolio Health Score
    health = portfolio_health_score(
        diversification_score=diversification_score,
        hhi_norm=hhi_norm_val,
        sortino_ratio=sortino_ratio,
        macro_resilience_score=macro_resilience_score,
        liquidity_score=liquidity_score,
        factor_balance_score=factor_balance_score,
    )

    # ── Portfolio Fragility Score
    fragility = portfolio_fragility_score(
        tail_risk_score=tail_risk_score,
        enb_utilization_pct=enb_utilization,
        macro_vulnerability_score=macro_vulnerability_score,
        liquidity_stress_score=liquidity_stress_score,
        regime_downside_prob=regime_downside_prob,
    )

    # ── Rebalancing Signals
    rebalancing = {}
    if target_weights:
        rebalancing = rebalancing_signals(stock_weights, target_weights)

    return {
        "computed_at": now,
        "methodology_version": "wealthos_proprietary_v1.0",

        # Signature scores — THE MOAT
        "portfolio_health_score": health,
        "portfolio_fragility_score": fragility,
        "diversification_illusion": illusion,

        # Concentration analytics
        "multi_level_hhi": ml_hhi,

        # Diversification analytics
        "effective_number_of_bets": enb_result,
        "diversification_ratio": dr_result,

        # Rebalancing
        "rebalancing_signals": rebalancing,

        # Summary for dashboard KPI cards
        "kpi_summary": {
            "health_score": health["health_score"],
            "health_grade": health["grade"],
            "fragility_score": fragility["fragility_score"],
            "fragility_grade": fragility["grade"],
            "illusion_score": illusion.get("illusion_score", 0),
            "illusion_grade": illusion.get("grade", "N/A"),
            "neff_holdings": neff_val,
            "enb": enb_result.get("enb", None),
            "diversification_ratio": dr_result.get("diversification_ratio", None),
        },

        # Audit trail
        "audit_trail": {
            "n_stocks": len(stock_weights),
            "n_sectors": len(sector_weights),
            "n_funds": n_funds,
            "cov_matrix_provided": cov_matrix is not None,
        },
    }
