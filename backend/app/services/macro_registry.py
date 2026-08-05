"""
WealthOS — Macro series registry.

The 12-series canonical list. Selected for Indian-wealth relevance:
US rates + USDINR + India CPI/policy rate + global risk + commodities.

This is the SINGLE source of truth for what series the sync script
fetches, the API surfaces, and the scenario engine references. Add a
new series here and only here.

methodology_version: macro_registry@1.0.0
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import List


@dataclass(frozen=True)
class TrackedSeries:
    series_id: str          # FRED series ID (the API key)
    label: str              # human-readable short name
    category: str           # 'rates' | 'fx' | 'inflation' | 'risk' | 'commodity' | 'credit'
    description: str        # one line, plain English
    geography: str          # 'US' | 'India' | 'Global'

    def to_dict(self) -> dict:
        return asdict(self)


SERIES_REGISTRY: List[TrackedSeries] = [
    # ── US rates ────────────────────────────────────────────────
    TrackedSeries("DGS10", "US 10Y Treasury Yield", "rates",
                  "10-Year US Treasury constant maturity yield, % p.a.", "US"),
    TrackedSeries("DGS2",  "US 2Y Treasury Yield",  "rates",
                  "2-Year US Treasury constant maturity yield, % p.a.", "US"),
    TrackedSeries("T10Y2Y", "US 10Y-2Y Spread",     "rates",
                  "10Y minus 2Y Treasury spread; recession indicator when inverted.", "US"),

    # ── FX ──────────────────────────────────────────────────────
    TrackedSeries("DEXINUS", "INR per USD",         "fx",
                  "India Rupees per US Dollar (daily, exchange rate).", "India"),

    # ── Inflation ───────────────────────────────────────────────
    TrackedSeries("CPIAUCSL", "US CPI (All Items)", "inflation",
                  "US Consumer Price Index, SA, monthly.", "US"),
    TrackedSeries("INDCPIALLMINMEI", "India CPI",   "inflation",
                  "India Consumer Price Index (OECD compilation), monthly.", "India"),

    # ── Risk ────────────────────────────────────────────────────
    TrackedSeries("VIXCLS", "VIX (S&P Volatility)", "risk",
                  "CBOE Volatility Index; market fear gauge.", "Global"),
    TrackedSeries("BAMLH0A0HYM2", "US HY Spread",   "credit",
                  "ICE BofA US High Yield option-adjusted spread, % over Treasuries.", "US"),

    # ── Commodity ───────────────────────────────────────────────
    TrackedSeries("DCOILWTICO",  "WTI Crude",       "commodity",
                  "West Texas Intermediate crude oil price, USD/bbl.", "Global"),
    TrackedSeries("DCOILBRENTEU", "Brent Crude",    "commodity",
                  "Europe Brent crude oil price, USD/bbl.", "Global"),
    TrackedSeries("GOLDAMGBD228NLBM", "Gold (London PM)", "commodity",
                  "London Bullion Market Gold Price, PM Fix, USD/oz.", "Global"),

    # ── India policy ────────────────────────────────────────────
    TrackedSeries("INTDSRINM193N", "India RBI Discount Rate", "rates",
                  "RBI Bank Rate / discount rate, % p.a.", "India"),
]


def registered_ids() -> List[str]:
    return [s.series_id for s in SERIES_REGISTRY]
