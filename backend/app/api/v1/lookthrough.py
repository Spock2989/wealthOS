"""
WealthOS — Look-Through Engine API Route
GET /api/v1/lookthrough/{portfolio_id}

What this computes from DB holdings (no external data required):
  1. Effective sector exposure  — weighted by current_value
  2. Effective market-cap split — weighted by current_value, equity only
  3. Fund overlap detection     — pairs of holdings sharing the same ISIN
  4. Hidden concentration       — any sector > threshold_pct of portfolio
  5. Asset class breakdown      — equity / debt / hybrid / other
  6. Top holdings by value

NOTE on full look-through (fund → constituent stocks):
  Full recursive decomposition requires fund holdings data from AMFI API or
  AMC disclosures (portfolio disclosure XMLs). This route computes effective
  exposure from the REPORTED holdings only. When AMFI integration is live,
  this route will be upgraded to use engines/lookthrough_engine.py with
  fund_constituents data. The current output is marked methodology_version
  "lookthrough_v1.0_direct" to distinguish it from the full v2 decomposition.

Output contract:
  {
    "portfolio_id": str,
    "total_value_inr": float,
    "holding_count": int,
    "effective_sector_exposure": {sector: pct},
    "effective_market_cap": {cap_bucket: pct_of_equity},
    "asset_class_breakdown": {class: pct},
    "top_holdings": [...],
    "overlap_flags": [...],
    "hidden_concentration": [...],
    "data_quality": {...},
    "methodology_version": "lookthrough_v1.0_direct"
  }
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../../.."))

from collections import defaultdict
from typing import List, Dict
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.models.holding import Holding
from app.services.portfolio_service import PortfolioService

router = APIRouter(prefix="/lookthrough", tags=["lookthrough"])


# ── Deterministic computations ────────────────────────────────

def _effective_sector_exposure(holdings: List[Holding], total: float) -> Dict[str, float]:
    by_sector: Dict[str, float] = defaultdict(float)
    for h in holdings:
        sec = (h.sector or "Unclassified").strip()
        by_sector[sec] += h.current_value
    return dict(
        sorted(
            {k: round(v / total * 100, 2) for k, v in by_sector.items()}.items(),
            key=lambda x: -x[1],
        )
    )


def _effective_market_cap(holdings: List[Holding]) -> Dict[str, float]:
    eq_holdings = [h for h in holdings if (h.asset_class or "").lower() == "equity"]
    eq_total = sum(h.current_value for h in eq_holdings)
    if not eq_total:
        return {}
    by_cap: Dict[str, float] = defaultdict(float)
    for h in eq_holdings:
        cap = (h.market_cap or "n_a").strip()
        by_cap[cap] += h.current_value
    return dict(
        sorted(
            {k: round(v / eq_total * 100, 2) for k, v in by_cap.items()}.items(),
            key=lambda x: -x[1],
        )
    )


def _asset_class_breakdown(holdings: List[Holding], total: float) -> Dict[str, float]:
    by_class: Dict[str, float] = defaultdict(float)
    for h in holdings:
        cls = (h.asset_class or "other").strip().lower()
        by_class[cls] += h.current_value
    return dict(
        sorted(
            {k: round(v / total * 100, 2) for k, v in by_class.items()}.items(),
            key=lambda x: -x[1],
        )
    )


def _top_holdings(holdings: List[Holding], total: float, n: int = 20) -> List[Dict]:
    sorted_h = sorted(holdings, key=lambda h: h.current_value, reverse=True)[:n]
    return [
        {
            "rank":              i + 1,
            "instrument_name":   h.instrument_name,
            "isin":              h.isin or "—",
            "asset_class":       h.asset_class,
            "sector":            h.sector or "—",
            "market_cap":        h.market_cap or "—",
            "current_value_inr": round(h.current_value, 2),
            "allocation_pct":    round(h.current_value / total * 100, 3),
        }
        for i, h in enumerate(sorted_h)
    ]


def _detect_isin_overlap(holdings: List[Holding]) -> List[Dict]:
    """
    Flag any ISIN that appears more than once — indicates duplicate positions
    or cross-fund holdings of the same instrument.
    """
    isin_map: Dict[str, List[Holding]] = defaultdict(list)
    for h in holdings:
        if h.isin:
            isin_map[h.isin].append(h)

    overlaps = []
    for isin, group in isin_map.items():
        if len(group) > 1:
            total_value = sum(g.current_value for g in group)
            overlaps.append({
                "isin":             isin,
                "instrument_name":  group[0].instrument_name,
                "occurrences":      len(group),
                "combined_value":   round(total_value, 2),
                "holdings":         [
                    {
                        "instrument_name": g.instrument_name,
                        "current_value":   round(g.current_value, 2),
                    }
                    for g in group
                ],
                "flag": "DUPLICATE_ISIN",
                "note": f"{isin} held across {len(group)} entries — verify intentional or duplicate CAS import.",
            })

    return sorted(overlaps, key=lambda x: -x["combined_value"])


def _detect_hidden_concentration(
    sector_exp: Dict[str, float],
    threshold_pct: float = 30.0,
) -> List[Dict]:
    flags = []
    for sector, pct in sector_exp.items():
        if pct >= threshold_pct:
            severity = "CRITICAL" if pct >= 40 else "HIGH"
            flags.append({
                "sector":       sector,
                "exposure_pct": pct,
                "threshold_pct": threshold_pct,
                "severity":     severity,
                "note": f"{sector} at {pct:.1f}% exceeds {threshold_pct}% concentration threshold.",
            })
    return sorted(flags, key=lambda x: -x["exposure_pct"])


def _data_quality(holdings: List[Holding]) -> Dict:
    total = len(holdings)
    if not total:
        return {"total": 0, "isin_coverage_pct": 0, "sector_coverage_pct": 0}
    with_isin   = sum(1 for h in holdings if h.isin)
    with_sector = sum(1 for h in holdings if h.sector)
    with_cap    = sum(1 for h in holdings if h.market_cap)
    missing_isin = [
        {"instrument_name": h.instrument_name, "asset_class": h.asset_class}
        for h in holdings if not h.isin
    ][:10]  # cap at 10 to keep payload reasonable
    return {
        "total_holdings":         total,
        "isin_coverage_pct":      round(with_isin   / total * 100, 1),
        "sector_coverage_pct":    round(with_sector / total * 100, 1),
        "market_cap_coverage_pct":round(with_cap    / total * 100, 1),
        "missing_isin_count":     total - with_isin,
        "missing_isin_sample":    missing_isin,
        "lookthrough_depth":      "direct_holdings_only",
        "full_lookthrough_ready": False,
        "full_lookthrough_note": (
            "Full recursive fund→stock look-through requires AMFI portfolio disclosure "
            "integration (Phase 2). Current output reflects reported holdings only."
        ),
    }


# ── Route ─────────────────────────────────────────────────────
@router.get("/{portfolio_id}")
def get_lookthrough(
    portfolio_id: str,
    concentration_threshold: float = 30.0,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Compute effective exposure, overlap flags, and concentration alerts
    from the portfolio's direct holdings.

    Query param `concentration_threshold` (default 30.0) controls
    the sector exposure % at which a hidden-concentration flag fires.
    """
    svc = PortfolioService(db)
    portfolio = svc.get(portfolio_id, current_user.id)
    if not portfolio:
        raise HTTPException(404, "Portfolio not found")

    holdings = svc.get_holdings(portfolio_id)
    if not holdings:
        raise HTTPException(422, "Portfolio has no holdings. Upload a CAS file first.")

    total = sum(h.current_value for h in holdings)
    if total <= 0:
        raise HTTPException(422, "Portfolio total value is zero — cannot compute exposures.")

    sector_exp  = _effective_sector_exposure(holdings, total)
    cap_exp     = _effective_market_cap(holdings)
    class_exp   = _asset_class_breakdown(holdings, total)
    top_h       = _top_holdings(holdings, total, n=20)
    overlaps    = _detect_isin_overlap(holdings)
    conc_flags  = _detect_hidden_concentration(sector_exp, concentration_threshold)
    dq          = _data_quality(holdings)

    # Summary interpretation
    top_sector      = next(iter(sector_exp), None)
    top_sector_pct  = sector_exp.get(top_sector, 0) if top_sector else 0
    conc_risk_level = (
        "CRITICAL" if top_sector_pct >= 40
        else "HIGH"   if top_sector_pct >= 30
        else "MEDIUM" if top_sector_pct >= 20
        else "LOW"
    )

    return {
        "portfolio_id":               portfolio_id,
        "portfolio_name":             portfolio.name or portfolio.filename,
        "total_value_inr":            round(total, 2),
        "holding_count":              len(holdings),
        "effective_sector_exposure":  sector_exp,
        "effective_market_cap":       cap_exp,
        "asset_class_breakdown":      class_exp,
        "top_holdings":               top_h,
        "overlap_flags":              overlaps,
        "hidden_concentration":       conc_flags,
        "summary": {
            "top_sector":               top_sector,
            "top_sector_pct":           top_sector_pct,
            "concentration_risk_level": conc_risk_level,
            "overlap_flag_count":       len(overlaps),
            "concentration_flag_count": len(conc_flags),
        },
        "data_quality":               dq,
        "methodology_version":        "lookthrough_v1.0_direct",
    }
