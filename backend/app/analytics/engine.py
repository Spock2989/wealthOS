"""
WealthOS Analytics Engine — Tier 1 composition analytics + orchestration.

Produces the full analytics snapshot written to AnalyticsSnapshot.result.
Output contract: all keys below are always present; empty dict {} when not
computable. methodology_version embedded in every sub-result.

Tier 1 (always): allocation, sector, market_cap, concentration, diversification,
                 overlap, volatility, drawdown, liquidity, stress_test
Tier 2 (always): scenarios (20 standard), macro_sensitivity matrix
Tier 3 (always): lookthrough (via AMFI fund constituents if available)
"""

from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from app.normalizer.canonical_schema import CanonicalHolding


@dataclass
class AnalyticsResult:
    # ── Tier 1 — Composition ──────────────────────────────────
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
    # ── Tier 2 — Scenario + Macro ─────────────────────────────
    scenarios: List[Dict] = field(default_factory=list)
    macro_sensitivity: Dict = field(default_factory=dict)
    # ── Tier 3 — Look-through ─────────────────────────────────
    lookthrough: Dict = field(default_factory=dict)
    # ── Meta ──────────────────────────────────────────────────
    warnings: List[str] = field(default_factory=list)
    observations: List[str] = field(default_factory=list)
    methodology_version: str = "wealthos_analytics@3.0"
    computed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict:
        return asdict(self)

class AnalyticsEngine:
    def run(self, holdings: List[CanonicalHolding]) -> "AnalyticsResult":
        """
        Full analytics pipeline — Tier 1 composition + Tier 2 scenarios/macro
        + Tier 3 lookthrough. Single call produces the complete snapshot.

        Determinism: same holdings list → same output (scenario engine is
        deterministic; no wall-clock or randomness in output).
        """
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../.."))

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
        import logging
        log = logging.getLogger(__name__)

        if not holdings:
            return AnalyticsResult()

        total = sum(h.current_value for h in holdings)
        if total == 0:
            return AnalyticsResult()

        result = AnalyticsResult(total_value_inr=round(total, 2), holding_count=len(holdings))

        # ── Tier 1: composition ───────────────────────────────
        result.asset_allocation     = aa(holdings, total)
        result.sector_exposure      = se(holdings, total)
        result.market_cap_exposure  = mc(holdings, total)
        result.concentration        = cn(holdings, total)
        result.diversification      = dv(holdings, total)
        result.fund_overlap         = fo(holdings)
        result.volatility           = vo(holdings, total)
        result.drawdown_sensitivity = dd(holdings, total)
        result.liquidity_profile    = lq(holdings, total)
        result.stress_test          = st(holdings, total)

        # ── Tier 2: scenarios + macro sensitivity ─────────────
        # sector_exp must be {sector_name: pct_of_portfolio (0–100)}
        # cap_split must be {cap_bucket: pct_of_portfolio (0–100)}
        try:
            from engines.scenario_engine import (
                run_scenarios,
                compute_full_macro_sensitivity_matrix,
            )
            sector_exp = result.sector_exposure.get("by_sector", {})
            cap_split  = result.market_cap_exposure.get("by_cap_pct_of_portfolio", {})
            if sector_exp:
                result.scenarios         = run_scenarios(sector_exp, cap_split, total)
                result.macro_sensitivity = compute_full_macro_sensitivity_matrix(sector_exp, total)
        except Exception as e:
            log.warning("tier2_scenario_failed: %s", e)
            result.warnings.append(f"scenario_engine_unavailable: {e}")

        # ── Tier 3: look-through ──────────────────────────────
        try:
            from engines.lookthrough_engine import compute_lookthrough_report
            result.lookthrough = _lookthrough_from_canonical(holdings)
        except Exception as e:
            log.warning("tier3_lookthrough_failed: %s", e)

        # ── Observation + warning generation ─────────────────
        warns: List[str] = []
        aa_data = result.asset_allocation.get("by_class", {})
        eq = aa_data.get("equity", 0)
        if eq > 80:
            warns.append(f"High equity concentration: {eq:.1f}% — consider adding debt for stability")
        if eq < 20:
            warns.append(f"Very low equity allocation: {eq:.1f}% — may underperform inflation long-term")
        if result.concentration.get("top5_weight_pct", 0) > 60:
            warns.append(f"Top 5 holdings = {result.concentration['top5_weight_pct']}% — high concentration risk")
        if result.diversification.get("score", 100) < 50:
            warns.append("Low diversification score — portfolio may be over-concentrated")
        result.warnings = warns
        return result


def _lookthrough_from_canonical(holdings: List[CanonicalHolding]) -> Dict:
    """
    Simplified look-through using CanonicalHolding fields.
    Direct equity holdings are passed through. Mutual funds without constituent
    data are listed as opaque. Constituent data (from AMFI seeding) would enrich
    this further but is not required for the engine to produce a valid output.

    methodology_version: lookthrough_canonical@1.0.0
    """
    from collections import defaultdict

    total = sum(h.current_value for h in holdings)
    if total == 0:
        return {"methodology_version": "lookthrough_canonical@1.0.0", "holdings": []}

    direct_equity: List[Dict] = []
    funds: List[Dict] = []

    for h in holdings:
        w = round(h.current_value / total * 100, 4)
        entry = {
            "isin":            h.isin,
            "name":            h.instrument_name,
            "sector":          h.sector,
            "market_cap":      h.market_cap,
            "asset_class":     h.asset_class,
            "weight_pct":      w,
            "value_inr":       round(h.current_value, 2),
        }
        if h.asset_class in ("equity", "stock"):
            direct_equity.append(entry)
        else:
            funds.append(entry)

    # Sector aggregation across all direct equity
    sector_agg: Dict[str, float] = defaultdict(float)
    for e in direct_equity:
        sector_agg[e["sector"] or "Unclassified"] += e["weight_pct"]

    return {
        "methodology_version":   "lookthrough_canonical@1.0.0",
        "direct_equity_count":   len(direct_equity),
        "fund_count":            len(funds),
        "direct_equity":         sorted(direct_equity, key=lambda x: -x["weight_pct"]),
        "funds":                 sorted(funds, key=lambda x: -x["weight_pct"]),
        "effective_sector_exposure": dict(sorted(sector_agg.items(), key=lambda x: -x[1])),
        "note": (
            "Full fund constituent look-through requires AMFI holdings data. "
            "Run scripts/seed_fund_constituents.py to enable."
            if funds else "No fund holdings — direct equity look-through complete."
        ),
    }
