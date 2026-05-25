"""
WealthOS Factor Engine
Multi-factor regression — Fama-French 5-factor + Carhart momentum + Quality.
True factor decomposition via OLS regression. Not weighted-average heuristics.
"""

import numpy as np
import pandas as pd
from typing import Dict, Optional, List

try:
    import statsmodels.api as sm
    STATSMODELS_AVAILABLE = True
except ImportError:
    STATSMODELS_AVAILABLE = False


# ── FAMA-FRENCH FACTORS ─────────────────────────────────────────
# Standard factor names — adapted for Indian market context.
FACTOR_DEFINITIONS = {
    "MKT":  "Market excess return (Nifty 500 − Risk-Free Rate)",
    "SMB":  "Small Minus Big — small-cap premium",
    "HML":  "High Minus Low — value premium (high B/M − low B/M)",
    "RMW":  "Robust Minus Weak — profitability factor (high ROE − low ROE)",
    "CMA":  "Conservative Minus Aggressive — investment factor",
    "MOM":  "Momentum — winners minus losers (12-month, skip 1)",
    "QMJ":  "Quality Minus Junk — AQR-style quality factor",
    "BAB":  "Betting Against Beta — low-beta anomaly",
    "LIQ":  "Liquidity factor — Pastor-Stambaugh",
}


# ── SINGLE-FACTOR (CAPM) ────────────────────────────────────────
def capm_regression(returns: pd.Series, market_returns: pd.Series,
                    rf: float = 0.0675) -> Dict:
    """
    Single-factor CAPM regression.
    r_p − rf = α + β(r_m − rf) + ε
    Returns alpha, beta, R², t-stats.
    """
    if not STATSMODELS_AVAILABLE:
        return {"error": "statsmodels_not_installed"}

    aligned = pd.concat([returns, market_returns], axis=1).dropna()
    if len(aligned) < 30:
        return {"error": "insufficient_data", "observations": len(aligned)}

    rf_daily = rf / 252
    y = aligned.iloc[:, 0] - rf_daily
    x = aligned.iloc[:, 1] - rf_daily
    X = sm.add_constant(x)
    model = sm.OLS(y, X).fit()

    return {
        "alpha_annualized": round(float(model.params.iloc[0]) * 252 * 100, 3),
        "alpha_t_stat":     round(float(model.tvalues.iloc[0]), 3),
        "alpha_p_value":    round(float(model.pvalues.iloc[0]), 4),
        "beta":             round(float(model.params.iloc[1]), 3),
        "beta_t_stat":      round(float(model.tvalues.iloc[1]), 3),
        "r_squared":        round(float(model.rsquared), 4),
        "adj_r_squared":    round(float(model.rsquared_adj), 4),
        "observations":     int(model.nobs),
        "methodology":      "ols_capm_v1",
    }


# ── MULTI-FACTOR (FAMA-FRENCH + CARHART) ───────────────────────
def multifactor_regression(
    returns: pd.Series,
    factor_returns: pd.DataFrame,
    rf: float = 0.0675,
) -> Dict:
    """
    Multi-factor OLS regression.
    r_p − rf = α + Σ βᵢ × Fᵢ + ε

    factor_returns: DataFrame with columns MKT, SMB, HML, MOM, QMJ etc.
    Each column is the factor's daily return time series.
    """
    if not STATSMODELS_AVAILABLE:
        return {"error": "statsmodels_not_installed"}

    aligned = pd.concat([returns, factor_returns], axis=1).dropna()
    if len(aligned) < 60:
        return {"error": "insufficient_data", "observations": len(aligned)}

    rf_daily = rf / 252
    y = aligned.iloc[:, 0] - rf_daily
    X = aligned.iloc[:, 1:]
    X_const = sm.add_constant(X)
    model   = sm.OLS(y, X_const).fit()

    # Extract factor loadings (skip intercept)
    factor_loadings = {}
    for col in X.columns:
        factor_loadings[col] = {
            "beta":     round(float(model.params[col]), 4),
            "t_stat":   round(float(model.tvalues[col]), 3),
            "p_value":  round(float(model.pvalues[col]), 4),
            "significant_5pct": bool(model.pvalues[col] < 0.05),
        }

    return {
        "alpha_annualized": round(float(model.params.iloc[0]) * 252 * 100, 3),
        "alpha_t_stat":     round(float(model.tvalues.iloc[0]), 3),
        "alpha_p_value":    round(float(model.pvalues.iloc[0]), 4),
        "alpha_is_significant_5pct": bool(model.pvalues.iloc[0] < 0.05),

        "factor_loadings": factor_loadings,

        "r_squared":     round(float(model.rsquared), 4),
        "adj_r_squared": round(float(model.rsquared_adj), 4),
        "f_statistic":   round(float(model.fvalue), 3),
        "f_p_value":     round(float(model.f_pvalue), 6),

        "observations": int(model.nobs),
        "methodology":  "ols_multifactor_v1",
    }


# ── RETURNS-BASED STYLE ANALYSIS (SHARPE) ──────────────────────
def sharpe_style_analysis(
    returns: pd.Series,
    style_indices: pd.DataFrame,
) -> Dict:
    """
    Sharpe Returns-Based Style Analysis.
    Constrained quadratic optimization: weights ≥0, sum to 1.
    Decomposes returns into exposure to N style indices.

    style_indices: DataFrame with columns = style names (large_value, large_growth,
                   mid_blend, small_value, etc.)
    """
    from scipy.optimize import minimize

    aligned = pd.concat([returns, style_indices], axis=1).dropna()
    if len(aligned) < 30:
        return {"error": "insufficient_data"}

    y = aligned.iloc[:, 0].values
    X = aligned.iloc[:, 1:].values
    n = X.shape[1]

    def tracking_error_sq(w):
        return float(np.sum((y - X @ w) ** 2))

    constraints = [
        {"type": "eq",   "fun": lambda w: np.sum(w) - 1},  # weights sum to 1
    ]
    bounds = [(0, 1) for _ in range(n)]  # no shorting
    w0     = np.ones(n) / n

    result = minimize(tracking_error_sq, w0, bounds=bounds, constraints=constraints)
    weights = result.x

    # R² of the style fit
    fitted     = X @ weights
    ss_res     = float(np.sum((y - fitted) ** 2))
    ss_tot     = float(np.sum((y - y.mean()) ** 2))
    r_squared  = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0.0

    style_names = style_indices.columns.tolist()
    exposures   = {name: round(float(w), 4) for name, w in zip(style_names, weights)}

    return {
        "style_exposures": exposures,
        "r_squared":       round(r_squared, 4),
        "selection_return":round(float(y.mean() - fitted.mean()) * 252 * 100, 3),
        "methodology":     "sharpe_quadratic_v1",
    }


# ── INFORMATION COEFFICIENT ─────────────────────────────────────
def information_coefficient(
    factor_scores: pd.Series,
    forward_returns: pd.Series
) -> Dict:
    """
    IC = Spearman rank correlation between factor scores and forward returns.
    Measures predictive power of a factor / signal.
    IC of 0.05+ is considered useful, 0.10+ is excellent.
    """
    from scipy import stats
    aligned = pd.concat([factor_scores, forward_returns], axis=1).dropna()
    if len(aligned) < 30:
        return {"error": "insufficient_data"}

    rho, p_value = stats.spearmanr(aligned.iloc[:, 0], aligned.iloc[:, 1])
    return {
        "ic":           round(float(rho), 4),
        "p_value":      round(float(p_value), 4),
        "is_significant_5pct": bool(p_value < 0.05),
        "observations": len(aligned),
        "methodology":  "spearman_rank_correlation",
    }


# ── PORTFOLIO FACTOR DECOMPOSITION ─────────────────────────────
def decompose_portfolio_factors(
    portfolio_returns: pd.Series,
    factor_returns: pd.DataFrame,
    rf: float = 0.0675,
) -> Dict:
    """
    Decompose portfolio total return into:
      - Risk-free component
      - Factor exposure contributions
      - Alpha (unexplained / selection skill)
      - Idiosyncratic risk
    """
    result = multifactor_regression(portfolio_returns, factor_returns, rf)
    if "error" in result:
        return result

    total_factor_contrib = 0.0
    contributions = {}
    for factor_name, stats in result["factor_loadings"].items():
        avg_factor_return = float(factor_returns[factor_name].mean() * 252)
        contribution      = stats["beta"] * avg_factor_return
        contributions[factor_name] = {
            "beta":         stats["beta"],
            "factor_return_annualized": round(avg_factor_return * 100, 3),
            "contribution_pct": round(contribution * 100, 3),
        }
        total_factor_contrib += contribution

    total_return_annual  = float(portfolio_returns.mean() * 252)
    explained_return     = rf + total_factor_contrib
    unexplained          = total_return_annual - explained_return

    return {
        "total_return_annualized":  round(total_return_annual * 100, 3),
        "risk_free_component":      round(rf * 100, 3),
        "factor_contributions":     contributions,
        "total_factor_contribution":round(total_factor_contrib * 100, 3),
        "alpha_annualized":         result["alpha_annualized"],
        "unexplained_residual":     round(unexplained * 100, 3),
        "r_squared":                result["r_squared"],
        "methodology":              "factor_decomposition_v1",
    }
