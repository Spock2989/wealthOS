"""
WealthOS Advanced Optimization Engine
Institutional portfolio construction methods.

References:
  - Black & Litterman (1992): "Global Portfolio Optimization"
  - López de Prado (2016): "Building Diversified Portfolios that Outperform OOS"
    Hierarchical Risk Parity, Journal of Portfolio Management
  - López de Prado (2020): "Machine Learning for Asset Managers" — NCO
  - Michaud (1989): "The Markowitz Optimization Enigma" — resampled frontier
  - Markowitz (1952): "Portfolio Selection"
"""

import numpy as np
import pandas as pd
from scipy import optimize, linalg
from scipy.cluster.hierarchy import linkage, fcluster
from scipy.spatial.distance import squareform
from typing import Dict, Optional, List, Tuple


# ════════════════════════════════════════════════════════════════
# BLACK-LITTERMAN
# ════════════════════════════════════════════════════════════════

def black_litterman(
    market_caps:      np.ndarray,
    cov_matrix:       np.ndarray,
    views_P:          Optional[np.ndarray] = None,
    views_Q:          Optional[np.ndarray] = None,
    views_omega:      Optional[np.ndarray] = None,
    risk_aversion:    float = 2.5,
    tau:              float = 0.025,
    risk_free_rate:   float = 0.0675,
) -> Dict:
    """
    Black-Litterman model — Bayesian update of equilibrium returns with investor views.

    Step 1: Reverse-engineer implied equilibrium returns from market caps:
            Π = δ · Σ · w_mkt

    Step 2: Blend equilibrium with views:
            E[R] = [(τΣ)⁻¹ + P'Ω⁻¹P]⁻¹ · [(τΣ)⁻¹Π + P'Ω⁻¹Q]

    Step 3: Mean-variance optimize using BL expected returns.

    Arguments:
        market_caps:   Vector of market capitalizations (or benchmark weights)
        cov_matrix:    NxN asset covariance matrix
        views_P:       KxN pick matrix (K views over N assets)
        views_Q:       Kx1 view returns
        views_omega:   KxK uncertainty in views (diagonal)
        risk_aversion: δ — typically 2-3 for institutional
        tau:           Scalar of confidence in equilibrium (0.025-0.05 standard)

    Returns posterior expected returns + optimal weights.
    """
    Sigma = np.asarray(cov_matrix)
    n     = Sigma.shape[0]
    mc    = np.asarray(market_caps, dtype=float)
    w_mkt = mc / mc.sum()

    # Step 1: Implied equilibrium returns
    Pi = risk_aversion * Sigma @ w_mkt

    # Step 2: If no views, return equilibrium portfolio
    if views_P is None or views_Q is None:
        return {
            "implied_equilibrium_returns_pct": [round(float(p)*100, 3) for p in Pi],
            "equilibrium_weights":             [round(float(w), 4) for w in w_mkt],
            "posterior_returns_pct":           [round(float(p)*100, 3) for p in Pi],
            "optimal_weights":                 [round(float(w), 4) for w in w_mkt],
            "has_views":                       False,
            "methodology":                     "black_litterman_no_views",
        }

    P = np.asarray(views_P)
    Q = np.asarray(views_Q).flatten()
    if views_omega is None:
        # Idzorek's method: Ω = diag(P · τΣ · P')
        Omega = np.diag(np.diag(P @ (tau * Sigma) @ P.T))
    else:
        Omega = np.asarray(views_omega)

    # Step 3: Posterior returns (Black-Litterman master formula)
    tau_sigma_inv = linalg.inv(tau * Sigma)
    omega_inv     = linalg.inv(Omega)

    M_inv = tau_sigma_inv + P.T @ omega_inv @ P
    M     = linalg.inv(M_inv)
    bl_returns = M @ (tau_sigma_inv @ Pi + P.T @ omega_inv @ Q)

    # Step 4: Posterior covariance and optimal weights
    Sigma_p   = Sigma + M
    w_optimal = linalg.inv(risk_aversion * Sigma_p) @ bl_returns
    # Normalize to sum to 1
    w_optimal = w_optimal / w_optimal.sum()

    return {
        "implied_equilibrium_returns_pct": [round(float(p)*100, 3) for p in Pi],
        "posterior_returns_pct":           [round(float(p)*100, 3) for p in bl_returns],
        "equilibrium_weights":             [round(float(w), 4) for w in w_mkt],
        "optimal_weights":                 [round(float(w), 4) for w in w_optimal],
        "tau":                             tau,
        "risk_aversion_delta":             risk_aversion,
        "n_views":                         int(P.shape[0]),
        "has_views":                       True,
        "methodology":                     "black_litterman_1992_idzorek_omega",
    }


# ════════════════════════════════════════════════════════════════
# HIERARCHICAL RISK PARITY (HRP) — López de Prado 2016
# ════════════════════════════════════════════════════════════════

def hierarchical_risk_parity(returns: pd.DataFrame) -> Dict:
    """
    Hierarchical Risk Parity (HRP) — López de Prado 2016.

    Three steps:
      1. Hierarchical clustering using correlation distance
      2. Quasi-diagonalization of covariance matrix
      3. Recursive bisection allocating inverse-variance weights

    Robust to ill-conditioned covariance matrices (where Markowitz fails).
    No matrix inversion required. Outperforms MVO out-of-sample.
    """
    if returns.shape[0] < 30 or returns.shape[1] < 2:
        return {"error": "insufficient_data"}

    cov  = returns.cov().values
    corr = returns.corr().values
    n    = corr.shape[0]
    assets = list(returns.columns)

    # Step 1: distance matrix and clustering
    # Correlation distance: d_ij = sqrt(0.5 · (1 - ρ_ij))
    dist = np.sqrt(0.5 * (1 - np.clip(corr, -1, 1)))
    np.fill_diagonal(dist, 0)
    condensed = squareform(dist, checks=False)
    link      = linkage(condensed, method="single")

    # Step 2: quasi-diagonalize — get sorted leaf order
    sort_ix = _get_quasi_diag_order(link, n)

    # Step 3: recursive bisection
    weights = pd.Series(1.0, index=sort_ix)
    cluster_items = [sort_ix]

    while cluster_items:
        new_items = []
        for cluster in cluster_items:
            if len(cluster) <= 1:
                continue
            # Bisect
            half = len(cluster) // 2
            left  = cluster[:half]
            right = cluster[half:]

            var_left  = _cluster_variance(cov, left)
            var_right = _cluster_variance(cov, right)

            alpha = 1 - var_left / (var_left + var_right) if (var_left + var_right) > 0 else 0.5

            weights[left]  *= alpha
            weights[right] *= (1 - alpha)

            new_items.append(left)
            new_items.append(right)
        cluster_items = new_items

    # Restore original ordering
    final_weights = weights.reindex(range(n)).values
    final_weights = final_weights / final_weights.sum()

    portfolio_vol = float(np.sqrt(final_weights @ cov @ final_weights))

    return {
        "assets":           assets,
        "weights":          [round(float(w), 4) for w in final_weights],
        "expected_volatility": round(portfolio_vol * np.sqrt(252), 4),
        "cluster_order":    [assets[i] for i in sort_ix],
        "methodology":      "hierarchical_risk_parity_lopez_de_prado_2016",
    }


def _get_quasi_diag_order(link, n: int) -> List[int]:
    """Recover leaf order from hierarchical clustering linkage matrix."""
    link = link.astype(int)
    sort_ix = pd.Series([link[-1, 0], link[-1, 1]])
    num_items = n

    while sort_ix.max() >= num_items:
        sort_ix.index = range(0, sort_ix.shape[0] * 2, 2)
        df0 = sort_ix[sort_ix >= num_items]
        i = df0.index
        j = df0.values - num_items
        sort_ix[i] = link[j, 0]
        df1 = pd.Series(link[j, 1], index=i + 1)
        sort_ix = pd.concat([sort_ix, df1])
        sort_ix = sort_ix.sort_index()
        sort_ix.index = range(sort_ix.shape[0])

    return sort_ix.tolist()


def _cluster_variance(cov: np.ndarray, items: List[int]) -> float:
    """Inverse-variance allocated variance for a cluster."""
    sub_cov = cov[np.ix_(items, items)]
    ivp     = 1.0 / np.diag(sub_cov)
    ivp    /= ivp.sum()
    return float(ivp @ sub_cov @ ivp)


# ════════════════════════════════════════════════════════════════
# RESAMPLED EFFICIENT FRONTIER (Michaud)
# ════════════════════════════════════════════════════════════════

def resampled_efficient_frontier(
    expected_returns: np.ndarray,
    cov_matrix:       np.ndarray,
    n_resamples:      int = 100,
    n_points:         int = 20,
) -> Dict:
    """
    Michaud (1989) Resampled Efficient Frontier.

    Standard Markowitz is extremely sensitive to input estimation errors.
    Resampling repeatedly perturbs inputs, computes the frontier each time,
    and averages the weights — producing a frontier robust to estimation noise.

    Used by Wellington, GMO, large pension funds.
    """
    er  = np.asarray(expected_returns)
    cov = np.asarray(cov_matrix)
    n   = len(er)

    all_weights = np.zeros((n_resamples, n_points, n))
    rng = np.random.default_rng(seed=42)

    for sim in range(n_resamples):
        # Resample by drawing from multivariate normal
        sampled = rng.multivariate_normal(er, cov, size=252)
        er_s    = sampled.mean(axis=0)
        cov_s   = np.cov(sampled.T)

        # Build frontier on this sample
        r_min = float(er_s.min())
        r_max = float(er_s.max())
        targets = np.linspace(r_min, r_max, n_points)

        for i, t in enumerate(targets):
            try:
                w = _solve_min_var_with_target(er_s, cov_s, t)
                all_weights[sim, i] = w
            except Exception:
                all_weights[sim, i] = np.ones(n) / n

    # Average across resamples
    avg_weights = all_weights.mean(axis=0)

    # Evaluate at original inputs
    frontier_points = []
    for i in range(n_points):
        w = avg_weights[i]
        ret = float(w @ er)
        vol = float(np.sqrt(w @ cov @ w))
        frontier_points.append({
            "expected_return": round(ret, 4),
            "volatility":      round(vol, 4),
            "sharpe":          round(ret / vol, 3) if vol > 0 else 0.0,
            "weights":         [round(float(x), 4) for x in w],
        })

    return {
        "frontier_points": frontier_points,
        "n_resamples":     n_resamples,
        "methodology":     "resampled_efficient_frontier_michaud_1989",
    }


def _solve_min_var_with_target(er, cov, target):
    n = len(er)
    def variance(w): return float(w @ cov @ w)
    constraints = [
        {"type": "eq", "fun": lambda w: np.sum(w) - 1},
        {"type": "eq", "fun": lambda w: w @ er - target},
    ]
    bounds = [(0, 1) for _ in range(n)]
    w0 = np.ones(n) / n
    result = optimize.minimize(variance, w0, bounds=bounds, constraints=constraints)
    return result.x


# ════════════════════════════════════════════════════════════════
# NESTED CLUSTERED OPTIMIZATION (López de Prado 2020)
# ════════════════════════════════════════════════════════════════

def nested_clustered_optimization(returns: pd.DataFrame, n_clusters: Optional[int] = None) -> Dict:
    """
    NCO — López de Prado (2020) "Machine Learning for Asset Managers"

    Solves Markowitz instability by clustering assets into groups, optimizing
    within each cluster, then optimizing across clusters.

    Avoids the curse of dimensionality in Σ⁻¹.
    """
    if returns.shape[0] < 30 or returns.shape[1] < 3:
        return {"error": "insufficient_data"}

    corr = returns.corr().values
    cov  = returns.cov().values
    n    = corr.shape[0]
    assets = list(returns.columns)

    if n_clusters is None:
        n_clusters = max(2, int(np.sqrt(n)))

    # Cluster via hierarchical clustering on correlation distance
    dist = np.sqrt(0.5 * (1 - np.clip(corr, -1, 1)))
    np.fill_diagonal(dist, 0)
    condensed = squareform(dist, checks=False)
    link      = linkage(condensed, method="ward")
    labels    = fcluster(link, t=n_clusters, criterion="maxclust")

    # Within-cluster optimization — min variance
    intra_weights = np.zeros(n)
    cluster_returns = {}

    for c in np.unique(labels):
        members = np.where(labels == c)[0]
        sub_cov = cov[np.ix_(members, members)]

        try:
            inv = linalg.inv(sub_cov + 1e-8 * np.eye(len(members)))
            ones = np.ones(len(members))
            w_sub = inv @ ones / (ones @ inv @ ones)
        except Exception:
            w_sub = np.ones(len(members)) / len(members)

        intra_weights[members] = w_sub

        # Compute synthetic cluster return series
        cluster_ret = (returns.iloc[:, members].values @ w_sub)
        cluster_returns[c] = cluster_ret

    # Between-cluster optimization
    cluster_df = pd.DataFrame(cluster_returns)
    cluster_cov = cluster_df.cov().values
    try:
        inv = linalg.inv(cluster_cov + 1e-8 * np.eye(cluster_cov.shape[0]))
        ones = np.ones(cluster_cov.shape[0])
        cluster_weights = inv @ ones / (ones @ inv @ ones)
    except Exception:
        cluster_weights = np.ones(cluster_cov.shape[0]) / cluster_cov.shape[0]

    # Combine
    final_weights = np.zeros(n)
    for idx, c in enumerate(np.unique(labels)):
        members = np.where(labels == c)[0]
        final_weights[members] = intra_weights[members] * cluster_weights[idx]
    final_weights = final_weights / final_weights.sum()

    return {
        "assets":          assets,
        "weights":         [round(float(w), 4) for w in final_weights],
        "cluster_labels":  labels.tolist(),
        "n_clusters":      int(n_clusters),
        "expected_volatility": round(float(np.sqrt(final_weights @ cov @ final_weights) * np.sqrt(252)), 4),
        "methodology":     "nested_clustered_optimization_lopez_de_prado_2020",
    }


# ════════════════════════════════════════════════════════════════
# MASTER OPTIMIZATION REPORT
# ════════════════════════════════════════════════════════════════

def compute_advanced_optimization_report(returns: pd.DataFrame,
                                           market_caps: Optional[np.ndarray] = None) -> Dict:
    """Run all institutional optimization methods on a returns DataFrame."""
    out = {}
    if returns.shape[0] < 30 or returns.shape[1] < 2:
        return {"error": "insufficient_data"}

    out["hierarchical_risk_parity"]    = hierarchical_risk_parity(returns)
    out["nested_clustered_optimization"] = nested_clustered_optimization(returns)

    if market_caps is not None:
        cov = returns.cov().values
        out["black_litterman_equilibrium"] = black_litterman(market_caps, cov)

    out["methodology_version"] = "advanced_opt_v1.0"
    return out
