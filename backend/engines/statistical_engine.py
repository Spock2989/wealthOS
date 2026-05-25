"""
WealthOS Statistical Engine
Returns, volatility, drawdown analytics — Bloomberg/FactSet grade.
All inputs are pandas Series of returns (decimal form: 0.01 = 1%).
"""

import numpy as np
import pandas as pd
from scipy import stats
from typing import Dict, Optional

TRADING_DAYS = 252


# ── RETURNS ─────────────────────────────────────────────────────
def log_returns(prices: pd.Series) -> pd.Series:
    """Continuously-compounded returns. Industry standard for vol calculations."""
    return np.log(prices / prices.shift(1)).dropna()


def simple_returns(prices: pd.Series) -> pd.Series:
    """Arithmetic returns. Use for performance reporting."""
    return prices.pct_change().dropna()


def annualized_return(returns: pd.Series, periods_per_year: int = TRADING_DAYS) -> float:
    """Geometric annualized return. CAGR-equivalent for returns series."""
    if len(returns) == 0:
        return 0.0
    compound = (1 + returns).prod()
    years    = len(returns) / periods_per_year
    return float(compound ** (1 / years) - 1) if years > 0 else 0.0


def cumulative_return(returns: pd.Series) -> float:
    """Total compounded return over the series."""
    if len(returns) == 0:
        return 0.0
    return float((1 + returns).prod() - 1)


# ── VOLATILITY ──────────────────────────────────────────────────
def annualized_volatility(returns: pd.Series, periods_per_year: int = TRADING_DAYS) -> float:
    """Annualized standard deviation. Most common risk measure."""
    if len(returns) < 2:
        return 0.0
    return float(returns.std(ddof=1) * np.sqrt(periods_per_year))


def downside_deviation(returns: pd.Series, mar: float = 0.0,
                       periods_per_year: int = TRADING_DAYS) -> float:
    """
    Downside deviation — semi-standard-deviation below a minimum acceptable return.
    Used in Sortino ratio. Captures only "bad" volatility.
    """
    if len(returns) < 2:
        return 0.0
    downside = returns[returns < mar] - mar
    if len(downside) == 0:
        return 0.0
    return float(np.sqrt((downside ** 2).mean()) * np.sqrt(periods_per_year))


def ewma_volatility(returns: pd.Series, lambda_: float = 0.94,
                    periods_per_year: int = TRADING_DAYS) -> float:
    """
    RiskMetrics-style EWMA volatility.
    Weights recent observations more heavily — industry standard for VaR.
    Default λ=0.94 matches J.P. Morgan RiskMetrics.
    """
    if len(returns) < 2:
        return 0.0
    squared    = returns ** 2
    weights    = np.array([(1 - lambda_) * lambda_ ** i for i in range(len(squared))])
    weights    = weights[::-1] / weights.sum()
    var_ewma   = float((squared.values * weights).sum())
    return float(np.sqrt(var_ewma * periods_per_year))


def rolling_volatility(returns: pd.Series, window: int = 21,
                       periods_per_year: int = TRADING_DAYS) -> pd.Series:
    """Rolling window annualized vol — for vol regime detection."""
    return returns.rolling(window).std(ddof=1) * np.sqrt(periods_per_year)


# ── DRAWDOWN ─────────────────────────────────────────────────────
def drawdown_series(returns: pd.Series) -> pd.Series:
    """Drawdown at each point — fraction below the running peak."""
    if len(returns) == 0:
        return pd.Series(dtype=float)
    wealth  = (1 + returns).cumprod()
    peak    = wealth.cummax()
    return (wealth - peak) / peak


def max_drawdown(returns: pd.Series) -> float:
    """Worst peak-to-trough decline. Critical institutional risk metric."""
    dd = drawdown_series(returns)
    return float(dd.min()) if len(dd) else 0.0


def max_drawdown_duration(returns: pd.Series) -> int:
    """
    Longest drawdown duration in days.
    Measures recovery time — how long capital stays under water.
    """
    dd = drawdown_series(returns)
    if len(dd) == 0:
        return 0
    in_dd        = (dd < 0).astype(int)
    groups       = (in_dd != in_dd.shift()).cumsum()
    if in_dd.sum() == 0:
        return 0
    longest = in_dd.groupby(groups).sum().max()
    return int(longest)


def ulcer_index(returns: pd.Series, window: int = 14) -> float:
    """
    Ulcer Index — RMS of drawdowns. Better than std for measuring downside pain.
    Used by Peter Martin in the original UI/UPI work.
    """
    if len(returns) < window:
        return 0.0
    dd      = drawdown_series(returns)
    return float(np.sqrt((dd ** 2).rolling(window).mean().iloc[-1]))


# ── DISTRIBUTION ────────────────────────────────────────────────
def skewness(returns: pd.Series) -> float:
    """
    Third moment. Negative = left tail (crash risk), positive = right tail.
    Indian equity typically has negative skewness.
    """
    if len(returns) < 3:
        return 0.0
    return float(stats.skew(returns.dropna()))


def excess_kurtosis(returns: pd.Series) -> float:
    """
    Fourth moment − 3. Measures fat tails.
    >0 = leptokurtic (more extreme events than normal distribution).
    """
    if len(returns) < 4:
        return 0.0
    return float(stats.kurtosis(returns.dropna(), fisher=True))


def jarque_bera_test(returns: pd.Series) -> Dict[str, float]:
    """
    JB test for normality. p<0.05 means returns are NOT normally distributed.
    Critical for understanding if VaR assumptions hold.
    """
    if len(returns) < 8:
        return {"statistic": 0.0, "p_value": 1.0, "is_normal": True}
    stat, p = stats.jarque_bera(returns.dropna())
    return {
        "statistic": float(stat),
        "p_value":   float(p),
        "is_normal": bool(p > 0.05),
    }


# ── MASTER SUMMARY ──────────────────────────────────────────────
def compute_statistical_summary(returns: pd.Series) -> Dict:
    """One-call summary of all statistical metrics."""
    if len(returns) < 2:
        return {"error": "insufficient_data", "observations": len(returns)}

    return {
        "observations":         len(returns),
        "annualized_return":    round(annualized_return(returns)   * 100, 2),
        "cumulative_return":    round(cumulative_return(returns)   * 100, 2),
        "annualized_volatility":round(annualized_volatility(returns) * 100, 2),
        "downside_deviation":   round(downside_deviation(returns)  * 100, 2),
        "ewma_volatility":      round(ewma_volatility(returns)     * 100, 2),
        "max_drawdown":         round(max_drawdown(returns)        * 100, 2),
        "max_drawdown_duration_days": max_drawdown_duration(returns),
        "ulcer_index":          round(ulcer_index(returns)         * 100, 3),
        "skewness":             round(skewness(returns), 3),
        "excess_kurtosis":      round(excess_kurtosis(returns), 3),
        "jarque_bera":          jarque_bera_test(returns),
        "methodology_version":  "stat_v1.0",
    }
