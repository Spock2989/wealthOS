"""
WealthOS Price Provider
Data adapter for price/NAV time series.
Currently uses mock generators — easily swap to Yahoo Finance / NSE / AMFI later.
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional


# ── MOCK DATA GENERATOR ─────────────────────────────────────────
def generate_mock_returns(
    ticker: str = "MOCK",
    days: int = 252,
    annualized_return: float = 0.12,
    annualized_vol: float = 0.18,
    seed: Optional[int] = None,
) -> pd.Series:
    """
    Generate mock daily return series with realistic Indian equity properties.
    annualized_return: e.g. 0.12 = 12% CAGR
    annualized_vol:    e.g. 0.18 = 18% annual std
    """
    if seed is not None:
        np.random.seed(seed)
    else:
        np.random.seed(hash(ticker) % (2**32))

    daily_mu    = annualized_return / 252
    daily_sigma = annualized_vol / np.sqrt(252)

    # Geometric Brownian Motion with slight negative skew (realistic Indian equity)
    rets = np.random.normal(daily_mu, daily_sigma, days)
    # Inject occasional crash days
    crash_days = np.random.choice(days, size=max(1, days // 100), replace=False)
    rets[crash_days] *= -3.5

    dates = pd.date_range(end=datetime.now(), periods=days, freq='B')
    return pd.Series(rets, index=dates, name=ticker)


def generate_mock_prices(ticker: str = "MOCK", **kwargs) -> pd.Series:
    """Mock daily prices — exponentiated returns starting at 100."""
    returns = generate_mock_returns(ticker, **kwargs)
    prices  = 100 * (1 + returns).cumprod()
    return prices


# ── PRESET MOCK PROFILES ────────────────────────────────────────
MOCK_PROFILES = {
    # benchmark
    "NIFTY50":      {"annualized_return": 0.135, "annualized_vol": 0.155, "seed": 1},
    "NIFTY500":     {"annualized_return": 0.142, "annualized_vol": 0.165, "seed": 2},
    "NIFTYMIDCAP":  {"annualized_return": 0.18,  "annualized_vol": 0.22,  "seed": 3},
    "NIFTYSMALLCAP":{"annualized_return": 0.22,  "annualized_vol": 0.28,  "seed": 4},

    # factor mock series
    "MKT":  {"annualized_return": 0.07,  "annualized_vol": 0.16, "seed": 10},
    "SMB":  {"annualized_return": 0.04,  "annualized_vol": 0.10, "seed": 11},
    "HML":  {"annualized_return": 0.03,  "annualized_vol": 0.08, "seed": 12},
    "MOM":  {"annualized_return": 0.05,  "annualized_vol": 0.12, "seed": 13},
    "QMJ":  {"annualized_return": 0.025, "annualized_vol": 0.07, "seed": 14},
}


def get_benchmark_returns(benchmark: str = "NIFTY50", days: int = 252) -> pd.Series:
    """Returns daily return series for a named benchmark."""
    profile = MOCK_PROFILES.get(benchmark, MOCK_PROFILES["NIFTY50"])
    return generate_mock_returns(ticker=benchmark, days=days, **profile)


def get_factor_returns(days: int = 252) -> pd.DataFrame:
    """Returns DataFrame of factor return series for multi-factor regression."""
    factors = ["MKT", "SMB", "HML", "MOM", "QMJ"]
    df = pd.DataFrame({
        f: generate_mock_returns(ticker=f, days=days, **MOCK_PROFILES[f])
        for f in factors
    })
    return df


def get_portfolio_returns(holdings: list, days: int = 252) -> pd.Series:
    """
    Build a synthetic portfolio return series from holdings.
    Each instrument gets its own mock return series; weighted-combine into portfolio.
    """
    if not holdings:
        return pd.Series(dtype=float)

    total_value = sum(h.value for h in holdings)
    if total_value == 0:
        return pd.Series(dtype=float)

    weights = {h.id: h.value / total_value for h in holdings}
    series_list = []
    weight_list = []
    for h in holdings:
        # Asset-class-driven volatility profile
        asset_class = h.instrument.asset_class if h.instrument else "equity"
        cap         = h.instrument.market_cap_bucket if h.instrument else None

        if asset_class == "debt":
            ann_ret, ann_vol = 0.07, 0.04
        elif asset_class == "hybrid":
            ann_ret, ann_vol = 0.10, 0.10
        elif cap == "small":
            ann_ret, ann_vol = 0.20, 0.28
        elif cap == "mid":
            ann_ret, ann_vol = 0.16, 0.22
        else:
            ann_ret, ann_vol = 0.13, 0.18

        rets = generate_mock_returns(
            ticker=h.id, days=days,
            annualized_return=ann_ret, annualized_vol=ann_vol,
            seed=hash(h.id) % (2**32)
        )
        series_list.append(rets)
        weight_list.append(weights[h.id])

    # Weighted combine
    combined = pd.concat(series_list, axis=1).fillna(0)
    portfolio_returns = (combined.values * np.array(weight_list)).sum(axis=1)
    return pd.Series(portfolio_returns, index=combined.index, name="portfolio")


# ── REAL DATA INTEGRATION HOOKS (TODO) ──────────────────────────
def fetch_yahoo_prices(ticker: str, days: int = 252) -> Optional[pd.Series]:
    """
    Hook for Yahoo Finance integration.
    Install: pip install yfinance
    Implementation deferred until live data layer is ready.
    """
    # import yfinance as yf
    # data = yf.download(ticker, period=f"{days}d", progress=False)
    # return data['Adj Close'].pct_change().dropna()
    return None


def fetch_amfi_nav(scheme_code: str, days: int = 252) -> Optional[pd.Series]:
    """
    Hook for AMFI NAV data.
    AMFI publishes daily NAVs at https://www.amfiindia.com/spages/NAVAll.txt
    """
    return None


def fetch_nse_prices(symbol: str, days: int = 252) -> Optional[pd.Series]:
    """Hook for NSE Bhavcopy data."""
    return None
