"""
WealthOS Backtesting Engine
Walk-forward analysis, deflated Sharpe ratio, PBO, statistical significance.

References:
  - López de Prado (2014): "The Sharpe Ratio Efficient Frontier"
  - Bailey & López de Prado (2014): "The Deflated Sharpe Ratio"
  - Bailey et al. (2017): "The Probability of Backtest Overfitting"
"""

import numpy as np
import pandas as pd
from scipy import stats
from typing import Dict, List, Callable, Optional

TRADING_DAYS = 252


# ════════════════════════════════════════════════════════════════
# WALK-FORWARD ANALYSIS
# ════════════════════════════════════════════════════════════════

def walk_forward_backtest(
    returns: pd.DataFrame,
    strategy_fn: Callable,
    train_window: int = 252,
    test_window: int = 63,
    step: int = 21,
) -> Dict:
    """
    Walk-forward backtesting with anchored re-fitting.

    For each window: train on past N days, generate weights, test on next M days.
    Slide forward and repeat. Aggregates true out-of-sample performance.

    strategy_fn: callable(train_returns: pd.DataFrame) -> weights: np.ndarray
    """
    if returns.shape[0] < train_window + test_window:
        return {"error": "insufficient_data_for_walkforward"}

    n_obs   = returns.shape[0]
    results = []
    oos_returns = []
    weights_history = []

    start = train_window
    while start + test_window <= n_obs:
        train = returns.iloc[start - train_window:start]
        test  = returns.iloc[start:start + test_window]

        try:
            w = strategy_fn(train)
            w = np.asarray(w)
            if len(w) != train.shape[1] or not np.isclose(w.sum(), 1.0, atol=0.01):
                start += step
                continue
        except Exception:
            start += step
            continue

        # Compute out-of-sample returns
        oos_period_returns = (test.values @ w)
        oos_returns.extend(oos_period_returns)
        weights_history.append(w)
        results.append({
            "start_idx":       start,
            "end_idx":         start + test_window,
            "period_return":   float((1 + pd.Series(oos_period_returns)).prod() - 1),
            "period_vol":      float(pd.Series(oos_period_returns).std() * np.sqrt(TRADING_DAYS)),
        })
        start += step

    if not oos_returns:
        return {"error": "no_valid_windows"}

    oos_series = pd.Series(oos_returns)
    ann_return = float(oos_series.mean() * TRADING_DAYS)
    ann_vol    = float(oos_series.std(ddof=1) * np.sqrt(TRADING_DAYS))
    sharpe     = ann_return / ann_vol if ann_vol > 0 else 0.0

    return {
        "n_windows":           len(results),
        "total_oos_days":      len(oos_returns),
        "oos_annualized_return_pct":  round(ann_return * 100, 3),
        "oos_annualized_volatility_pct": round(ann_vol * 100, 3),
        "oos_sharpe_ratio":    round(sharpe, 3),
        "weights_stability_avg_l1": _weights_stability(weights_history),
        "methodology":         "walk_forward_anchored",
    }


def _weights_stability(weights_history: List[np.ndarray]) -> float:
    """Average L1-norm between consecutive weight vectors. Lower = more stable."""
    if len(weights_history) < 2:
        return 0.0
    diffs = [
        float(np.abs(weights_history[i] - weights_history[i - 1]).sum())
        for i in range(1, len(weights_history))
    ]
    return round(float(np.mean(diffs)), 4)


# ════════════════════════════════════════════════════════════════
# DEFLATED SHARPE RATIO (Bailey & López de Prado 2014)
# ════════════════════════════════════════════════════════════════

def deflated_sharpe_ratio(
    sharpe_observed: float,
    n_trials: int,
    n_observations: int,
    skewness: float = 0.0,
    kurtosis: float = 3.0,
) -> Dict:
    """
    Deflated Sharpe Ratio (DSR) — adjusts observed Sharpe for:
      1. Number of strategies tried (multiple testing bias)
      2. Skewness and kurtosis of returns
      3. Length of backtest

    Returns the probability that the true Sharpe is positive.

    Critical: a Sharpe of 2.0 found among 100 trials is much weaker evidence
    than the same Sharpe from a single test.
    """
    if n_observations < 30 or n_trials < 1:
        return {"error": "insufficient_inputs"}

    # Expected maximum Sharpe under null (no skill, all luck)
    # E[max SR] ≈ √(2·log(N)) (Bailey & López de Prado)
    if n_trials > 1:
        emc       = 0.5772156649  # Euler-Mascheroni constant
        max_z     = ((1 - emc) * stats.norm.ppf(1 - 1 / n_trials)
                     + emc * stats.norm.ppf(1 - 1 / (n_trials * np.e)))
    else:
        max_z = 0.0

    # Variance of Sharpe estimator (Mertens 2002)
    var_sr = (1 - skewness * sharpe_observed
              + (kurtosis - 1) / 4 * sharpe_observed ** 2) / (n_observations - 1)
    if var_sr <= 0:
        return {"error": "invalid_variance"}

    sr_std = np.sqrt(var_sr)
    # Deflated SR statistic
    dsr_stat = (sharpe_observed - max_z * sr_std) / sr_std

    # Probability under H₀: SR ≤ 0
    p_value = 1 - stats.norm.cdf(dsr_stat)
    psr     = stats.norm.cdf(dsr_stat)   # Probabilistic Sharpe Ratio

    return {
        "observed_sharpe":     round(float(sharpe_observed), 4),
        "expected_max_sharpe_null": round(float(max_z * sr_std), 4),
        "dsr_statistic":       round(float(dsr_stat), 4),
        "psr_probability":     round(float(psr), 4),
        "p_value":             round(float(p_value), 4),
        "is_significant_5pct": bool(p_value < 0.05),
        "n_trials_adjusted_for": n_trials,
        "n_observations":      n_observations,
        "methodology":         "deflated_sharpe_bailey_lopez_de_prado_2014",
    }


# ════════════════════════════════════════════════════════════════
# PROBABILISTIC SHARPE RATIO (PSR)
# ════════════════════════════════════════════════════════════════

def probabilistic_sharpe_ratio(returns: pd.Series, benchmark_sr: float = 0.0) -> Dict:
    """
    Probabilistic Sharpe Ratio — probability that the true SR exceeds a benchmark.

    PSR adjusts for non-normality via higher moments.

    PSR(SR*) = Φ((SR - SR*)·√(n-1) / √(1 - γ₃·SR + (γ₄-1)/4·SR²))
    """
    series = returns.dropna()
    n      = len(series)
    if n < 30:
        return {"error": "insufficient_data"}

    sr   = float(series.mean() / series.std(ddof=1)) if series.std(ddof=1) > 0 else 0.0
    g3   = float(stats.skew(series))
    g4   = float(stats.kurtosis(series, fisher=False))  # not excess

    se   = np.sqrt((1 - g3 * sr + (g4 - 1) / 4 * sr ** 2) / (n - 1))
    if se <= 0:
        return {"error": "invalid_se"}

    psr = stats.norm.cdf((sr - benchmark_sr) / se)

    return {
        "sharpe_ratio":      round(float(sr), 4),
        "psr_vs_zero":       round(float(psr), 4),
        "benchmark_sr":      benchmark_sr,
        "skewness":          round(g3, 3),
        "kurtosis":          round(g4, 3),
        "standard_error":    round(float(se), 4),
        "is_significant_5pct": bool(psr > 0.95),
        "methodology":       "probabilistic_sharpe_lopez_de_prado",
    }


# ════════════════════════════════════════════════════════════════
# BLOCK BOOTSTRAP CONFIDENCE INTERVALS
# ════════════════════════════════════════════════════════════════

def block_bootstrap_sharpe_ci(
    returns: pd.Series,
    n_bootstraps: int = 5000,
    block_length: int = 21,
    confidence: float = 0.95,
) -> Dict:
    """
    Stationary block bootstrap CI for Sharpe ratio.
    Preserves autocorrelation structure unlike iid bootstrap.

    Politis & Romano (1994) — stationary bootstrap.
    """
    series = returns.dropna().values
    n      = len(series)
    if n < 50:
        return {"error": "insufficient_data"}

    rng = np.random.default_rng(seed=42)
    sharpes = np.zeros(n_bootstraps)

    for b in range(n_bootstraps):
        sample = np.zeros(n)
        i = 0
        while i < n:
            start = rng.integers(0, n)
            # Geometric block length
            length = rng.geometric(1.0 / block_length)
            length = min(length, n - i)
            for j in range(length):
                sample[i + j] = series[(start + j) % n]
            i += length

        s = sample.std(ddof=1)
        sharpes[b] = (sample.mean() / s * np.sqrt(TRADING_DAYS)) if s > 0 else 0.0

    lower = float(np.quantile(sharpes, (1 - confidence) / 2))
    upper = float(np.quantile(sharpes, 1 - (1 - confidence) / 2))

    return {
        "sharpe_mean":      round(float(sharpes.mean()), 4),
        "sharpe_std":       round(float(sharpes.std(ddof=1)), 4),
        "ci_lower":         round(lower, 4),
        "ci_upper":         round(upper, 4),
        "confidence_level": confidence,
        "n_bootstraps":     n_bootstraps,
        "block_length":     block_length,
        "methodology":      "stationary_block_bootstrap_politis_romano_1994",
    }


# ════════════════════════════════════════════════════════════════
# MINIMUM BACKTEST LENGTH
# ════════════════════════════════════════════════════════════════

def minimum_backtest_length(target_sharpe: float = 1.0,
                              confidence: float = 0.95) -> Dict:
    """
    Minimum number of observations required to claim a target Sharpe is statistically
    different from zero at the given confidence level.

    n ≥ (1 + z²/SR²)  where z = Φ⁻¹(conf)

    Practical rule: to claim SR=1 with 95% confidence, need ~4 years of daily data.
    """
    z = stats.norm.ppf(confidence)
    if target_sharpe == 0:
        return {"error": "target_sharpe_must_be_nonzero"}
    daily_sr = target_sharpe / np.sqrt(TRADING_DAYS)
    min_n = int(np.ceil(1 + (z / daily_sr) ** 2))

    return {
        "target_annualized_sharpe": target_sharpe,
        "confidence_level":         confidence,
        "minimum_daily_observations": min_n,
        "minimum_years_of_data":    round(min_n / TRADING_DAYS, 1),
        "methodology":              "minbtl_lopez_de_prado",
    }
