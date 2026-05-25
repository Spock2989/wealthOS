"""
WealthOS Optimization Engine
Portfolio construction — Mean-Variance, Risk Parity, Maximum Diversification.
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional
from scipy.optimize import minimize


# ── MEAN-VARIANCE (MARKOWITZ) ──────────────────────────────────
def mean_variance_optimize(
    expected_returns: np.ndarray,
    cov_matrix: np.ndarray,
    target_return: Optional[float] = None,
    risk_aversion: float = 1.0,
    allow_short: bool = False,
) -> Dict:
    """
    Markowitz mean-variance optimization.
    Maximizes: r_p − (λ/2) × σ_p²
    Or solves min variance s.t. expected return = target.
    """
    n   = len(expected_returns)
    er  = np.asarray(expected_returns)
    cov = np.asarray(cov_matrix)

    if target_return is None:
        # Maximize utility: λ-weighted return − variance
        def neg_utility(w):
            return -(w @ er - 0.5 * risk_aversion * w @ cov @ w)
        objective = neg_utility
        constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1}]
    else:
        # Min variance s.t. target return
        def variance(w):
            return float(w @ cov @ w)
        objective = variance
        constraints = [
            {"type": "eq", "fun": lambda w: np.sum(w) - 1},
            {"type": "eq", "fun": lambda w: w @ er - target_return},
        ]

    bounds = [(None, None) if allow_short else (0, 1) for _ in range(n)]
    w0     = np.ones(n) / n

    result = minimize(objective, w0, bounds=bounds, constraints=constraints)
    w      = result.x

    return {
        "weights":          [round(float(x), 4) for x in w],
        "expected_return":  round(float(w @ er), 4),
        "volatility":       round(float(np.sqrt(w @ cov @ w)), 4),
        "sharpe":           round(float(w @ er / np.sqrt(w @ cov @ w)), 3)
                            if (w @ cov @ w) > 0 else 0.0,
        "converged":        bool(result.success),
        "methodology":      "markowitz_mvo_v1",
    }


# ── MINIMUM VARIANCE ────────────────────────────────────────────
def minimum_variance_portfolio(cov_matrix: np.ndarray, allow_short: bool = False) -> Dict:
    """
    Global Minimum Variance portfolio. No expected returns needed.
    Robust — doesn't require error-prone return forecasts.
    """
    n   = len(cov_matrix)
    cov = np.asarray(cov_matrix)

    def variance(w):
        return float(w @ cov @ w)

    constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1}]
    bounds      = [(None, None) if allow_short else (0, 1) for _ in range(n)]
    w0          = np.ones(n) / n

    result = minimize(variance, w0, bounds=bounds, constraints=constraints)
    w      = result.x

    return {
        "weights":     [round(float(x), 4) for x in w],
        "volatility":  round(float(np.sqrt(w @ cov @ w)), 4),
        "converged":   bool(result.success),
        "methodology": "min_variance_v1",
    }


# ── RISK PARITY (EQUAL RISK CONTRIBUTION) ──────────────────────
def risk_parity_weights(cov_matrix: np.ndarray) -> Dict:
    """
    Equal Risk Contribution portfolio.
    Each asset contributes equally to portfolio risk.
    Used by Bridgewater All Weather, Ray Dalio's approach.
    """
    n   = len(cov_matrix)
    cov = np.asarray(cov_matrix)

    def risk_budget_objective(w):
        portfolio_vol      = np.sqrt(w @ cov @ w)
        if portfolio_vol == 0:
            return 0.0
        marginal_contrib   = (cov @ w) / portfolio_vol
        risk_contributions = w * marginal_contrib
        target             = portfolio_vol / n
        return float(np.sum((risk_contributions - target) ** 2))

    constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1}]
    bounds      = [(0.001, 1) for _ in range(n)]  # avoid zero weights
    w0          = np.ones(n) / n

    result = minimize(risk_budget_objective, w0, bounds=bounds, constraints=constraints)
    w      = result.x

    portfolio_vol     = np.sqrt(w @ cov @ w)
    marginal_contrib  = (cov @ w) / portfolio_vol if portfolio_vol > 0 else np.zeros(n)
    risk_contributions = w * marginal_contrib

    return {
        "weights":             [round(float(x), 4) for x in w],
        "volatility":          round(float(portfolio_vol), 4),
        "risk_contributions":  [round(float(rc), 4) for rc in risk_contributions],
        "max_risk_contrib_pct":round(float(risk_contributions.max() /
                                          risk_contributions.sum() * 100), 2),
        "converged":           bool(result.success),
        "methodology":         "equal_risk_contribution_v1",
    }


# ── MAXIMUM DIVERSIFICATION ────────────────────────────────────
def max_diversification_portfolio(cov_matrix: np.ndarray) -> Dict:
    """
    Choueifaty's Most Diversified Portfolio.
    Maximizes the Diversification Ratio = w·σ / sqrt(w·Σ·w).
    """
    n   = len(cov_matrix)
    cov = np.asarray(cov_matrix)
    vols = np.sqrt(np.diag(cov))

    def neg_div_ratio(w):
        weighted_vol  = float(w @ vols)
        portfolio_vol = float(np.sqrt(w @ cov @ w))
        if portfolio_vol == 0:
            return 0.0
        return -(weighted_vol / portfolio_vol)

    constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1}]
    bounds      = [(0, 1) for _ in range(n)]
    w0          = np.ones(n) / n

    result = minimize(neg_div_ratio, w0, bounds=bounds, constraints=constraints)
    w      = result.x

    return {
        "weights":              [round(float(x), 4) for x in w],
        "diversification_ratio":round(-result.fun, 3),
        "volatility":           round(float(np.sqrt(w @ cov @ w)), 4),
        "converged":            bool(result.success),
        "methodology":          "max_diversification_choueifaty_v1",
    }


# ── EFFICIENT FRONTIER ──────────────────────────────────────────
def efficient_frontier(
    expected_returns: np.ndarray,
    cov_matrix: np.ndarray,
    n_points: int = 200,
    rf: float = 0.0675,
) -> Dict:
    """
    Generate full efficient frontier — 200 Pareto-optimal portfolios.
    Marks minimum variance portfolio and tangency (max Sharpe) portfolio.

    Spec: "Trace 200 portfolios from min variance to max return.
           Mark: minimum variance portfolio, tangency portfolio (max Sharpe).
           Report: expected return, volatility, Sharpe for each point."
    """
    er  = np.asarray(expected_returns, dtype=float)
    cov = np.asarray(cov_matrix, dtype=float)

    # Minimum variance portfolio — starting anchor
    mvp = minimum_variance_portfolio(cov)

    r_min = float(er.min())
    r_max = float(er.max())
    target_returns = np.linspace(r_min, r_max, n_points)

    frontier = []
    best_sharpe = -np.inf
    tangency_idx = 0

    for i, target in enumerate(target_returns):
        result = mean_variance_optimize(er, cov, target_return=target)
        if result["converged"]:
            pt = {
                "expected_return_ann_pct": round(target * 252 * 100, 2),
                "volatility_ann_pct":      round(result["volatility"] * np.sqrt(252) * 100, 2),
                "sharpe":                  result["sharpe"],
                "weights":                 result["weights"],
            }
            frontier.append(pt)
            if result["sharpe"] > best_sharpe:
                best_sharpe   = result["sharpe"]
                tangency_idx  = len(frontier) - 1

    # Mark special portfolios
    if frontier:
        frontier[0]["is_minimum_variance"]  = True
        frontier[tangency_idx]["is_tangency"] = True

    mvp_vol = float(mvp["volatility"] * np.sqrt(252) * 100) if "volatility" in mvp else None

    return {
        "frontier":                  frontier,
        "n_points":                  len(frontier),
        "minimum_variance_portfolio": mvp,
        "minimum_variance_vol_ann_pct": round(mvp_vol, 2) if mvp_vol else None,
        "tangency_portfolio_idx":    tangency_idx,
        "tangency_sharpe":           round(best_sharpe, 3),
        "rf_used":                   rf,
        "methodology":               "markowitz_efficient_frontier_200pts",
    }
