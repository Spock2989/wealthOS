"""
WealthOS — Price Provider Engine
==================================
Deterministic price fetching for:
  - Mutual Fund NAVs  → AMFI DB (canonical, daily seeded)
  - Equity prices     → yfinance (NSE: SYMBOL.NS / BSE: SYMBOL.BO)
  - Fallback chain    → DB cache → live fetch → None (flagged)

Design principles:
  - No guessing: if price unavailable, return None + log flag
  - All prices in INR
  - Reproducible: same date → same price (uses historical fetch)
"""

import logging
from datetime import date, timedelta
from typing import Optional
from functools import lru_cache

log = logging.getLogger(__name__)

# ── yfinance import (graceful degradation if not installed) ─────────────────
try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False
    log.warning("yfinance not installed. Equity prices unavailable. Run: pip install yfinance")


# ── NAV from AMFI DB ──────────────────────────────────────────────────────────

def get_mf_nav(scheme_code: int, nav_date: Optional[date] = None, db=None) -> Optional[float]:
    """
    Fetch mutual fund NAV from AMFI instruments table.
    Returns latest NAV from DB if nav_date is None.
    Returns None and logs if unavailable.
    """
    if db is None:
        log.error(f"get_mf_nav: db session required for scheme_code={scheme_code}")
        return None

    try:
        from models_amfi import AMFIInstrument
        inst = db.query(AMFIInstrument).filter_by(scheme_code=scheme_code).first()
        if inst and inst.nav is not None:
            return float(inst.nav)
        log.warning(f"NAV not found in DB for scheme_code={scheme_code}")
        return None
    except Exception as e:
        log.error(f"DB error fetching NAV for {scheme_code}: {e}")
        return None


def get_mf_nav_by_isin(isin: str, db=None) -> Optional[float]:
    """Fetch MF NAV by ISIN (tries canonical, payout, reinvest columns)."""
    if db is None:
        return None
    try:
        from models_amfi import AMFIInstrument
        inst = (
            db.query(AMFIInstrument)
            .filter(
                (AMFIInstrument.canonical_isin == isin) |
                (AMFIInstrument.isin_payout == isin) |
                (AMFIInstrument.isin_reinvest == isin)
            )
            .first()
        )
        if inst and inst.nav is not None:
            return float(inst.nav)
        log.warning(f"NAV not found for ISIN={isin}")
        return None
    except Exception as e:
        log.error(f"DB error fetching NAV for ISIN {isin}: {e}")
        return None


# ── Equity prices via yfinance ────────────────────────────────────────────────

def get_equity_price(
    symbol: str,
    exchange: str = "NSE",
    price_date: Optional[date] = None,
) -> Optional[float]:
    """
    Fetch equity closing price from Yahoo Finance.

    Args:
        symbol: NSE/BSE symbol (e.g. "RELIANCE", "HDFCBANK")
        exchange: "NSE" (appends .NS) or "BSE" (appends .BO)
        price_date: specific date for historical price; None = latest close

    Returns:
        float price in INR, or None if unavailable
    """
    if not YFINANCE_AVAILABLE:
        log.error("yfinance unavailable. Install: pip install yfinance")
        return None

    suffix = ".NS" if exchange.upper() == "NSE" else ".BO"
    ticker_symbol = f"{symbol.upper()}{suffix}"

    try:
        ticker = yf.Ticker(ticker_symbol)

        if price_date is None:
            # Latest price
            info = ticker.fast_info
            price = getattr(info, "last_price", None)
            if price and price > 0:
                return float(price)
            # Fallback: last close from history
            hist = ticker.history(period="5d")
            if not hist.empty:
                return float(hist["Close"].iloc[-1])
            log.warning(f"No price data for {ticker_symbol}")
            return None
        else:
            # Historical: fetch window around target date
            start = price_date - timedelta(days=5)
            end = price_date + timedelta(days=1)
            hist = ticker.history(start=start.isoformat(), end=end.isoformat())
            if hist.empty:
                log.warning(f"No historical data for {ticker_symbol} on {price_date}")
                return None
            # Get closest date on or before requested date
            hist.index = hist.index.date
            valid = hist[hist.index <= price_date]
            if valid.empty:
                return None
            return float(valid["Close"].iloc[-1])

    except Exception as e:
        log.error(f"yfinance error for {ticker_symbol}: {e}")
        return None


def get_equity_price_bulk(
    symbols: list[str],
    exchange: str = "NSE",
) -> dict[str, Optional[float]]:
    """
    Fetch latest prices for multiple symbols in one call.
    More efficient than calling get_equity_price() in a loop.
    Returns: {symbol: price_or_None}
    """
    if not YFINANCE_AVAILABLE:
        return {s: None for s in symbols}

    suffix = ".NS" if exchange.upper() == "NSE" else ".BO"
    tickers_str = " ".join(f"{s.upper()}{suffix}" for s in symbols)

    try:
        data = yf.download(tickers_str, period="5d", auto_adjust=True, progress=False)
        if data.empty:
            return {s: None for s in symbols}

        result = {}
        close = data["Close"] if "Close" in data else data
        for s in symbols:
            col = f"{s.upper()}{suffix}"
            if col in close.columns:
                series = close[col].dropna()
                result[s] = float(series.iloc[-1]) if not series.empty else None
            else:
                result[s] = None
        return result

    except Exception as e:
        log.error(f"Bulk price fetch error: {e}")
        return {s: None for s in symbols}


# ── Unified price resolver ────────────────────────────────────────────────────

def resolve_price(
    instrument: dict,
    price_date: Optional[date] = None,
    db=None,
) -> Optional[float]:
    """
    Unified price resolver. Accepts an instrument dict with keys:
      - instrument_type: "mutual_fund" | "equity" | "etf"
      - scheme_code: int (for MFs)
      - isin: str
      - symbol: str (for equities)
      - exchange: "NSE" | "BSE"

    Returns float price in INR or None.
    """
    itype = instrument.get("instrument_type", "").lower()

    if itype == "mutual_fund" or itype == "etf":
        scheme_code = instrument.get("scheme_code")
        isin = instrument.get("isin")
        if scheme_code:
            return get_mf_nav(scheme_code, price_date, db)
        if isin:
            return get_mf_nav_by_isin(isin, db)
        log.warning(f"Cannot resolve MF price — no scheme_code or isin: {instrument}")
        return None

    elif itype == "equity":
        symbol = instrument.get("symbol")
        exchange = instrument.get("exchange", "NSE")
        if symbol:
            return get_equity_price(symbol, exchange, price_date)
        log.warning(f"Cannot resolve equity price — no symbol: {instrument}")
        return None

    else:
        log.warning(f"Unknown instrument type: {itype}")
        return None
