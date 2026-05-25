"""
WealthOS Fixed Income Engine
Bond math, duration, convexity, yield curve construction.

References:
  - Macaulay (1938): Duration
  - Fisher & Weil (1971): Modified duration, convexity
  - Nelson & Siegel (1987): Parametric yield curve
  - Svensson (1994): Extended Nelson-Siegel
"""

import numpy as np
import pandas as pd
from scipy import optimize
from typing import Dict, List, Optional


# ════════════════════════════════════════════════════════════════
# BOND PRICING
# ════════════════════════════════════════════════════════════════

def bond_price(face: float, coupon_rate: float, ytm: float,
               years_to_maturity: float, coupons_per_year: int = 2) -> float:
    """
    Standard bond pricing formula.

    P = Σ C/(1+y)^t + F/(1+y)^T

    coupon_rate: annual (e.g., 0.07 = 7%)
    ytm:         annual yield-to-maturity
    """
    n_coupons = int(years_to_maturity * coupons_per_year)
    if n_coupons == 0:
        return face / (1 + ytm) ** years_to_maturity

    c_payment = face * coupon_rate / coupons_per_year
    period_y  = ytm / coupons_per_year

    pv_coupons = sum(c_payment / (1 + period_y) ** t for t in range(1, n_coupons + 1))
    pv_face    = face / (1 + period_y) ** n_coupons
    return float(pv_coupons + pv_face)


def yield_to_maturity(price: float, face: float, coupon_rate: float,
                      years_to_maturity: float, coupons_per_year: int = 2) -> float:
    """
    Solve for YTM via Newton-Raphson.
    """
    def price_diff(y):
        return bond_price(face, coupon_rate, y, years_to_maturity, coupons_per_year) - price

    try:
        ytm = optimize.brentq(price_diff, 0.0001, 1.0)
        return float(ytm)
    except Exception:
        return float("nan")


# ════════════════════════════════════════════════════════════════
# DURATION & CONVEXITY
# ════════════════════════════════════════════════════════════════

def macaulay_duration(face: float, coupon_rate: float, ytm: float,
                       years_to_maturity: float, coupons_per_year: int = 2) -> float:
    """
    Macaulay duration — weighted average time to cash flows.
    Time-weighted measure in years.

    D = Σ t·(CF_t / (1+y)^t) / P
    """
    n_coupons   = int(years_to_maturity * coupons_per_year)
    c_payment   = face * coupon_rate / coupons_per_year
    period_y    = ytm / coupons_per_year
    price       = bond_price(face, coupon_rate, ytm, years_to_maturity, coupons_per_year)

    weighted = 0.0
    for t in range(1, n_coupons + 1):
        pv_cf      = c_payment / (1 + period_y) ** t
        weighted  += (t / coupons_per_year) * pv_cf
    weighted += (n_coupons / coupons_per_year) * (face / (1 + period_y) ** n_coupons)

    return float(weighted / price) if price > 0 else 0.0


def modified_duration(face: float, coupon_rate: float, ytm: float,
                       years_to_maturity: float, coupons_per_year: int = 2) -> float:
    """
    Modified duration — % price sensitivity to 1% yield change.
    MD = D_mac / (1 + y/m)

    Price change ≈ −MD · Δy · Price
    """
    d_mac = macaulay_duration(face, coupon_rate, ytm, years_to_maturity, coupons_per_year)
    return float(d_mac / (1 + ytm / coupons_per_year))


def convexity(face: float, coupon_rate: float, ytm: float,
              years_to_maturity: float, coupons_per_year: int = 2) -> float:
    """
    Bond convexity — second-order yield sensitivity.

    ΔP/P ≈ −MD·Δy + 0.5·C·(Δy)²

    Convexity is positive for option-free bonds. Higher convexity = better
    when yields fall, less bad when they rise.
    """
    n_coupons   = int(years_to_maturity * coupons_per_year)
    c_payment   = face * coupon_rate / coupons_per_year
    period_y    = ytm / coupons_per_year
    price       = bond_price(face, coupon_rate, ytm, years_to_maturity, coupons_per_year)

    conv = 0.0
    for t in range(1, n_coupons + 1):
        conv += c_payment * t * (t + 1) / (1 + period_y) ** (t + 2)
    conv += face * n_coupons * (n_coupons + 1) / (1 + period_y) ** (n_coupons + 2)

    return float(conv / (price * coupons_per_year ** 2)) if price > 0 else 0.0


def dv01(face: float, coupon_rate: float, ytm: float,
         years_to_maturity: float, coupons_per_year: int = 2) -> float:
    """
    DV01 (Dollar Value of 1 basis point) — absolute price change per 1bp yield change.
    Standard institutional risk measure for individual bonds.
    """
    p0 = bond_price(face, coupon_rate, ytm, years_to_maturity, coupons_per_year)
    p1 = bond_price(face, coupon_rate, ytm + 0.0001, years_to_maturity, coupons_per_year)
    return float(p0 - p1)


def key_rate_duration(face: float, coupon_rate: float,
                       yield_curve: Dict[float, float],
                       key_tenor: float, years_to_maturity: float,
                       shock_bps: float = 25) -> float:
    """
    Key Rate Duration — sensitivity to a parallel shift in one segment of the yield curve.
    Decomposes total duration across the curve.

    yield_curve: {tenor_years: yield} dict
    """
    base_price   = _price_from_curve(face, coupon_rate, yield_curve, years_to_maturity)

    # Shock only the key tenor
    shocked_curve = dict(yield_curve)
    shocked_curve[key_tenor] = shocked_curve.get(key_tenor, 0.07) + shock_bps / 10000

    shocked_price = _price_from_curve(face, coupon_rate, shocked_curve, years_to_maturity)
    return float((base_price - shocked_price) / (base_price * shock_bps / 10000))


def _price_from_curve(face: float, coupon_rate: float,
                      curve: Dict[float, float], maturity: float) -> float:
    """Price a bond using spot rates from a yield curve."""
    sorted_tenors = sorted(curve.keys())
    sorted_yields = [curve[t] for t in sorted_tenors]
    interp = lambda t: float(np.interp(t, sorted_tenors, sorted_yields))

    n_coupons = int(maturity * 2)
    c = face * coupon_rate / 2
    price = 0.0
    for i in range(1, n_coupons + 1):
        t = i / 2
        y = interp(t)
        price += c / (1 + y / 2) ** (t * 2)
    y_final = interp(maturity)
    price += face / (1 + y_final / 2) ** (maturity * 2)
    return price


# ════════════════════════════════════════════════════════════════
# YIELD CURVE CONSTRUCTION
# ════════════════════════════════════════════════════════════════

def nelson_siegel(t: float, beta0: float, beta1: float, beta2: float,
                  tau: float) -> float:
    """
    Nelson-Siegel (1987) yield curve parametric form.

    y(t) = β₀ + β₁·((1-exp(-t/τ))/(t/τ)) + β₂·(((1-exp(-t/τ))/(t/τ)) − exp(-t/τ))

    β₀ = long-run level
    β₁ = slope (short rate − long rate)
    β₂ = curvature (medium-term hump)
    τ  = decay parameter
    """
    if t == 0:
        return float(beta0 + beta1)
    factor = (1 - np.exp(-t / tau)) / (t / tau)
    return float(beta0 + beta1 * factor + beta2 * (factor - np.exp(-t / tau)))


def fit_nelson_siegel(tenors: np.ndarray, yields: np.ndarray) -> Dict:
    """
    Fit Nelson-Siegel parameters via non-linear least squares.
    Used to construct smooth yield curves from sparse market data.
    """
    tenors = np.asarray(tenors, dtype=float)
    yields = np.asarray(yields, dtype=float)

    def objective(params):
        beta0, beta1, beta2, tau = params
        if tau <= 0:
            return 1e10
        fitted = np.array([nelson_siegel(t, beta0, beta1, beta2, tau) for t in tenors])
        return float(np.sum((fitted - yields) ** 2))

    # Initial guess
    x0 = [yields.mean(), yields[0] - yields[-1], 0.0, 2.0]
    bounds = [(0, 0.30), (-0.20, 0.20), (-0.20, 0.20), (0.01, 30.0)]

    result = optimize.minimize(objective, x0, bounds=bounds, method="L-BFGS-B")

    return {
        "beta0_level":     round(float(result.x[0]), 6),
        "beta1_slope":     round(float(result.x[1]), 6),
        "beta2_curvature": round(float(result.x[2]), 6),
        "tau_decay":       round(float(result.x[3]), 4),
        "ssr":             round(float(result.fun), 8),
        "converged":       bool(result.success),
        "methodology":     "nelson_siegel_1987_nls",
    }


def svensson(t: float, beta0: float, beta1: float, beta2: float, beta3: float,
             tau1: float, tau2: float) -> float:
    """
    Svensson (1994) extended Nelson-Siegel.
    Adds a second hump for greater flexibility. Used by ECB, BOE, US Fed.
    """
    if t == 0:
        return float(beta0 + beta1)
    f1 = (1 - np.exp(-t / tau1)) / (t / tau1)
    f2 = (1 - np.exp(-t / tau2)) / (t / tau2)
    return float(beta0 + beta1 * f1 + beta2 * (f1 - np.exp(-t / tau1))
                 + beta3 * (f2 - np.exp(-t / tau2)))


# ════════════════════════════════════════════════════════════════
# PORTFOLIO-LEVEL FIXED INCOME ANALYTICS
# ════════════════════════════════════════════════════════════════

def portfolio_duration(bonds: List[Dict]) -> Dict:
    """
    Weighted average modified duration of a bond portfolio.

    bonds: List of dicts with keys: market_value, coupon, ytm, maturity
    """
    if not bonds:
        return {"error": "no_bonds"}

    total_mv = sum(b["market_value"] for b in bonds)
    if total_mv == 0:
        return {"error": "zero_total_value"}

    weighted_md   = 0.0
    weighted_conv = 0.0
    total_dv01    = 0.0

    for b in bonds:
        w   = b["market_value"] / total_mv
        md  = modified_duration(100, b["coupon"], b["ytm"], b["maturity"])
        cv  = convexity(100, b["coupon"], b["ytm"], b["maturity"])
        d01 = dv01(b["market_value"], b["coupon"], b["ytm"], b["maturity"])
        weighted_md   += w * md
        weighted_conv += w * cv
        total_dv01    += d01

    return {
        "weighted_modified_duration": round(weighted_md, 3),
        "weighted_convexity":         round(weighted_conv, 3),
        "total_portfolio_dv01":       round(total_dv01, 2),
        "total_market_value":         round(total_mv, 2),
        "estimated_loss_100bps_rise": round(total_mv * weighted_md * 0.01, 2),
        "methodology":                "portfolio_duration_v1",
    }
