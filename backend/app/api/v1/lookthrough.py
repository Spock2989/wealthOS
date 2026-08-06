"""
WealthOS — Look-Through Engine API Route  v2.0
GET /api/v1/lookthrough/{portfolio_id}
POST /api/v1/lookthrough/{portfolio_id}/refresh   (force AMFI refresh)

What this returns:
  1. Effective stock exposure  — recursive fund→stock decomposition
  2. Cross-fund overlap        — stocks held via multiple funds
  3. Fund-vs-fund overlap      — pairwise overlap matrix for all fund pairs
  4. Direct holdings           — top holdings by value
  5. Data quality              — which funds have constituent data vs pending

Look-through depth:
  - Funds with AMFI constituent data → full recursive decomposition
  - Funds without data              → shown as black-box with their reported
                                       sector/cap, marked "data_pending"

Data flow:
  CAS holdings (DB) → amfi_instruments (ISIN→scheme_code)
  → fund_constituents (cached AMFI portfolio) → lookthrough computation

Output contract:
  {
    "portfolio_id": str,
    "total_value_inr": float,
    "holding_count": int,
    "lookthrough_depth": "full" | "partial" | "direct_only",
    "top_underlying_holdings": [...],     # stocks ranked by effective weight
    "cross_fund_overlap": [...],          # stocks in 2+ funds
    "fund_pair_overlap": [...],           # pairwise fund overlap
    "effective_sector_exposure": {...},   # sector breakdown post look-through
    "effective_market_cap": {...},        # cap split post look-through
    "data_quality": {...},
    "methodology_version": "lookthrough_v2.0_amfi"
  }
"""

import os
import logging
from collections import defaultdict
from typing import List, Dict

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.services.portfolio_service import PortfolioService
from app.services.amfi_holdings_service import build_portfolio_lookthrough

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/lookthrough", tags=["lookthrough"])

# Path to SQLite DB — the amfi_instruments + fund_constituents tables live here.
# Resolve against the backend directory so relative paths (sqlite:///wealthos.db)
# work regardless of the process cwd.
def _resolve_db_path() -> str:
    raw = os.environ.get("DATABASE_URL", "wealthos.db")
    # Strip SQLite URI prefix
    path = raw.replace("sqlite:////", "/").replace("sqlite:///", "")
    if not os.path.isabs(path):
        # Relative path → anchor to this file's backend directory
        backend_dir = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "..")
        )
        path = os.path.join(backend_dir, path)
    return path

_DB_PATH = _resolve_db_path()


def _holdings_to_dicts(holdings) -> List[Dict]:
    """Convert SQLAlchemy Holding ORM objects to plain dicts for the service layer."""
    return [
        {
            "isin":            h.isin or "",
            "instrument_name": h.instrument_name or "",
            "current_value":   float(h.current_value or 0),
            "asset_class":     h.asset_class or "equity",
            "sector":          h.sector or "",
            "market_cap":      h.market_cap or "",
        }
        for h in holdings
    ]


def _aggregate_sector(underlying_positions: List[Dict]) -> Dict[str, float]:
    """Roll up effective sector exposure from look-through positions."""
    sectors: Dict[str, float] = defaultdict(float)
    for p in underlying_positions:
        s = p.get("sector") or "Unclassified"
        sectors[s] += p.get("effective_weight_pct", 0)
    return dict(sorted(sectors.items(), key=lambda x: -x[1]))


def _aggregate_market_cap(underlying_positions: List[Dict]) -> Dict[str, float]:
    """Roll up effective market cap exposure from look-through positions."""
    caps: Dict[str, float] = defaultdict(float)
    for p in underlying_positions:
        cap = p.get("market_cap") or "unclassified"
        caps[cap] += p.get("effective_weight_pct", 0)
    return {k: round(v, 2) for k, v in sorted(caps.items(), key=lambda x: -x[1])}


def _determine_depth(dq: Dict) -> str:
    """
    Classify look-through depth by BOTH coverage and provenance.

    Coverage alone is not enough: a portfolio whose funds are all modelled has
    complete coverage and zero real data. Reporting that as "full" put a green
    FULL LOOK-THROUGH badge directly beside a banner saying the data was
    estimated. "full" now means every constituent came from a real AMFI
    disclosure — nothing else earns it.

      direct_only       no funds at all
      estimated         every decomposed fund is modelled
      partial_estimated some modelled, and some funds have no data
      partial           real data, but some funds have none
      full              every fund decomposed from a real disclosure
    """
    without   = dq.get("funds_without_constituents", 0)
    synthetic = dq.get("funds_synthetic_count", 0)
    total_funds = dq.get("funds_with_constituents", 0) + without

    if total_funds == 0:
        return "direct_only"
    if synthetic > 0:
        return "partial_estimated" if without > 0 else "estimated"
    if without == 0:
        return "full"
    return "partial"


@router.get("/{portfolio_id}")
def get_lookthrough(
    portfolio_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Full portfolio look-through.
    Uses cached AMFI constituent data where available; falls back to
    direct holding classification where not.
    """
    svc       = PortfolioService(db)
    portfolio = svc.get(portfolio_id, current_user.id)
    if not portfolio:
        raise HTTPException(404, "Portfolio not found")

    holdings = svc.get_holdings(portfolio_id)
    if not holdings:
        raise HTTPException(422, "Portfolio has no holdings. Upload a CAS file first.")

    total = sum(h.current_value for h in holdings if h.current_value)
    if total <= 0:
        raise HTTPException(422, "Portfolio total value is zero.")

    holdings_dicts = _holdings_to_dicts(holdings)

    # Run full look-through
    report = build_portfolio_lookthrough(holdings_dicts, _DB_PATH, force_refresh=False)
    if not report:
        raise HTTPException(500, "Look-through computation returned empty result.")

    dq    = report.get("data_quality", {})
    depth = _determine_depth(dq)

    # Post look-through sector + cap aggregation
    eff_sector = _aggregate_sector(report.get("top_underlying_holdings", []))
    eff_cap    = _aggregate_market_cap(report.get("top_underlying_holdings", []))

    return {
        "portfolio_id":              portfolio_id,
        "portfolio_name":            portfolio.name or portfolio.filename,
        "total_value_inr":           round(total, 2),
        "holding_count":             len(holdings),
        "lookthrough_depth":         depth,
        "top_underlying_holdings":   report.get("top_underlying_holdings", []),
        "total_underlying_positions":report.get("total_underlying_positions", 0),
        "cross_fund_overlap":        report.get("cross_fund_overlap", []),
        "fund_pair_overlap":         report.get("fund_pair_overlap", []),
        "effective_sector_exposure": eff_sector,
        "effective_market_cap":      eff_cap,
        "data_quality":              dq,
        "methodology_version":       "lookthrough_v2.0_amfi",
    }


@router.post("/{portfolio_id}/refresh")
def refresh_lookthrough(
    portfolio_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Force-refresh AMFI constituent data for all funds in this portfolio.
    Triggers live AMFI API calls (ignores cache). Use sparingly — AMFI
    publishes new disclosures monthly.
    """
    svc       = PortfolioService(db)
    portfolio = svc.get(portfolio_id, current_user.id)
    if not portfolio:
        raise HTTPException(404, "Portfolio not found")

    holdings = svc.get_holdings(portfolio_id)
    if not holdings:
        raise HTTPException(422, "Portfolio has no holdings.")

    total = sum(h.current_value for h in holdings if h.current_value)
    if total <= 0:
        raise HTTPException(422, "Portfolio total value is zero.")

    holdings_dicts = _holdings_to_dicts(holdings)
    report = build_portfolio_lookthrough(holdings_dicts, _DB_PATH, force_refresh=True)

    dq    = report.get("data_quality", {})
    depth = _determine_depth(dq)

    return {
        "portfolio_id":              portfolio_id,
        "total_value_inr":           round(total, 2),
        "lookthrough_depth":         depth,
        "funds_refreshed":           dq.get("funds_with_constituents", 0),
        "funds_pending":             dq.get("funds_without_constituents", 0),
        "pending_list":              dq.get("funds_pending_data", []),
        "top_underlying_holdings":   report.get("top_underlying_holdings", []),
        "total_underlying_positions":report.get("total_underlying_positions", 0),
        "cross_fund_overlap":        report.get("cross_fund_overlap", []),
        "fund_pair_overlap":         report.get("fund_pair_overlap", []),
        "methodology_version":       "lookthrough_v2.0_amfi",
    }
