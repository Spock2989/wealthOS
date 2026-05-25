"""
WealthOS Risk Models Engine
Institutional-tier covariance estimation and tail risk modeling.

References:
  - Ledoit & Wolf (2004): "Honey, I shrunk the sample covariance matrix"
  - Rousseeuw (1984): Minimum Covariance Determinant
  - McNeil, Frey, Embrechts (2015): "Quantitative Risk Management" — EVT
  - Hill (1975): tail index estimator
  - Sklar's theorem: copulas
"""

import numpy as np
import pandas as pd
from scipy import stats, optimize
from typing import Dict, Optional, Tuple

try:
    from sklearn.covariance import LedoitWolf, MinCovDet, OAS
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False


# ════════════════════════════════════════════════════════════════
# COVARIANCE ESTIMATION
# ════════════════════════════════════════════════════════════════

def ledoit_wolf_covariance(returns: pd.DataFrame) -> Dict:
    """
    Ledoit-Wolf optimal shrinkage covariance estimator.

    The sample covariance matrix is notoriously ill-conditioned when N > T or even
    N close to T. Ledoit-Wolf shrinks the sample covariance toward a structured
    target (constant correlation), with an analytically optimal shrinkage intensity.

    Σ̂ = δ·F + (1−δ)·S
    where δ is optimal shrinkage, F is target, S is sample covariance.

    Used by every serious quant fund. Critical for portfolios with >30 assets.
    """
    if not SKLEARN_AVAILABLE:
        return {"error": "sklearn_not_installed"}

    X = returns.dropna().values
    if X.shape[0] < 20 or X.shape[1] < 2:
        return {"error": "insufficient_data"}

    lw = LedoitWolf().fit(X)
    return {
        "covariance":          lw.covariance_.tolist(),
        "shrinkage_intensity": round(float(lw.shrinkage_), 4),
        "n_features":          int(X.shape[1]),
        "n_samples":           int(X.shape[0]),
        "methodology":         "ledoit_wolf_2004",
    }


def oracle_approx_shrinkage(returns: pd.DataFrame) -> Dict:
    """
    Oracle Approximating Shrinkage (Chen et al. 2010).
    Improvement over Ledoit-Wolf when returns are Gaussian — faster convergence.
    """
    if not SKLEARN_AVAILABLE:
        return {"error": "sklearn_not_installed"}

    X = returns.dropna().values
    if X.shape[0] < 20:
        return {"error": "insufficient_data"}

    oas = OAS().fit(X)
    return {
        "covariance":          oas.covariance_.tolist(),
        "shrinkage_intensity": round(float(oas.shrinkage_), 4),
        "methodology":         "oracle_approximating_shrinkage_chen_2010",
    }


def mcd_robust_covariance(returns: pd.DataFrame, support_fraction: float = 0.75) -> Dict:
    """
    Minimum Covariance Determinant (Rousseeuw 1984).
    Robust covariance estimator — finds the h-subset of observations with smallest
    covariance determinant. Resistant to up to 50% outliers.

    Critical for Indian markets where occasional crash days are non-Gaussian outliers.
    """
    if not SKLEARN_AVAILABLE:
        return {"error": "sklearn_not_installed"}

    X = returns.dropna().values
    if X.shape[0] < 30:
        return {"error": "insufficient_data"}

    mcd = MinCovDet(support_fraction=support_fraction, random_state=42).fit(X)
    return {
        "covariance":   mcd.covariance_.tolist(),
        "location":     mcd.location_.tolist(),
        "outlier_mask": (~mcd.support_).tolist(),
        "n_outliers":   int((~mcd.support_).sum()),
        "methodology":  "minimum_covariance_determinant_rousseeuw_1984",
    }


def shrinkage_to_identity(returns: pd.DataFrame, intensity: float = 0.5) -> np.ndarray:
    """
    Manual shrinkage toward identity matrix.
    Σ̂ = (1−δ)·S + δ·tr(S)/N · I
    Simple but effective when nothing else is available.
    """
    S          = returns.dropna().cov().values
    n          = S.shape[0]
    avg_var    = np.trace(S) / n
    target     = avg_var * np.eye(n)
    return (1 - intensity) * S + intensity * target


# ════════════════════════════════════════════════════════════════
# EXTREME VALUE THEORY (TAIL RISK)
# ════════════════════════════════════════════════════════════════

def hill_estimator(returns: pd.Series, k: Optional[int] = None) -> Dict:
    """
    Hill estimator of the tail index α.
    Returns are assumed to follow a power-law in the tail: P(X > x) ~ x^(-α).

    α < 2  → infinite variance (very fat tails)
    α < 4  → infinite kurtosis
    Typical equity: α ≈ 3-4

    Lower α = fatter tails = more extreme events than Gaussian predicts.
    """
    # Use negative returns (losses) for left-tail risk
    losses = -returns.dropna()
    losses = losses[losses > 0]   # only positive losses
    if len(losses) < 30:
        return {"error": "insufficient_data"}

    sorted_losses = np.sort(losses)[::-1]
    n = len(sorted_losses)

    if k is None:
        # Heuristic: k = sqrt(n)
        k = int(np.sqrt(n))

    k = min(k, n - 1)
    log_ratios = np.log(sorted_losses[:k]) - np.log(sorted_losses[k])
    alpha_hat  = 1.0 / log_ratios.mean()

    return {
        "tail_index_alpha":     round(float(alpha_hat), 3),
        "interpretation":       _interpret_alpha(alpha_hat),
        "k_order_statistics":   int(k),
        "threshold":            round(float(sorted_losses[k]), 5),
        "methodology":          "hill_estimator_1975",
    }


def _interpret_alpha(alpha: float) -> str:
    if alpha < 2:  return "extreme_fat_tails_infinite_variance"
    if alpha < 3:  return "very_fat_tails"
    if alpha < 4:  return "fat_tails_typical_equity"
    if alpha < 5:  return "moderate_tails"
    return "near_gaussian"


def fit_generalized_pareto(returns: pd.Series, threshold_quantile: float = 0.95) -> Dict:
    """
    Peaks-Over-Threshold (POT) method with Generalized Pareto Distribution.

    Theory: For high threshold u, excesses (X - u | X > u) follow GPD(ξ, σ).
      - ξ > 0: heavy-tailed (Fréchet domain)
      - ξ = 0: exponential-tailed (Gumbel)
      - ξ < 0: bounded (Weibull)

    This is the modern gold standard for tail risk (regulatory FRTB approach).
    """
    losses = -returns.dropna()
    if len(losses) < 50:
        return {"error": "insufficient_data"}

    threshold = float(losses.quantile(threshold_quantile))
    excesses  = losses[losses > threshold] - threshold

    if len(excesses) < 20:
        return {"error": "insufficient_tail_observations",
                "n_excesses": len(excesses)}

    # MLE fit of GPD parameters
    shape, loc, scale = stats.genpareto.fit(excesses, floc=0)

    n          = len(losses)
    n_excesses = len(excesses)

    return {
        "shape_xi":          round(float(shape), 4),
        "scale_sigma":       round(float(scale), 6),
        "threshold_u":       round(float(threshold), 5),
        "threshold_quantile":threshold_quantile,
        "n_excesses":        int(n_excesses),
        "tail_type":         _gpd_tail_type(shape),
        "expected_excess":   round(float(scale / (1 - shape)), 6)
                              if shape < 1 else float("inf"),
        "methodology":       "peaks_over_threshold_gpd_mle",
    }


def _gpd_tail_type(xi: float) -> str:
    if xi > 0.1:  return "heavy_tailed_frechet"
    if xi > -0.1: return "exponential_gumbel"
    return "bounded_weibull"


def evt_var_cvar(returns: pd.Series,
                 confidence: float = 0.99,
                 threshold_quantile: float = 0.95) -> Dict:
    """
    EVT-based VaR and CVaR using fitted GPD.

    VaR_p = u + (σ/ξ) · [((n/N_u)·(1-p))^(-ξ) - 1]
    ES_p  = VaR_p/(1-ξ) + (σ - ξ·u)/(1-ξ)

    More accurate than historical VaR for extreme quantiles (>99%) where
    historical method runs out of observations.
    """
    losses = -returns.dropna()
    n      = len(losses)
    if n < 50:
        return {"error": "insufficient_data"}

    gpd = fit_generalized_pareto(returns, threshold_quantile)
    if "error" in gpd:
        return gpd

    u   = gpd["threshold_u"]
    xi  = gpd["shape_xi"]
    sig = gpd["scale_sigma"]
    nu  = gpd["n_excesses"]

    # EVT VaR formula
    if abs(xi) < 1e-6:
        var_p = u + sig * np.log((n / nu) * (1 - confidence))
    else:
        var_p = u + (sig / xi) * (((n / nu) * (1 - confidence)) ** (-xi) - 1)

    # Expected Shortfall (ES) above VaR
    if xi < 1:
        es_p = (var_p / (1 - xi)) + (sig - xi * u) / (1 - xi)
    else:
        es_p = float("inf")

    return {
        "var_pct":             round(float(-var_p) * 100, 4),   # negative = loss
        "expected_shortfall_pct": round(float(-es_p) * 100, 4),
        "confidence_level":    confidence,
        "tail_type":           gpd["tail_type"],
        "shape_xi":            xi,
        "n_tail_observations": nu,
        "methodology":         "evt_pot_gpd_var_cvar",
    }


def evt_var_gpd(returns: pd.Series, confidence: float = 0.95) -> Dict:
    """
    Alias for evt_var_cvar — exposes EVT VaR in the format expected by
    compute_risk_summary in risk_engine.py.

    Returns keys:
      var_evt   — 1-day VaR (as negative fraction, e.g. -0.023)
      es_evt    — 1-day ES  (as negative fraction)
      xi_shape  — GPD shape parameter (tail heaviness)
      tail_heavy — True if xi > 0.2 (heavy tails confirmed)
    """
    result = evt_var_cvar(returns, confidence=confidence)
    if "error" in result:
        return result

    var_pct = result.get("var_pct", 0)   # stored as %, positive number
    es_pct  = result.get("expected_shortfall_pct", 0)
    xi      = result.get("shape_xi", 0)

    return {
        "var_evt":   round(-abs(var_pct) / 100, 6),   # return as fraction, negative
        "es_evt":    round(-abs(es_pct)  / 100, 6),
        "xi_shape":  round(xi, 4),
        "tail_heavy": xi > 0.2,
        "methodology": "evt_pot_gpd_mle_var",
    }


# ════════════════════════════════════════════════════════════════
# PCA CONCENTRATION (INSTITUTIONAL DIVERSIFICATION SIGNAL)
# ════════════════════════════════════════════════════════════════

def pca_concentration(returns: pd.DataFrame, n_components: int = 5) -> Dict:
    """
    PCA-based portfolio concentration analysis.

    Decomposes the asset return covariance matrix into principal components.
    The variance explained by each PC reveals how concentrated / diversified
    the portfolio's risk structure really is.

    Interpretation (from spec):
      PC1 > 50% variance → dangerously concentrated (one systemic risk driver)
      PC1 < 25%          → genuinely diversified
      Top 3 PCs < 60%    → institutional-grade diversification

    Also detects "factor crowding": if PC1 has uniform positive loadings across
    all assets, the whole portfolio moves together.

    Returns:
      variance_explained_pct  — list, % variance per PC
      cumulative_explained_pct — cumulative
      pc1_loading_uniformity  — |mean(loading)| / std(loading) — crowding indicator
      concentration_grade     — Diversified | Moderate | Concentrated | Extreme
    """
    df = returns.dropna()
    if df.shape[0] < 30 or df.shape[1] < 2:
        return {"error": "insufficient_data"}

    n_comp = min(n_components, df.shape[1])
    cov    = np.cov(df.values.T)

    # Eigendecomposition (sorted descending)
    eigvals, eigvecs = np.linalg.eigh(cov)
    idx    = np.argsort(eigvals)[::-1]
    eigvals = eigvals[idx]
    eigvecs = eigvecs[:, idx]

    total_var = float(eigvals.sum())
    var_exp   = [float(v / total_var * 100) for v in eigvals[:n_comp]]
    cum_exp   = list(np.cumsum(var_exp))

    # PC1 loading uniformity — measures "crowding"
    pc1_loadings = eigvecs[:, 0]
    uniformity   = float(abs(pc1_loadings.mean()) / (pc1_loadings.std() + 1e-10))

    pc1_pct = var_exp[0]
    if pc1_pct < 25:
        grade = "Diversified"
    elif pc1_pct < 40:
        grade = "Moderate"
    elif pc1_pct < 55:
        grade = "Concentrated"
    else:
        grade = "Extreme_Concentration"

    # Statistical risk: how many PCs needed to explain 80%?
    pcs_for_80pct = int(next((i+1 for i, c in enumerate(cum_exp) if c >= 80),
                              len(cum_exp)))

    return {
        "variance_explained_pct":     [round(v, 2) for v in var_exp],
        "cumulative_explained_pct":   [round(c, 2) for c in cum_exp],
        "pc1_variance_pct":           round(pc1_pct, 2),
        "pc1_loading_uniformity":     round(uniformity, 3),
        "crowding_risk":              uniformity > 0.5,
        "pcs_to_explain_80pct":       pcs_for_80pct,
        "concentration_grade":        grade,
        "n_assets":                   int(df.shape[1]),
        "interpretation":             (
            f"PC1 explains {pc1_pct:.1f}% of portfolio variance. "
            f"Need {pcs_for_80pct} PCs to explain 80%."
        ),
        "methodology":                "pca_covariance_eigendecomposition_v1",
    }


# ════════════════════════════════════════════════════════════════
# COPULA-BASED DEPENDENCE
# ════════════════════════════════════════════════════════════════

def gaussian_copula_correlation(returns: pd.DataFrame) -> Dict:
    """
    Gaussian copula correlation — captures dependence after marginal transformation.
    Convert each series to uniform via empirical CDF, then to standard normal.
    The correlation of the transformed series is the copula correlation.

    Robust to non-linear monotonic transformations.
    """
    df = returns.dropna()
    if df.shape[0] < 30 or df.shape[1] < 2:
        return {"error": "insufficient_data"}

    # Empirical CDF transform
    uniform = df.rank(pct=True)
    # Inverse normal CDF (avoid 0/1)
    uniform = uniform.clip(1e-6, 1 - 1e-6)
    normal  = pd.DataFrame(stats.norm.ppf(uniform.values),
                           columns=df.columns, index=df.index)

    corr_matrix = normal.corr()
    return {
        "copula_correlation_matrix": corr_matrix.values.tolist(),
        "assets":                    list(corr_matrix.columns),
        "average_correlation":       round(float(_upper_tri_mean(corr_matrix)), 4),
        "methodology":               "gaussian_copula_via_empirical_cdf",
    }


def tail_dependence_coefficient(x: pd.Series, y: pd.Series,
                                quantile: float = 0.95) -> Dict:
    """
    Empirical tail dependence coefficient.
    λ_U = lim_{q→1} P(Y > F_Y⁻¹(q) | X > F_X⁻¹(q))

    Measures dependence in the tail — critical for portfolio risk.
    Two assets can have correlation 0.3 in normal times but tail dependence 0.7
    during crises. Gaussian copula misses this; t-copula captures it.
    """
    aligned = pd.concat([x, y], axis=1).dropna()
    if len(aligned) < 50:
        return {"error": "insufficient_data"}

    threshold_x = aligned.iloc[:, 0].quantile(quantile)
    threshold_y = aligned.iloc[:, 1].quantile(quantile)

    x_extreme  = aligned.iloc[:, 0] > threshold_x
    y_extreme  = aligned.iloc[:, 1] > threshold_y

    both       = (x_extreme & y_extreme).sum()
    x_only     = x_extreme.sum()

    lambda_u   = float(both / x_only) if x_only > 0 else 0.0

    # Lower tail dependence
    threshold_x_low = aligned.iloc[:, 0].quantile(1 - quantile)
    threshold_y_low = aligned.iloc[:, 1].quantile(1 - quantile)
    x_low      = aligned.iloc[:, 0] < threshold_x_low
    y_low      = aligned.iloc[:, 1] < threshold_y_low
    both_low   = (x_low & y_low).sum()
    x_low_n    = x_low.sum()
    lambda_l   = float(both_low / x_low_n) if x_low_n > 0 else 0.0

    return {
        "upper_tail_dependence": round(lambda_u, 4),
        "lower_tail_dependence": round(lambda_l, 4),
        "asymmetry":             round(lambda_l - lambda_u, 4),
        "interpretation":        _interpret_tail_dep(lambda_l),
        "quantile_threshold":    quantile,
        "methodology":           "empirical_tail_dependence",
    }


def _interpret_tail_dep(lambda_l: float) -> str:
    if lambda_l < 0.1: return "tail_independent"
    if lambda_l < 0.3: return "weak_tail_dependence"
    if lambda_l < 0.5: return "moderate_tail_dependence"
    return "strong_tail_dependence_crisis_correlated"


# ════════════════════════════════════════════════════════════════
# UTILITIES
# ════════════════════════════════════════════════════════════════

def _upper_tri_mean(corr: pd.DataFrame) -> float:
    n = corr.shape[0]
    if n < 2:
        return 0.0
    mask = np.triu(np.ones((n, n)), k=1).astype(bool)
    return float(corr.values[mask].mean())


# ════════════════════════════════════════════════════════════════
# MASTER REPORT
# ════════════════════════════════════════════════════════════════

def compute_risk_models_report(returns: pd.DataFrame,
                                portfolio_returns: Optional[pd.Series] = None) -> Dict:
    """Full institutional-tier risk model report."""
    out = {}

    if portfolio_returns is not None and len(portfolio_returns) >= 50:
        out["hill_tail_index"] = hill_estimator(portfolio_returns)
        out["evt_gpd_fit"]     = fit_generalized_pareto(portfolio_returns)
        out["evt_var_cvar_99"] = evt_var_cvar(portfolio_returns, confidence=0.99)

    if returns.shape[1] >= 2 and len(returns.dropna()) >= 30:
        out["ledoit_wolf_shrinkage"] = ledoit_wolf_covariance(returns)
        out["oracle_shrinkage"]      = oracle_approx_shrinkage(returns)
        out["robust_mcd_covariance"] = mcd_robust_covariance(returns)
        out["gaussian_copula"]       = gaussian_copula_correlation(returns)
        out["pca_concentration"]     = pca_concentration(returns)

    out["methodology_version"] = "risk_models_v2.0"
    return out
