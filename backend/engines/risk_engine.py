"""
WealthOS Risk Engine
VaR, CVaR, beta, tail risk — Aladdin/RiskMetrics grade.
"""

import numpy as np
import pandas as pd
from scipy import stats
from typing import Dict, Optional

TRADING_DAYS = 252


# ── VALUE AT RISK ───────────────────────────────────────────────
def historical_var(returns: pd.Series, confidence: float = 0.95) -> float:
    """
    Historical VaR — empirical quantile of past returns.
    No distribution assumptions. Returns negative number (loss).
    confidence=0.95 → 95% confidence, 5% tail loss.
    """
    if len(returns) < 20:
        return 0.0
    return float(returns.quantile(1 - confidence))


def parametric_var(returns: pd.Series, confidence: float = 0.95) -> float:
    """
    Parametric (delta-normal) VaR. Assumes returns ~ Normal.
    Faster than historical, but fails under fat tails.
    Use Cornish-Fisher for tail-adjusted version.
    """
    if len(returns) < 2:
        return 0.0
    mu    = returns.mean()
    sigma = returns.std(ddof=1)
    z     = stats.norm.ppf(1 - confidence)
    return float(mu + z * sigma)


def cornish_fisher_var(returns: pd.Series, confidence: float = 0.95) -> float:
    """
    Cornish-Fisher VaR — adjusts parametric VaR for skewness and kurtosis.
    More accurate than parametric for non-normal Indian equity returns.
    """
    if len(returns) < 4:
        return 0.0
    z = stats.norm.ppf(1 - confidence)
    s = stats.skew(returns.dropna())
    k = stats.kurtosis(returns.dropna(), fisher=True)

    # Cornish-Fisher expansion
    z_cf = (z
            + (z ** 2 - 1) * s / 6
            + (z ** 3 - 3 * z) * k / 24
            - (2 * z ** 3 - 5 * z) * (s ** 2) / 36)

    mu    = returns.mean()
    sigma = returns.std(ddof=1)
    return float(mu + z_cf * sigma)


def monte_carlo_var(returns: pd.Series, confidence: float = 0.95,
                    n_simulations: int = 10000, horizon_days: int = 1) -> float:
    """
    Monte Carlo VaR with horizon scaling.
    Simulates n paths and returns the quantile of P&L distribution.
    """
    if len(returns) < 2:
        return 0.0
    mu    = returns.mean() * horizon_days
    sigma = returns.std(ddof=1) * np.sqrt(horizon_days)
    rng   = np.random.default_rng(seed=42)
    sims  = rng.normal(mu, sigma, n_simulations)
    return float(np.quantile(sims, 1 - confidence))


# ── CONDITIONAL VAR / EXPECTED SHORTFALL ────────────────────────
def expected_shortfall(returns: pd.Series, confidence: float = 0.95) -> float:
    """
    CVaR / Expected Shortfall — average loss when VaR is breached.
    Coherent risk measure (unlike VaR, it satisfies sub-additivity).
    Regulatory standard under Basel III FRTB.
    """
    if len(returns) < 20:
        return 0.0
    var = historical_var(returns, confidence)
    tail = returns[returns <= var]
    return float(tail.mean()) if len(tail) else float(var)


# ── BETA / SYSTEMATIC RISK ──────────────────────────────────────
def beta(returns: pd.Series, benchmark_returns: pd.Series) -> float:
    """
    CAPM beta — covariance(asset, market) / variance(market).
    >1 = more volatile than benchmark, <1 = less.
    """
    aligned = pd.concat([returns, benchmark_returns], axis=1).dropna()
    if len(aligned) < 20:
        return 0.0
    cov_matrix = np.cov(aligned.iloc[:, 0], aligned.iloc[:, 1])
    var_market = cov_matrix[1, 1]
    return float(cov_matrix[0, 1] / var_market) if var_market > 0 else 0.0


def rolling_beta(returns: pd.Series, benchmark: pd.Series, window: int = 63) -> pd.Series:
    """
    Rolling 3-month beta. Detects regime changes / structural breaks.
    """
    aligned = pd.concat([returns, benchmark], axis=1).dropna()
    aligned.columns = ['r', 'b']
    cov  = aligned['r'].rolling(window).cov(aligned['b'])
    var_ = aligned['b'].rolling(window).var()
    return cov / var_


def downside_beta(returns: pd.Series, benchmark_returns: pd.Series) -> float:
    """
    Downside beta — beta computed only when market is down.
    True crash risk measure. Used by sophisticated allocators.
    """
    aligned = pd.concat([returns, benchmark_returns], axis=1).dropna()
    if len(aligned) < 20:
        return 0.0
    down_mask = aligned.iloc[:, 1] < 0
    if down_mask.sum() < 5:
        return 0.0
    down = aligned[down_mask]
    cov_d = np.cov(down.iloc[:, 0], down.iloc[:, 1])
    var_d = cov_d[1, 1]
    return float(cov_d[0, 1] / var_d) if var_d > 0 else 0.0


# ── COMPONENT VAR / RISK DECOMPOSITION ──────────────────────────
def component_var(weights: np.ndarray, cov_matrix: np.ndarray,
                  confidence: float = 0.95) -> np.ndarray:
    """
    Component VaR — each asset's contribution to portfolio VaR.
    Sum of components = portfolio VaR. Critical for risk budgeting.
    """
    weights = np.asarray(weights)
    portfolio_var      = float(weights @ cov_matrix @ weights)
    portfolio_vol      = np.sqrt(portfolio_var)
    if portfolio_vol == 0:
        return np.zeros_like(weights)
    z                  = stats.norm.ppf(1 - confidence)
    marginal_contrib   = (cov_matrix @ weights) / portfolio_vol
    return weights * marginal_contrib * z


# ── TAIL RISK ───────────────────────────────────────────────────
def tail_ratio(returns: pd.Series) -> float:
    """
    Ratio of right tail (95th %ile) to left tail (5th %ile).
    >1 = positive asymmetry, <1 = crash-prone.
    """
    if len(returns) < 20:
        return 1.0
    right = returns.quantile(0.95)
    left  = abs(returns.quantile(0.05))
    return float(right / left) if left > 0 else 1.0


def gain_to_pain_ratio(returns: pd.Series) -> float:
    """
    Sum of positive returns / abs(sum of negative returns).
    Used by Jack Schwager. Robust to outliers.
    """
    gains  = returns[returns > 0].sum()
    losses = abs(returns[returns < 0].sum())
    return float(gains / losses) if losses > 0 else float('inf')


# ── LIQUIDITY RISK ──────────────────────────────────────────────
def days_to_liquidate(position_value: float, avg_daily_volume: float,
                      participation_rate: float = 0.20) -> float:
    """
    Days needed to liquidate position without market impact.
    participation_rate = max % of ADV the trader will consume per day.
    Standard institutional value: 20%.
    """
    if avg_daily_volume <= 0:
        return float('inf')
    return float(position_value / (avg_daily_volume * participation_rate))


def liquidity_score(holdings: list) -> float:
    """
    Portfolio-level liquidity score 0-100.
    Weighted average of per-instrument liquidity, weighted by position size.
    Higher = more liquid.
    """
    if not holdings:
        return 0.0
    total_w     = sum(h.get('weight', 0) for h in holdings)
    if total_w == 0:
        return 0.0
    weighted    = sum(h.get('weight', 0) * h.get('liquidity_score', 0.5)
                      for h in holdings)
    return float(weighted / total_w * 100)


# ── MASTER SUMMARY ──────────────────────────────────────────────
def compute_risk_summary(
    returns: pd.Series,
    benchmark_returns: Optional[pd.Series] = None,
    confidence: float = 0.95
) -> Dict:
    """One-call risk dashboard."""
    if len(returns) < 20:
        return {"error": "insufficient_data", "observations": len(returns)}

    summary = {
        "confidence_level":     confidence,
        "observations":         len(returns),

        # VaR family
        "historical_var_1d":    round(historical_var(returns, confidence)    * 100, 3),
        "parametric_var_1d":    round(parametric_var(returns, confidence)    * 100, 3),
        "cornish_fisher_var_1d":round(cornish_fisher_var(returns, confidence)* 100, 3),
        "monte_carlo_var_1d":   round(monte_carlo_var(returns, confidence)   * 100, 3),
        "expected_shortfall_1d":round(expected_shortfall(returns, confidence)* 100, 3),

        # Tail
        "tail_ratio":           round(tail_ratio(returns), 3),
        "gain_to_pain_ratio":   round(gain_to_pain_ratio(returns), 3),

        "methodology_version":  "risk_v1.0",
    }

    if benchmark_returns is not None and len(benchmark_returns) >= 20:
        summary.update({
            "beta":          round(beta(returns, benchmark_returns), 3),
            "downside_beta": round(downside_beta(returns, benchmark_returns), 3),
        })

    return summary
