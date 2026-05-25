"""
WealthOS Regime Detection Engine
Bull/bear regimes, structural breaks, dynamic state estimation.

References:
  - Hamilton (1989): "A New Approach to the Economic Analysis of Nonstationary Time
    Series and the Business Cycle" — Markov-switching
  - Chow (1960): structural break test
  - Bai & Perron (2003): multiple structural breaks
  - Kalman (1960): linear state-space filtering
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional

try:
    from hmmlearn import hmm
    HMM_AVAILABLE = True
except ImportError:
    HMM_AVAILABLE = False

try:
    from sklearn.preprocessing import StandardScaler
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False


# ════════════════════════════════════════════════════════════════
# HIDDEN MARKOV MODEL — Bull/Bear Regime Detection
# ════════════════════════════════════════════════════════════════

def fit_hmm_regimes(returns: pd.Series, n_states: int = 2,
                    covariance_type: str = "full") -> Dict:
    """
    Hidden Markov Model with Gaussian emissions.
    Standard approach for regime identification in financial time series.

    States are typically interpreted as:
      n_states=2: bull / bear
      n_states=3: bull / sideways / bear
      n_states=4: bull / recovery / sideways / crash
    """
    if not HMM_AVAILABLE:
        return {"error": "hmmlearn_not_installed"}

    series = returns.dropna()
    if len(series) < 100:
        return {"error": "insufficient_data"}

    X = series.values.reshape(-1, 1)

    try:
        model = hmm.GaussianHMM(
            n_components=n_states,
            covariance_type=covariance_type,
            n_iter=100,
            random_state=42,
        )
        model.fit(X)

        # Predict the regime at each timestep
        states         = model.predict(X)
        state_probs    = model.predict_proba(X)
        current_state  = int(states[-1])
        current_probs  = state_probs[-1].tolist()

        # Characterize each regime
        regime_stats = []
        for s in range(n_states):
            mask = states == s
            regime_returns = series[mask] if mask.sum() > 0 else pd.Series([0.0])
            mean_ann = float(regime_returns.mean() * 252 * 100)
            vol_ann  = float(regime_returns.std() * np.sqrt(252) * 100)
            regime_stats.append({
                "state":             s,
                "label":             _regime_label(mean_ann, vol_ann),
                "mean_return_pct":   round(mean_ann, 2),
                "volatility_pct":    round(vol_ann, 2),
                "frequency_pct":     round(float(mask.mean() * 100), 2),
                "avg_duration_days": round(_avg_duration(states, s), 1),
                "transition_probs":  [round(float(p), 3)
                                     for p in model.transmat_[s]],
            })

        return {
            "n_states":          n_states,
            "current_state":     current_state,
            "current_state_label":_regime_label(
                                    regime_stats[current_state]["mean_return_pct"],
                                    regime_stats[current_state]["volatility_pct"]),
            "current_state_probs":[round(p, 3) for p in current_probs],
            "regimes":           regime_stats,
            "transition_matrix": model.transmat_.tolist(),
            "log_likelihood":    round(float(model.score(X)), 3),
            "aic":               round(float(2 * (n_states * (n_states + 2) - 1)
                                              - 2 * model.score(X)), 2),
            "methodology":       "gaussian_hmm_baum_welch_em",
        }
    except Exception as e:
        return {"error": f"hmm_fit_failed: {str(e)}"}


def _regime_label(mean_ann_pct: float, vol_ann_pct: float) -> str:
    """Heuristic labeling of regimes."""
    if mean_ann_pct > 8 and vol_ann_pct < 20:
        return "bull_low_vol"
    if mean_ann_pct > 8:
        return "bull_high_vol"
    if mean_ann_pct < -8:
        return "bear"
    if vol_ann_pct > 30:
        return "crisis_high_vol"
    return "sideways"


def _avg_duration(states: np.ndarray, target: int) -> float:
    """Average consecutive run-length of a state."""
    in_state = (states == target).astype(int)
    if in_state.sum() == 0:
        return 0.0
    runs = []
    current = 0
    for s in in_state:
        if s == 1:
            current += 1
        else:
            if current > 0:
                runs.append(current)
            current = 0
    if current > 0:
        runs.append(current)
    return float(np.mean(runs)) if runs else 0.0


# ════════════════════════════════════════════════════════════════
# STRUCTURAL BREAK TESTS
# ════════════════════════════════════════════════════════════════

def chow_test(returns: pd.Series, breakpoint: int) -> Dict:
    """
    Chow (1960) test for a single structural break at a known point.
    F-test comparing pooled regression to two-segment regression.

    Use when you suspect a break at a specific event (e.g., Covid March 2020).
    """
    series = returns.dropna().values
    n = len(series)
    if n < 30 or breakpoint < 10 or breakpoint > n - 10:
        return {"error": "insufficient_data_or_invalid_breakpoint"}

    # Pooled
    y         = series
    X         = np.column_stack([np.ones(n), np.arange(n)])
    coef, *_  = np.linalg.lstsq(X, y, rcond=None)
    ssr_pool  = float(((y - X @ coef) ** 2).sum())

    # Segment 1
    y1 = series[:breakpoint]
    X1 = np.column_stack([np.ones(breakpoint), np.arange(breakpoint)])
    c1, *_ = np.linalg.lstsq(X1, y1, rcond=None)
    ssr1 = float(((y1 - X1 @ c1) ** 2).sum())

    # Segment 2
    n2 = n - breakpoint
    y2 = series[breakpoint:]
    X2 = np.column_stack([np.ones(n2), np.arange(n2)])
    c2, *_ = np.linalg.lstsq(X2, y2, rcond=None)
    ssr2 = float(((y2 - X2 @ c2) ** 2).sum())

    k = 2  # parameters
    f_stat = ((ssr_pool - (ssr1 + ssr2)) / k) / ((ssr1 + ssr2) / (n - 2 * k))

    from scipy import stats as ss
    p_value = 1 - ss.f.cdf(f_stat, k, n - 2 * k)

    return {
        "f_statistic":     round(float(f_stat), 4),
        "p_value":         round(float(p_value), 5),
        "break_detected":  bool(p_value < 0.05),
        "breakpoint":      int(breakpoint),
        "methodology":     "chow_1960_structural_break_test",
    }


def bai_perron_breaks(returns: pd.Series, max_breaks: int = 3,
                      min_segment: int = 30) -> Dict:
    """
    Bai & Perron (1998/2003) — Multiple structural break detection.

    Unlike Chow (single known break) or CUSUM (drift), Bai-Perron finds the
    globally optimal set of break dates simultaneously, using dynamic programming
    to minimize the sum of squared residuals across all segments.

    Algorithm:
      1. Compute RSS for all admissible sub-samples [i,j] (min_segment gap)
      2. Dynamic programming: OPT(m,T) = min_{m≤τ≤T-min_seg}[OPT(m-1,τ) + RSS(τ+1,T)]
      3. Select m via Bayesian Information Criterion

    Output: break dates, segment means, optimal break count, BIC scores.
    """
    series = returns.dropna()
    n = len(series)
    if n < max_breaks * min_segment + min_segment:
        return {"error": "insufficient_data_for_break_count"}

    y = series.values

    # Pre-compute RSS for all [i, j] sub-samples
    rss_table = np.full((n, n), np.inf)
    for i in range(n):
        for j in range(i + min_segment - 1, min(i + n, n)):
            seg = y[i: j + 1]
            rss_table[i, j] = float(np.sum((seg - seg.mean()) ** 2))

    # Dynamic programming for up to max_breaks breaks
    bic_scores = {}
    break_sets  = {}

    for m in range(0, max_breaks + 1):
        n_segs = m + 1

        if m == 0:
            # No breaks — full sample
            dp     = {0: 0.0}
            parent = {0: []}
            total_rss = rss_table[0, n - 1]
            bic_scores[0] = (n * np.log(total_rss / n + 1e-12) +
                             n_segs * 2 * np.log(n))
            break_sets[0] = []
            continue

        # dp[j] = min RSS ending at position j with m segments
        dp_prev = {0: 0.0}
        prev_breaks: dict = {0: []}

        for seg_num in range(1, n_segs + 1):
            dp_curr = {}
            curr_breaks = {}
            for j in range(min_segment * seg_num - 1, n):
                best_rss   = np.inf
                best_split = -1
                start_range = min_segment * (seg_num - 1) - 1
                for k in range(max(start_range, 0), j - min_segment + 1):
                    if k not in dp_prev:
                        continue
                    candidate = dp_prev[k] + rss_table[k + 1 if k > 0 else 0, j]
                    if candidate < best_rss:
                        best_rss   = candidate
                        best_split = k
                if best_split >= 0:
                    dp_curr[j]    = best_rss
                    curr_breaks[j] = prev_breaks.get(best_split, []) + [best_split]
            dp_prev     = dp_curr
            prev_breaks = curr_breaks

        if n - 1 not in dp_prev:
            continue

        total_rss = dp_prev[n - 1]
        bic       = n * np.log(total_rss / n + 1e-12) + (m + 1) * 2 * np.log(n)
        bic_scores[m]   = bic
        raw_breaks       = prev_breaks.get(n - 1, [])
        break_sets[m]    = sorted([int(b) for b in raw_breaks if 0 < b < n - 1])

    # Select optimal m by minimum BIC
    optimal_m = min(bic_scores, key=bic_scores.get) if bic_scores else 0
    best_breaks = break_sets.get(optimal_m, [])

    # Build segment summaries
    breakpoints = [0] + best_breaks + [n]
    segments = []
    for i in range(len(breakpoints) - 1):
        seg = y[breakpoints[i]: breakpoints[i + 1]]
        segments.append({
            "start_idx":  int(breakpoints[i]),
            "end_idx":    int(breakpoints[i + 1] - 1),
            "length":     len(seg),
            "mean_return":round(float(seg.mean() * 252 * 100), 3),
            "vol_ann":    round(float(seg.std() * np.sqrt(252) * 100), 3),
        })

    # Convert break indices to approximate dates if possible
    dates = None
    if hasattr(series.index, 'strftime'):
        dates = [series.index[b].strftime('%Y-%m-%d')
                 for b in best_breaks if 0 < b < n]

    return {
        "optimal_n_breaks":    int(optimal_m),
        "break_indices":       best_breaks,
        "break_dates":         dates,
        "bic_by_breaks":       {k: round(v, 2) for k, v in bic_scores.items()},
        "segments":            segments,
        "methodology":         "bai_perron_2003_dynamic_programming",
    }


def cusum_test(returns: pd.Series) -> Dict:
    """
    Cumulative sum (CUSUM) test for parameter stability.
    Identifies drift in mean. Used to detect regime changes.
    """
    series = returns.dropna()
    if len(series) < 30:
        return {"error": "insufficient_data"}

    mu       = float(series.mean())
    sigma    = float(series.std(ddof=1))
    standardized = (series - mu) / sigma if sigma > 0 else series
    cusum    = standardized.cumsum()
    cusum_max = float(cusum.abs().max())

    n = len(series)
    crit_5pct = 1.358 * np.sqrt(n)  # Brownian bridge approximation
    break_detected = cusum_max > crit_5pct

    # Most likely break location
    break_idx = int(cusum.abs().idxmax()) if hasattr(cusum.abs(), "idxmax") else int(cusum.abs().values.argmax())

    return {
        "cusum_max":          round(cusum_max, 3),
        "critical_value_5pct":round(crit_5pct, 3),
        "break_detected":     bool(break_detected),
        "n_observations":     int(n),
        "methodology":        "recursive_cusum",
    }


# ════════════════════════════════════════════════════════════════
# KALMAN FILTER — Dynamic Linear Models
# ════════════════════════════════════════════════════════════════

def kalman_dynamic_beta(asset_returns: pd.Series,
                         benchmark_returns: pd.Series) -> Dict:
    """
    Time-varying CAPM beta via Kalman filter.
    Allows beta to drift over time — more realistic than rolling-window beta.

    State equation: β_t = β_{t-1} + ε_t  (random walk)
    Observation:    r_t = α + β_t · r_m_t + η_t

    Used in pairs trading and dynamic hedge ratio estimation.
    """
    aligned = pd.concat([asset_returns, benchmark_returns], axis=1).dropna()
    if len(aligned) < 30:
        return {"error": "insufficient_data"}

    y = aligned.iloc[:, 0].values
    x = aligned.iloc[:, 1].values
    n = len(y)

    # Initial beta via OLS
    beta0 = float(np.cov(y, x)[0, 1] / np.var(x))

    # Kalman parameters
    Q = 0.001    # process noise (how much β can drift per step)
    R = float(np.var(y - beta0 * x))  # observation noise
    P = 1.0      # initial uncertainty

    betas = np.zeros(n)
    beta  = beta0

    for t in range(n):
        # Predict
        P_pred = P + Q

        # Update
        K       = P_pred * x[t] / (x[t]**2 * P_pred + R) if (x[t]**2 * P_pred + R) > 0 else 0
        beta    = beta + K * (y[t] - beta * x[t])
        P       = (1 - K * x[t]) * P_pred
        betas[t] = beta

    return {
        "initial_beta":   round(float(beta0), 4),
        "current_beta":   round(float(betas[-1]), 4),
        "mean_beta":      round(float(betas.mean()), 4),
        "beta_std":       round(float(betas.std()), 4),
        "beta_min":       round(float(betas.min()), 4),
        "beta_max":       round(float(betas.max()), 4),
        "beta_path_last20": [round(float(b), 4) for b in betas[-20:]],
        "process_noise_Q": Q,
        "observation_noise_R": round(float(R), 6),
        "methodology":    "kalman_filter_random_walk_beta",
    }


# ════════════════════════════════════════════════════════════════
# MASTER REPORT
# ════════════════════════════════════════════════════════════════

def compute_regime_report(returns: pd.Series,
                           benchmark_returns: Optional[pd.Series] = None) -> Dict:
    """Full regime / state analysis report."""
    out = {}
    if len(returns) < 100:
        return {"error": "insufficient_data"}

    out["hmm_2state"]   = fit_hmm_regimes(returns, n_states=2)
    out["hmm_3state"]   = fit_hmm_regimes(returns, n_states=3)
    out["cusum_test"]   = cusum_test(returns)

    # Bai-Perron multiple structural breaks (computationally heavier — capped at 2)
    if len(returns) >= 120:
        try:
            out["bai_perron_breaks"] = bai_perron_breaks(returns, max_breaks=2, min_segment=40)
        except Exception:
            out["bai_perron_breaks"] = {"error": "computation_failed"}

    if benchmark_returns is not None and len(benchmark_returns) >= 30:
        out["kalman_dynamic_beta"] = kalman_dynamic_beta(returns, benchmark_returns)

    out["methodology_version"] = "regime_v2.0"
    return out
