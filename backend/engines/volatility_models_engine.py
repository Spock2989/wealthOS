"""
WealthOS Volatility Models Engine
Forward-looking conditional volatility models — institutional grade.

References:
  - Engle (1982): ARCH
  - Bollerslev (1986): GARCH
  - Nelson (1991): EGARCH (asymmetric)
  - Glosten, Jagannathan, Runkle (1993): GJR-GARCH (leverage effect)
  - Yang & Zhang (2000): drift-independent OHLC volatility estimator
  - Parkinson (1980): high-low estimator
"""

import numpy as np
import pandas as pd
from typing import Dict, Optional
from scipy import optimize

try:
    from arch import arch_model
    ARCH_AVAILABLE = True
except ImportError:
    ARCH_AVAILABLE = False

TRADING_DAYS = 252


# ════════════════════════════════════════════════════════════════
# GARCH FAMILY
# ════════════════════════════════════════════════════════════════

def fit_garch(returns: pd.Series, p: int = 1, q: int = 1,
              dist: str = "studentst") -> Dict:
    """
    GARCH(p,q) — Generalized Autoregressive Conditional Heteroskedasticity.

    σ²_t = ω + Σαᵢ·ε²_{t−i} + Σβⱼ·σ²_{t−j}

    Captures volatility clustering — high-vol days follow high-vol days.
    Standard at every quant fund for vol forecasting.

    dist: 'normal', 'studentst' (better for fat tails), 'skewstudent'
    """
    if not ARCH_AVAILABLE:
        return {"error": "arch_package_not_installed"}

    series = returns.dropna() * 100   # arch expects percentage returns
    if len(series) < 100:
        return {"error": "insufficient_data", "n_obs": len(series)}

    try:
        model   = arch_model(series, vol="GARCH", p=p, q=q, dist=dist)
        result  = model.fit(disp="off", show_warning=False)
        params  = result.params

        # 1-day-ahead forecast
        forecast = result.forecast(horizon=1, reindex=False)
        next_vol = float(np.sqrt(forecast.variance.iloc[-1, 0]))

        # Persistence: α + β. Closer to 1 = more persistent vol clustering.
        alpha = float(params.get("alpha[1]", 0))
        beta_p = float(params.get("beta[1]", 0))
        persistence = alpha + beta_p

        # Long-run unconditional variance
        omega = float(params.get("omega", 0))
        if persistence < 1:
            long_run_var = omega / (1 - persistence)
            long_run_vol = float(np.sqrt(long_run_var * TRADING_DAYS) / 100)
        else:
            long_run_vol = None   # non-stationary

        return {
            "omega":               round(omega, 6),
            "alpha_1":             round(alpha, 4),
            "beta_1":              round(beta_p, 4),
            "persistence":         round(persistence, 4),
            "is_stationary":       bool(persistence < 1),
            "next_day_vol_pct":    round(next_vol, 3),
            "next_day_vol_annualized": round(next_vol * np.sqrt(TRADING_DAYS), 3),
            "long_run_vol_annualized": round(long_run_vol, 3) if long_run_vol else None,
            "log_likelihood":      round(float(result.loglikelihood), 2),
            "aic":                 round(float(result.aic), 2),
            "bic":                 round(float(result.bic), 2),
            "distribution":        dist,
            "methodology":         f"garch_{p}_{q}_bollerslev_1986",
        }
    except Exception as e:
        return {"error": f"garch_fit_failed: {str(e)}"}


def fit_egarch(returns: pd.Series, p: int = 1, q: int = 1) -> Dict:
    """
    EGARCH (Nelson 1991) — Exponential GARCH.
    Models log(σ²) allowing for asymmetric response to positive/negative shocks.
    Captures the "leverage effect" — bad news increases vol more than good news.
    """
    if not ARCH_AVAILABLE:
        return {"error": "arch_package_not_installed"}

    series = returns.dropna() * 100
    if len(series) < 100:
        return {"error": "insufficient_data"}

    try:
        model   = arch_model(series, vol="EGARCH", p=p, q=q, dist="studentst")
        result  = model.fit(disp="off", show_warning=False)
        forecast = result.forecast(horizon=1, reindex=False)
        next_vol = float(np.sqrt(forecast.variance.iloc[-1, 0]))

        gamma_param = result.params.get("gamma[1]", None)
        return {
            "next_day_vol_pct":     round(next_vol, 3),
            "next_day_vol_annualized": round(next_vol * np.sqrt(TRADING_DAYS), 3),
            "leverage_gamma":       round(float(gamma_param), 4) if gamma_param is not None else None,
            "leverage_significant": bool(gamma_param is not None and abs(gamma_param) > 0.05),
            "log_likelihood":       round(float(result.loglikelihood), 2),
            "methodology":          "egarch_nelson_1991",
        }
    except Exception as e:
        return {"error": f"egarch_fit_failed: {str(e)}"}


def fit_gjr_garch(returns: pd.Series) -> Dict:
    """
    GJR-GARCH (Glosten, Jagannathan, Runkle 1993).
    Adds asymmetric "leverage" term to standard GARCH.
    Negative shocks have a different (usually larger) effect on next-period variance.
    """
    if not ARCH_AVAILABLE:
        return {"error": "arch_package_not_installed"}

    series = returns.dropna() * 100
    if len(series) < 100:
        return {"error": "insufficient_data"}

    try:
        model   = arch_model(series, vol="GARCH", p=1, o=1, q=1, dist="studentst")
        result  = model.fit(disp="off", show_warning=False)
        forecast = result.forecast(horizon=1, reindex=False)
        next_vol = float(np.sqrt(forecast.variance.iloc[-1, 0]))

        gamma_param = result.params.get("gamma[1]", None)
        return {
            "next_day_vol_pct":         round(next_vol, 3),
            "next_day_vol_annualized":  round(next_vol * np.sqrt(TRADING_DAYS), 3),
            "leverage_gamma":           round(float(gamma_param), 4) if gamma_param is not None else None,
            "asymmetry_detected":       bool(gamma_param is not None and gamma_param > 0.02),
            "methodology":              "gjr_garch_1993",
        }
    except Exception as e:
        return {"error": f"gjr_fit_failed: {str(e)}"}


# ════════════════════════════════════════════════════════════════
# OHLC VOLATILITY ESTIMATORS
# ════════════════════════════════════════════════════════════════

def parkinson_volatility(high: pd.Series, low: pd.Series,
                         periods_per_year: int = TRADING_DAYS) -> float:
    """
    Parkinson (1980) high-low volatility estimator.
    ~5x more efficient than close-to-close. Doesn't use opening price.

    σ²_P = (1 / 4·ln(2)) · E[(ln(H/L))²]
    """
    if len(high) < 2 or len(low) < 2:
        return 0.0
    log_hl_sq = (np.log(high / low) ** 2).dropna()
    daily_var = log_hl_sq.mean() / (4 * np.log(2))
    return float(np.sqrt(daily_var * periods_per_year))


def garman_klass_volatility(open_p: pd.Series, high: pd.Series,
                             low: pd.Series, close: pd.Series,
                             periods_per_year: int = TRADING_DAYS) -> float:
    """
    Garman-Klass (1980) OHLC volatility estimator.
    More efficient than close-to-close by using all four prices.

    σ² = 0.5·(ln(H/L))² - (2·ln(2)-1)·(ln(C/O))²
    """
    log_hl = np.log(high / low)
    log_co = np.log(close / open_p)
    daily_var = (0.5 * log_hl ** 2 - (2 * np.log(2) - 1) * log_co ** 2).dropna().mean()
    return float(np.sqrt(daily_var * periods_per_year))


def yang_zhang_volatility(open_p: pd.Series, high: pd.Series,
                           low: pd.Series, close: pd.Series,
                           periods_per_year: int = TRADING_DAYS,
                           k: float = 0.34) -> float:
    """
    Yang-Zhang (2000) OHLC volatility — drift-independent estimator.

    σ²_YZ = σ²_overnight + k·σ²_open_to_close + (1-k)·σ²_RS

    Most accurate OHLC vol estimator. ~8x more efficient than close-to-close.
    Used by HFT firms for intraday vol.
    """
    if len(open_p) < 2:
        return 0.0

    log_oc_prev = np.log(open_p / close.shift(1)).dropna()
    log_co      = np.log(close / open_p).dropna()
    log_ho      = np.log(high / open_p)
    log_lo      = np.log(low / open_p)
    log_hc      = np.log(high / close)
    log_lc      = np.log(low / close)

    # Rogers-Satchell variance
    sigma_rs_sq = (log_ho * log_hc + log_lo * log_lc).dropna()

    sigma_o_sq  = log_oc_prev.var(ddof=1)
    sigma_c_sq  = log_co.var(ddof=1)
    sigma_rs    = float(sigma_rs_sq.mean())

    daily_var = sigma_o_sq + k * sigma_c_sq + (1 - k) * sigma_rs
    return float(np.sqrt(daily_var * periods_per_year))


# ════════════════════════════════════════════════════════════════
# REALIZED VOLATILITY (FROM INTRADAY DATA)
# ════════════════════════════════════════════════════════════════

def realized_volatility(intraday_returns: pd.Series,
                        periods_per_year: int = TRADING_DAYS) -> float:
    """
    Realized volatility from high-frequency returns.
    Sum of squared intraday returns within each day, then annualize.

    Critical for risk models when intraday data is available.
    """
    rv_daily = (intraday_returns ** 2).sum()
    return float(np.sqrt(rv_daily * periods_per_year))


def realized_volatility_with_jump_test(intraday_returns: pd.Series) -> Dict:
    """
    Barndorff-Nielsen & Shephard jump test.
    Decomposes total variation into continuous + jump components.
    """
    if len(intraday_returns) < 5:
        return {"error": "insufficient_data"}

    rv = float((intraday_returns ** 2).sum())
    # Bipower variation — robust to jumps
    bv = float((np.pi / 2) *
               (intraday_returns.abs() * intraday_returns.shift(1).abs()).sum())
    jump_component = max(0, rv - bv)

    return {
        "realized_variance":  round(rv, 8),
        "bipower_variation":  round(bv, 8),
        "jump_component":     round(jump_component, 8),
        "jump_pct_of_total":  round(jump_component / rv * 100, 2) if rv > 0 else 0,
        "methodology":        "barndorff_nielsen_shephard_jump_test",
    }


# ════════════════════════════════════════════════════════════════
# VARIANCE FORECASTING
# ════════════════════════════════════════════════════════════════

def har_rv_model(realized_vols: pd.Series) -> Dict:
    """
    Heterogeneous Autoregressive model of Realized Volatility (Corsi 2009).

    RV_t = c + β_d·RV_{t-1} + β_w·RV̄_week + β_m·RV̄_month + ε

    Simple but powerful. Often outperforms GARCH for forecasting.
    """
    rv = realized_vols.dropna()
    if len(rv) < 25:
        return {"error": "insufficient_data"}

    df = pd.DataFrame({"rv": rv})
    df["rv_daily"]   = df["rv"].shift(1)
    df["rv_weekly"]  = df["rv"].shift(1).rolling(5).mean()
    df["rv_monthly"] = df["rv"].shift(1).rolling(22).mean()
    df = df.dropna()

    if len(df) < 25:
        return {"error": "insufficient_data_after_lags"}

    y = df["rv"].values
    X = np.column_stack([np.ones(len(df)),
                         df["rv_daily"], df["rv_weekly"], df["rv_monthly"]])

    # OLS
    coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    y_pred   = X @ coef
    ss_res   = float(((y - y_pred) ** 2).sum())
    ss_tot   = float(((y - y.mean()) ** 2).sum())
    r2       = 1 - ss_res / ss_tot if ss_tot > 0 else 0

    # Forecast next period
    last_rv = rv.iloc[-1]
    last_w  = rv.iloc[-5:].mean()
    last_m  = rv.iloc[-22:].mean()
    next_forecast = float(coef[0] + coef[1]*last_rv + coef[2]*last_w + coef[3]*last_m)

    return {
        "intercept":             round(float(coef[0]), 6),
        "beta_daily":            round(float(coef[1]), 4),
        "beta_weekly":           round(float(coef[2]), 4),
        "beta_monthly":          round(float(coef[3]), 4),
        "r_squared":             round(r2, 4),
        "next_period_forecast":  round(next_forecast, 6),
        "methodology":           "har_rv_corsi_2009",
    }


# ════════════════════════════════════════════════════════════════
# MASTER VOLATILITY DASHBOARD
# ════════════════════════════════════════════════════════════════

def compute_volatility_models_report(returns: pd.Series) -> Dict:
    """All conditional volatility models in one shot."""
    out = {}
    if len(returns) < 100:
        return {"error": "insufficient_data_for_garch"}

    out["garch_1_1_studentt"] = fit_garch(returns, dist="studentst")
    out["egarch"]             = fit_egarch(returns)
    out["gjr_garch"]          = fit_gjr_garch(returns)
    out["methodology_version"] = "vol_models_v1.0"
    return out
