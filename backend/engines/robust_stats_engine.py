"""
WealthOS Robust Statistics Engine
Outlier detection, robust regression, distance metrics.

References:
  - Mahalanobis (1936): multivariate distance
  - Liu et al. (2008): Isolation Forest
  - Huber (1964): robust M-estimators
"""

import numpy as np
import pandas as pd
from scipy import stats, linalg
from typing import Dict, List, Optional

try:
    from sklearn.ensemble    import IsolationForest
    from sklearn.covariance  import MinCovDet, EmpiricalCovariance
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False


# ════════════════════════════════════════════════════════════════
# UNIVARIATE OUTLIER DETECTION
# ════════════════════════════════════════════════════════════════

def z_score_outliers(returns: pd.Series, threshold: float = 3.0) -> Dict:
    """
    Standard Z-score outlier detection.
    Flags returns more than `threshold` standard deviations from the mean.

    Assumes normality — use only for quick screening.
    """
    series = returns.dropna()
    if len(series) < 10:
        return {"error": "insufficient_data"}

    mu      = float(series.mean())
    sigma   = float(series.std(ddof=1))
    z       = (series - mu) / sigma if sigma > 0 else series * 0
    outliers = z[z.abs() > threshold]

    return {
        "n_outliers":          int(len(outliers)),
        "outlier_indices":     [str(idx) for idx in outliers.index][:50],
        "outlier_values_pct":  [round(float(v) * 100, 3) for v in outliers.values][:50],
        "threshold_sigma":     threshold,
        "methodology":         "z_score_normality_based",
    }


def iqr_outliers(returns: pd.Series, multiplier: float = 1.5) -> Dict:
    """
    Tukey's IQR rule. Distribution-free, robust to skew.

    Outlier if: x < Q1 − k·IQR  or  x > Q3 + k·IQR
    """
    series = returns.dropna()
    if len(series) < 10:
        return {"error": "insufficient_data"}

    q1, q3 = series.quantile([0.25, 0.75])
    iqr    = q3 - q1
    lower  = q1 - multiplier * iqr
    upper  = q3 + multiplier * iqr
    outliers = series[(series < lower) | (series > upper)]

    return {
        "n_outliers":         int(len(outliers)),
        "lower_bound_pct":    round(float(lower) * 100, 3),
        "upper_bound_pct":    round(float(upper) * 100, 3),
        "outlier_indices":    [str(idx) for idx in outliers.index][:50],
        "multiplier":         multiplier,
        "methodology":        "tukey_iqr_rule",
    }


# ════════════════════════════════════════════════════════════════
# MULTIVARIATE OUTLIER DETECTION
# ════════════════════════════════════════════════════════════════

def mahalanobis_outliers(returns: pd.DataFrame, alpha: float = 0.025) -> Dict:
    """
    Mahalanobis distance — multivariate outlier detection.

    d_M(x) = √((x − μ)ᵀ Σ⁻¹ (x − μ))

    Under multivariate normality, d² follows χ²(p) where p is dimensions.
    Flag points exceeding the χ² critical value at `alpha`.

    Standard approach for detecting unusual return combinations.
    """
    X = returns.dropna().values
    n, p = X.shape
    if n < 30 or p < 2:
        return {"error": "insufficient_data"}

    mu  = X.mean(axis=0)
    cov = np.cov(X.T)
    try:
        inv = linalg.inv(cov)
    except linalg.LinAlgError:
        return {"error": "singular_covariance"}

    centered = X - mu
    d2       = np.einsum("ij,jk,ik->i", centered, inv, centered)
    critical = stats.chi2.ppf(1 - alpha, df=p)
    is_out   = d2 > critical

    return {
        "n_outliers":          int(is_out.sum()),
        "critical_value":      round(float(critical), 3),
        "max_distance_sq":     round(float(d2.max()), 3),
        "outlier_indices":     [int(i) for i in np.where(is_out)[0]][:50],
        "alpha":               alpha,
        "dimensions":          int(p),
        "methodology":         "mahalanobis_chi2_test",
    }


def robust_mahalanobis(returns: pd.DataFrame, alpha: float = 0.025) -> Dict:
    """
    Robust Mahalanobis using MCD covariance.
    Resistant to up to 50% contamination. Critical for detecting outliers
    in the presence of clustered outliers (which standard Mahalanobis misses).
    """
    if not SKLEARN_AVAILABLE:
        return {"error": "sklearn_not_installed"}

    X = returns.dropna().values
    n, p = X.shape
    if n < 30 or p < 2:
        return {"error": "insufficient_data"}

    mcd = MinCovDet(random_state=42).fit(X)
    d2  = mcd.mahalanobis(X)
    critical = stats.chi2.ppf(1 - alpha, df=p)
    is_out   = d2 > critical

    return {
        "n_outliers":      int(is_out.sum()),
        "critical_value":  round(float(critical), 3),
        "outlier_indices": [int(i) for i in np.where(is_out)[0]][:50],
        "methodology":     "robust_mahalanobis_mcd",
    }


def isolation_forest_outliers(returns: pd.DataFrame,
                               contamination: float = 0.05) -> Dict:
    """
    Isolation Forest (Liu et al. 2008).
    Tree-based anomaly detection. Doesn't assume any distribution.

    Splits data randomly — outliers get isolated faster (shorter path length).
    Works well in high dimensions and with non-Gaussian data.
    """
    if not SKLEARN_AVAILABLE:
        return {"error": "sklearn_not_installed"}

    X = returns.dropna().values
    if X.shape[0] < 30:
        return {"error": "insufficient_data"}

    iso     = IsolationForest(contamination=contamination, random_state=42, n_estimators=200)
    labels  = iso.fit_predict(X)         # +1 normal, -1 outlier
    scores  = iso.score_samples(X)       # higher = more normal

    is_out  = labels == -1
    return {
        "n_outliers":          int(is_out.sum()),
        "outlier_indices":     [int(i) for i in np.where(is_out)[0]][:50],
        "anomaly_scores":      [round(float(s), 4) for s in scores[:50]],
        "contamination_param": contamination,
        "methodology":         "isolation_forest_liu_2008",
    }


# ════════════════════════════════════════════════════════════════
# ROBUST REGRESSION
# ════════════════════════════════════════════════════════════════

def huber_regression(y: pd.Series, x: pd.Series, k: float = 1.345) -> Dict:
    """
    Huber M-estimator regression.
    Combines OLS for small residuals and L1 for large residuals.
    Resistant to outliers in y; default k=1.345 gives 95% efficiency vs OLS under normality.
    """
    aligned = pd.concat([y, x], axis=1).dropna()
    if len(aligned) < 20:
        return {"error": "insufficient_data"}

    y_arr = aligned.iloc[:, 0].values
    x_arr = aligned.iloc[:, 1].values
    n     = len(y_arr)

    # Initial OLS
    A      = np.column_stack([np.ones(n), x_arr])
    beta, *_ = np.linalg.lstsq(A, y_arr, rcond=None)

    # Iteratively Reweighted Least Squares
    for _ in range(20):
        residuals = y_arr - A @ beta
        scale     = 1.4826 * np.median(np.abs(residuals - np.median(residuals)))  # MAD
        if scale == 0:
            break
        u         = residuals / scale
        weights   = np.where(np.abs(u) <= k, 1.0, k / np.abs(u))
        W         = np.diag(weights)
        AtWA      = A.T @ W @ A
        AtWy      = A.T @ W @ y_arr
        try:
            beta_new = linalg.solve(AtWA, AtWy)
        except Exception:
            break
        if np.allclose(beta, beta_new, atol=1e-6):
            beta = beta_new
            break
        beta = beta_new

    fitted = A @ beta
    ss_res = float(((y_arr - fitted) ** 2).sum())
    ss_tot = float(((y_arr - y_arr.mean()) ** 2).sum())
    r2     = 1 - ss_res / ss_tot if ss_tot > 0 else 0

    return {
        "intercept_alpha": round(float(beta[0]), 6),
        "slope_beta":      round(float(beta[1]), 4),
        "r_squared":       round(float(r2), 4),
        "n_observations":  int(n),
        "tuning_k":        k,
        "methodology":     "huber_m_estimator_irls",
    }


# ════════════════════════════════════════════════════════════════
# DATA QUALITY METRICS
# ════════════════════════════════════════════════════════════════

def data_quality_report(returns: pd.DataFrame) -> Dict:
    """
    Comprehensive data quality assessment.
    Critical before running any analytics.
    """
    out = {
        "n_observations":   int(len(returns)),
        "n_assets":         int(returns.shape[1]),
        "missing_pct":      round(float(returns.isnull().mean().mean() * 100), 2),
        "zero_return_pct":  round(float((returns == 0).mean().mean() * 100), 2),
        "constant_columns": [c for c in returns.columns
                              if returns[c].nunique() <= 1],
        "duplicate_rows":   int(returns.duplicated().sum()),
        "date_gaps_max":    _max_date_gap_days(returns),
        "methodology":      "data_quality_v1",
    }

    # Per-column return-distribution sanity checks
    extreme_returns = {}
    for col in returns.columns:
        s = returns[col].dropna()
        if len(s) > 10:
            max_abs = float(s.abs().max())
            if max_abs > 0.30:  # >30% in one period
                extreme_returns[col] = round(max_abs * 100, 2)
    out["extreme_single_period_returns_pct"] = extreme_returns

    return out


def _max_date_gap_days(returns: pd.DataFrame) -> int:
    if not isinstance(returns.index, pd.DatetimeIndex):
        return 0
    diffs = returns.index.to_series().diff().dropna()
    if len(diffs) == 0:
        return 0
    return int(diffs.max().days)
