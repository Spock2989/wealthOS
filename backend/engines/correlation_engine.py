"""
WealthOS Correlation Engine
Pairwise correlations, rolling correlation, PCA-based diversification.
"""

import numpy as np
import pandas as pd
from typing import Dict, List


# ── PAIRWISE CORRELATION ────────────────────────────────────────
def correlation_matrix(returns_df: pd.DataFrame, method: str = "pearson") -> pd.DataFrame:
    """
    Returns NxN correlation matrix. method: 'pearson' or 'spearman' (rank-based).
    Spearman is more robust to outliers — preferred for fat-tailed Indian markets.
    """
    return returns_df.corr(method=method)


def average_correlation(returns_df: pd.DataFrame) -> float:
    """
    Average pairwise correlation. Critical diversification metric.
    <0.3 = well diversified, >0.7 = highly correlated (illusion of diversification).
    """
    corr = returns_df.corr()
    n    = len(corr)
    if n < 2:
        return 0.0
    # Sum upper triangle, exclude diagonal
    upper_tri = corr.where(np.triu(np.ones(corr.shape), k=1).astype(bool))
    return float(upper_tri.stack().mean())


def rolling_correlation(asset1: pd.Series, asset2: pd.Series, window: int = 63) -> pd.Series:
    """3-month rolling correlation. Detects regime shifts (e.g., crisis = correlations → 1)."""
    return asset1.rolling(window).corr(asset2)


# ── DIVERSIFICATION RATIO ───────────────────────────────────────
def diversification_ratio(weights: np.ndarray, cov_matrix: np.ndarray) -> float:
    """
    Diversification Ratio (Choueifaty) = weighted avg vol / portfolio vol.
    >1 always; higher = more diversification benefit.
    Best portfolios reach DR of 1.5–2.5.
    """
    weights        = np.asarray(weights)
    vols           = np.sqrt(np.diag(cov_matrix))
    weighted_vol   = float(weights @ vols)
    portfolio_vol  = float(np.sqrt(weights @ cov_matrix @ weights))
    return float(weighted_vol / portfolio_vol) if portfolio_vol > 0 else 1.0


# ── PCA / EFFECTIVE NUMBER OF BETS ──────────────────────────────
def principal_component_analysis(returns_df: pd.DataFrame, n_components: int = 5) -> Dict:
    """
    PCA on returns. First component usually = market factor.
    Variance explained by PC1 reveals market-driven the portfolio is.
    Effective Number of Bets (ENB) = sum of variance-weighted PCs.
    """
    cleaned = returns_df.dropna()
    if len(cleaned) < 30 or cleaned.shape[1] < 2:
        return {"error": "insufficient_data"}

    centered  = cleaned - cleaned.mean()
    cov       = np.cov(centered.T)
    eigvals, eigvecs = np.linalg.eigh(cov)

    # Sort descending
    idx       = eigvals.argsort()[::-1]
    eigvals   = eigvals[idx]
    eigvecs   = eigvecs[:, idx]

    total     = eigvals.sum()
    var_ratio = eigvals / total if total > 0 else eigvals

    # Effective Number of Bets (Meucci)
    p   = var_ratio[var_ratio > 1e-10]
    enb = float(np.exp(-np.sum(p * np.log(p)))) if len(p) else 1.0

    return {
        "variance_explained": [round(float(v) * 100, 2) for v in var_ratio[:n_components]],
        "cumulative_variance":[round(float(v) * 100, 2)
                               for v in np.cumsum(var_ratio[:n_components])],
        "pc1_dominance_pct":   round(float(var_ratio[0]) * 100, 2),
        "effective_number_of_bets": round(enb, 2),
        "methodology":         "pca_eigenvalue_v1",
    }


# ── CORRELATION CLUSTERS ────────────────────────────────────────
def identify_correlation_clusters(returns_df: pd.DataFrame,
                                  threshold: float = 0.7) -> List[List[str]]:
    """
    Group assets with pairwise correlation above threshold.
    Reveals true diversification clusters.
    """
    corr      = returns_df.corr()
    assets    = corr.columns.tolist()
    clusters  = []
    assigned  = set()

    for asset in assets:
        if asset in assigned:
            continue
        cluster = [asset]
        for other in assets:
            if other != asset and other not in assigned:
                if abs(corr.loc[asset, other]) >= threshold:
                    cluster.append(other)
                    assigned.add(other)
        if len(cluster) > 1:
            clusters.append(cluster)
        assigned.add(asset)

    return clusters


# ── MASTER REPORT ───────────────────────────────────────────────
def compute_correlation_report(returns_df: pd.DataFrame) -> Dict:
    """Full correlation analytics report."""
    if returns_df.empty or returns_df.shape[1] < 2:
        return {"error": "insufficient_data"}

    cleaned = returns_df.dropna()
    avg_corr = average_correlation(cleaned)
    pca      = principal_component_analysis(cleaned)
    clusters = identify_correlation_clusters(cleaned)

    return {
        "average_pairwise_correlation": round(avg_corr, 3),
        "diversification_quality":      _interpret_corr(avg_corr),
        "principal_components":         pca,
        "correlation_clusters":         clusters,
        "n_assets":                     int(returns_df.shape[1]),
        "n_clusters_found":             len(clusters),
        "methodology_version":          "corr_v1.0",
    }


def _interpret_corr(avg: float) -> str:
    if avg < 0.3: return "well_diversified"
    if avg < 0.5: return "moderate"
    if avg < 0.7: return "concentrated"
    return "highly_correlated"
