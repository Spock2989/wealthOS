
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any
from app.normalizer.canonical_schema import CanonicalHolding

@dataclass
class AnalyticsResult:
    total_value_inr: float = 0.0
    holding_count: int = 0
    asset_allocation: Dict = field(default_factory=dict)
    sector_exposure: Dict = field(default_factory=dict)
    market_cap_exposure: Dict = field(default_factory=dict)
    concentration: Dict = field(default_factory=dict)
    diversification: Dict = field(default_factory=dict)
    fund_overlap: Dict = field(default_factory=dict)
    volatility: Dict = field(default_factory=dict)
    drawdown_sensitivity: Dict = field(default_factory=dict)
    liquidity_profile: Dict = field(default_factory=dict)
    stress_test: Dict = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    observations: List[str] = field(default_factory=list)

    def to_dict(self):
        return asdict(self)

class AnalyticsEngine:
    def run(self, holdings: List[CanonicalHolding]) -> AnalyticsResult:
        from app.analytics.asset_allocation import run as aa
        from app.analytics.sector_exposure import run as se
        from app.analytics.market_cap import run as mc
        from app.analytics.concentration import run as cn
        from app.analytics.diversification import run as dv
        from app.analytics.fund_overlap import run as fo
        from app.analytics.volatility import run as vo
        from app.analytics.drawdown import run as dd
        from app.analytics.liquidity import run as lq
        from app.analytics.stress_test import run as st

        total = sum(h.current_value for h in holdings)
        result = AnalyticsResult(total_value_inr=round(total, 2), holding_count=len(holdings))
        result.asset_allocation    = aa(holdings, total)
        result.sector_exposure     = se(holdings, total)
        result.market_cap_exposure = mc(holdings, total)
        result.concentration       = cn(holdings, total)
        result.diversification     = dv(holdings, total)
        result.fund_overlap        = fo(holdings)
        result.volatility          = vo(holdings, total)
        result.drawdown_sensitivity= dd(holdings, total)
        result.liquidity_profile   = lq(holdings, total)
        result.stress_test         = st(holdings, total)

        warns = []
        aa_data = result.asset_allocation.get("by_class", {})
        eq = aa_data.get("equity", 0)
        if eq > 80: warns.append(f"High equity concentration: {eq:.1f}% — consider adding debt for stability")
        if eq < 20: warns.append(f"Very low equity allocation: {eq:.1f}% — may underperform inflation long-term")
        if result.concentration.get("top5_weight_pct", 0) > 60:
            warns.append(f"Top 5 holdings = {result.concentration['top5_weight_pct']}% of portfolio — high concentration risk")
        if result.diversification.get("score", 100) < 50:
            warns.append("Low diversification score — portfolio may be over-concentrated")
        result.warnings = warns
        return result
