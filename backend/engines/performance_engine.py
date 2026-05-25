"""
WealthOS Performance Engine
Risk-adjusted return metrics — institutional-grade ratios.
"""

import numpy as np
import pandas as pd
from typing import Dict, Optional
from engines.statistical_engine import (
    annualized_return, annualized_volatility, downside_deviation, max_drawdown
)
from engines.risk_engine import beta, expected_shortfall

TRADING_DAYS = 252
RISK_FREE_RATE_IN = 0.0675   # India 10Y G-Sec yield, May 2026


# ── SHARPE & VARIANTS ───────────────────────────────────────────
def sharpe_ratio(returns: pd.Series, rf: float = RISK_FREE_RATE_IN,
                 periods_per_year: int = TRADING_DAYS) -> float:
    """
    Sharpe = (excess return) / volatility.
    Most quoted risk-adjusted metric. >1 = good, >2 = excellent.
    """
    if len(returns) < 20:
        return 0.0
    excess = returns - rf / periods_per_year
    sigma  = returns.std(ddof=1)
    if sigma == 0:
        return 0.0
    return float(excess.mean() / sigma * np.sqrt(periods_per_year))


def sortino_ratio(returns: pd.Series, rf: float = RISK_FREE_RATE_IN,
                  periods_per_year: int = TRADING_DAYS) -> float:
    """
    Sortino = excess return / downside deviation.
    Better than Sharpe — only penalises downside volatility.
    """
    if len(returns) < 20:
        return 0.0
    excess = returns - rf / periods_per_year
    dd     = downside_deviation(returns, mar=rf / periods_per_year,
                                periods_per_year=periods_per_year)
    if dd == 0:
        return 0.0
    return float(excess.mean() * periods_per_year / dd)


def calmar_ratio(returns: pd.Series, periods_per_year: int = TRADING_DAYS) -> float:
    """
    Calmar = annualized return / max drawdown.
    Tail-risk-aware. Used heavily by CTAs and hedge funds.
    """
    if len(returns) < 20:
        return 0.0
    ann_ret = annualized_return(returns, periods_per_year)
    mdd     = abs(max_drawdown(returns))
    return float(ann_ret / mdd) if mdd > 0 else 0.0


def omega_ratio(returns: pd.Series, mar: float = 0.0) -> float:
    """
    Omega = probability-weighted ratio of gains to losses around MAR.
    Captures the entire return distribution. Higher = better.
    """
    if len(returns) < 20:
        return 1.0
    excess = returns - mar
    gains  = excess[excess > 0].sum()
    losses = abs(excess[excess < 0].sum())
    return float(gains / losses) if losses > 0 else float('inf')


# ── MARKET-RELATIVE METRICS ─────────────────────────────────────
def treynor_ratio(returns: pd.Series, benchmark: pd.Series,
                  rf: float = RISK_FREE_RATE_IN,
                  periods_per_year: int = TRADING_DAYS) -> float:
    """
    Treynor = excess return / beta.
    Like Sharpe but uses systematic risk only.
    """
    if len(returns) < 20:
        return 0.0
    b = beta(returns, benchmark)
    if b == 0:
        return 0.0
    ann_ret = annualized_return(returns, periods_per_year)
    return float((ann_ret - rf) / b)


def jensens_alpha(returns: pd.Series, benchmark: pd.Series,
                  rf: float = RISK_FREE_RATE_IN,
                  periods_per_year: int = TRADING_DAYS) -> float:
    """
    Jensen's Alpha — CAPM intercept. The "skill" return after adjusting for beta.
    Annualized. >0 = manager beat the market on risk-adjusted basis.
    """
    aligned = pd.concat([returns, benchmark], axis=1).dropna()
    if len(aligned) < 20:
        return 0.0
    r_p     = annualized_return(aligned.iloc[:, 0], periods_per_year)
    r_m     = annualized_return(aligned.iloc[:, 1], periods_per_year)
    b       = beta(aligned.iloc[:, 0], aligned.iloc[:, 1])
    expected = rf + b * (r_m - rf)
    return float(r_p - expected)


def tracking_error(returns: pd.Series, benchmark: pd.Series,
                   periods_per_year: int = TRADING_DAYS) -> float:
    """
    Tracking Error = annualized stdev of active returns.
    For index funds: <0.5% = tight tracking. Active: 4-8% typical.
    """
    aligned = pd.concat([returns, benchmark], axis=1).dropna()
    if len(aligned) < 20:
        return 0.0
    active = aligned.iloc[:, 0] - aligned.iloc[:, 1]
    return float(active.std(ddof=1) * np.sqrt(periods_per_year))


def information_ratio(returns: pd.Series, benchmark: pd.Series,
                      periods_per_year: int = TRADING_DAYS) -> float:
    """
    Information Ratio = active return / tracking error.
    Measures manager skill per unit of active risk. >0.5 = good.
    """
    aligned = pd.concat([returns, benchmark], axis=1).dropna()
    if len(aligned) < 20:
        return 0.0
    active = aligned.iloc[:, 0] - aligned.iloc[:, 1]
    te     = active.std(ddof=1)
    if te == 0:
        return 0.0
    return float(active.mean() / te * np.sqrt(periods_per_year))


def modigliani_m2(returns: pd.Series, benchmark: pd.Series,
                  rf: float = RISK_FREE_RATE_IN,
                  periods_per_year: int = TRADING_DAYS) -> float:
    """
    M² (Modigliani-Modigliani) — Sharpe expressed as a return.
    More intuitive than raw Sharpe: "what would return be at benchmark vol".
    """
    if len(returns) < 20:
        return 0.0
    sr      = sharpe_ratio(returns, rf, periods_per_year)
    bench_vol = annualized_volatility(benchmark, periods_per_year)
    return float(rf + sr * bench_vol)


# ── CAPTURE RATIOS ──────────────────────────────────────────────
def upside_capture(returns: pd.Series, benchmark: pd.Series) -> float:
    """
    Up Capture = portfolio return when benchmark is up / benchmark return when up.
    >100 = outperforms in rising markets.
    """
    aligned = pd.concat([returns, benchmark], axis=1).dropna()
    if len(aligned) < 20:
        return 0.0
    up_mask = aligned.iloc[:, 1] > 0
    if up_mask.sum() < 5:
        return 0.0
    up = aligned[up_mask]
    pr = (1 + up.iloc[:, 0]).prod() - 1
    br = (1 + up.iloc[:, 1]).prod() - 1
    return float(pr / br * 100) if br != 0 else 0.0


def downside_capture(returns: pd.Series, benchmark: pd.Series) -> float:
    """
    Down Capture = portfolio loss when benchmark is down / benchmark loss when down.
    <100 = protects in falling markets. Lower is better.
    """
    aligned = pd.concat([returns, benchmark], axis=1).dropna()
    if len(aligned) < 20:
        return 0.0
    down_mask = aligned.iloc[:, 1] < 0
    if down_mask.sum() < 5:
        return 0.0
    down = aligned[down_mask]
    pr = (1 + down.iloc[:, 0]).prod() - 1
    br = (1 + down.iloc[:, 1]).prod() - 1
    return float(pr / br * 100) if br != 0 else 0.0


# ── BRINSON ATTRIBUTION ─────────────────────────────────────────
def brinson_attribution(
    portfolio_weights: Dict[str, float],
    benchmark_weights: Dict[str, float],
    portfolio_returns: Dict[str, float],
    benchmark_returns: Dict[str, float],
) -> Dict[str, float]:
    """
    Brinson-Hood-Beebower attribution.
    Decomposes active return into: Allocation effect + Selection effect + Interaction.

    portfolio_weights: {sector: weight}
    benchmark_weights: {sector: weight}
    portfolio_returns: {sector: return}
    benchmark_returns: {sector: return}
    """
    all_sectors = set(portfolio_weights) | set(benchmark_weights)
    bench_total = sum(benchmark_weights.get(s, 0) * benchmark_returns.get(s, 0)
                      for s in all_sectors)

    allocation  = 0.0
    selection   = 0.0
    interaction = 0.0

    for s in all_sectors:
        wp = portfolio_weights.get(s, 0)
        wb = benchmark_weights.get(s, 0)
        rp = portfolio_returns.get(s, 0)
        rb = benchmark_returns.get(s, 0)
        allocation  += (wp - wb) * (rb - bench_total)
        selection   += wb * (rp - rb)
        interaction += (wp - wb) * (rp - rb)

    return {
        "allocation_effect":  round(allocation  * 100, 3),
        "selection_effect":   round(selection   * 100, 3),
        "interaction_effect": round(interaction * 100, 3),
        "total_active":       round((allocation + selection + interaction) * 100, 3),
        "methodology":        "brinson_hood_beebower_v1",
    }


# ── MASTER SUMMARY ──────────────────────────────────────────────
def compute_performance_summary(
    returns: pd.Series,
    benchmark: Optional[pd.Series] = None,
    rf: float = RISK_FREE_RATE_IN
) -> Dict:
    """One-call performance dashboard."""
    if len(returns) < 20:
        return {"error": "insufficient_data", "observations": len(returns)}

    summary = {
        "observations":   len(returns),
        "risk_free_rate": round(rf * 100, 2),

        "sharpe_ratio":   round(sharpe_ratio(returns, rf),  3),
        "sortino_ratio":  round(sortino_ratio(returns, rf), 3),
        "calmar_ratio":   round(calmar_ratio(returns),      3),
        "omega_ratio":    round(omega_ratio(returns),       3),

        "methodology_version": "perf_v1.0",
    }

    if benchmark is not None and len(benchmark) >= 20:
        summary.update({
            "treynor_ratio":     round(treynor_ratio(returns, benchmark, rf), 3),
            "jensens_alpha":     round(jensens_alpha(returns, benchmark, rf) * 100, 3),
            "tracking_error":    round(tracking_error(returns, benchmark)    * 100, 3),
            "information_ratio": round(information_ratio(returns, benchmark), 3),
            "m_squared":         round(modigliani_m2(returns, benchmark, rf) * 100, 3),
            "upside_capture":    round(upside_capture(returns, benchmark),    1),
            "downside_capture":  round(downside_capture(returns, benchmark),  1),
        })

    return summary


# ── BRINSON-HOOD-BEEBOWER ATTRIBUTION (1986) ────────────────────
def bhb_attribution(
    portfolio_weights: dict,     # {sector: portfolio_weight}  (fractions, sum=1)
    benchmark_weights: dict,     # {sector: benchmark_weight}  (fractions, sum=1)
    portfolio_returns: dict,     # {sector: portfolio_sector_return} (fractions)
    benchmark_returns: dict,     # {sector: benchmark_sector_return} (fractions)
) -> dict:
    """
    Brinson-Hood-Beebower (1986) three-way return attribution.

    Decomposes active return into three sources:
      Allocation effect  = (w_p - w_b) × (R_b_sector - R_b_total)
        → Did the manager make the right active bets on sectors?
      Selection effect   = w_b × (R_p_sector - R_b_sector)
        → Did the manager pick better stocks within each sector?
      Interaction effect = (w_p - w_b) × (R_p_sector - R_b_sector)
        → Combined effect of allocation + selection decisions

    Active Return = Σ(Allocation + Selection + Interaction) across sectors
    This identity holds exactly — no residual.

    Args:
        portfolio_weights:  {sector: w_p}  — portfolio allocation fraction
        benchmark_weights:  {sector: w_b}  — benchmark allocation fraction
        portfolio_returns:  {sector: R_p}  — portfolio return within sector
        benchmark_returns:  {sector: R_b}  — benchmark return within sector

    Returns:
        Full BHB decomposition with sector-level and aggregate attribution.
    """
    all_sectors = set(portfolio_weights) | set(benchmark_weights)

    # Total benchmark return
    R_b_total = sum(
        benchmark_weights.get(s, 0.0) * benchmark_returns.get(s, 0.0)
        for s in all_sectors
    )
    R_p_total = sum(
        portfolio_weights.get(s, 0.0) * portfolio_returns.get(s, 0.0)
        for s in all_sectors
    )

    sector_attribution = []
    total_allocation   = 0.0
    total_selection    = 0.0
    total_interaction  = 0.0

    for sector in sorted(all_sectors):
        w_p  = portfolio_weights.get(sector, 0.0)
        w_b  = benchmark_weights.get(sector, 0.0)
        R_p  = portfolio_returns.get(sector, 0.0)
        R_b  = benchmark_returns.get(sector, 0.0)

        allocation   = (w_p - w_b) * (R_b - R_b_total)
        selection    = w_b * (R_p - R_b)
        interaction  = (w_p - w_b) * (R_p - R_b)
        total_effect = allocation + selection + interaction

        total_allocation  += allocation
        total_selection   += selection
        total_interaction += interaction

        sector_attribution.append({
            "sector":            sector,
            "portfolio_weight":  round(w_p * 100, 2),
            "benchmark_weight":  round(w_b * 100, 2),
            "active_weight":     round((w_p - w_b) * 100, 2),
            "portfolio_return":  round(R_p * 100, 3),
            "benchmark_return":  round(R_b * 100, 3),
            "active_return":     round((R_p - R_b) * 100, 3),
            "allocation_effect": round(allocation * 100, 4),
            "selection_effect":  round(selection * 100, 4),
            "interaction_effect":round(interaction * 100, 4),
            "total_effect":      round(total_effect * 100, 4),
        })

    active_return = R_p_total - R_b_total
    explained     = total_allocation + total_selection + total_interaction
    residual      = active_return - explained   # should be ~0 (numerical noise only)

    sector_attribution.sort(key=lambda x: abs(x["total_effect"]), reverse=True)

    return {
        "portfolio_return_pct":    round(R_p_total * 100, 3),
        "benchmark_return_pct":    round(R_b_total * 100, 3),
        "active_return_pct":       round(active_return * 100, 3),
        "attribution": {
            "allocation_effect_pct":  round(total_allocation * 100, 4),
            "selection_effect_pct":   round(total_selection * 100, 4),
            "interaction_effect_pct": round(total_interaction * 100, 4),
            "total_explained_pct":    round(explained * 100, 4),
            "residual_pct":           round(residual * 100, 6),  # must be ~0
        },
        "by_sector":        sector_attribution,
        "n_sectors":        len(all_sectors),
        "benchmark_return_total_pct": round(R_b_total * 100, 3),
        "methodology":      "brinson_hood_beebower_1986",
        "methodology_version": "bhb_v1.0",
    }


def pain_ratio(returns: pd.Series, rf: float = RISK_FREE_RATE_IN,
               periods_per_year: int = TRADING_DAYS) -> float:
    """
    Pain Ratio = annualized excess return / Ulcer Index.
    Superior to Sharpe for drawdown-sensitive strategies.
    """
    from engines.statistical_engine import ulcer_index, annualized_return
    if len(returns) < 20:
        return 0.0
    ui = ulcer_index(returns)
    if ui == 0:
        return 0.0
    ann_ret = annualized_return(returns, periods_per_year)
    return float((ann_ret - rf) / ui)
