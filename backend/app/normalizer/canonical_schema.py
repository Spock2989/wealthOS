
from pydantic import BaseModel, Field
from typing import Optional

class CanonicalHolding(BaseModel):
    instrument_name: str
    isin: Optional[str] = None
    folio_number: Optional[str] = None
    asset_class: str = "equity"
    sub_asset_class: Optional[str] = None
    sector: Optional[str] = None
    market_cap: Optional[str] = None
    geography: str = "India"
    quantity: Optional[float] = None
    nav: Optional[float] = None
    current_value: float = 0.0
    allocation_percent: Optional[float] = None
    risk_score: Optional[float] = None
    liquidity_score: Optional[float] = None
