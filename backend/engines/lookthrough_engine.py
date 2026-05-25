"""
WealthOS Look-Through Engine
Recursive mutual-fund decomposition to underlying stocks.
Effective exposure aggregation, overlap detection, hidden concentration.
"""

from typing import List, Dict, Tuple
from collections import defaultdict


# ── CORE LOOK-THROUGH ───────────────────────────────────────────
def lookthrough_decompose(holdings: List, max_depth: int = 2) -> Dict[str, Dict]:
    """
    Recursively decompose every fund into its underlying holdings.

    holdings: List[Holding] from DB. Each has .instrument with .fund_constituents.
    fund_constituents: {underlying_isin: weight_in_fund}

    Returns: {underlying_isin: {name, sector, market_cap, effective_weight, sources}}
    """
    underlying = defaultdict(lambda: {
        "name":             None,
        "sector":           None,
        "market_cap":       None,
        "effective_weight": 0.0,
        "sources":          [],
    })

    for h in holdings:
        if not h.instrument:
            continue
        holding_weight = (h.weight or 0) / 100

        # Direct stock — pass through
        if h.instrument.asset_class == "equity" and not h.instrument.fund_constituents:
            isin = h.instrument.isin or h.instrument.id
            underlying[isin]["name"]              = h.instrument.name
            underlying[isin]["sector"]            = h.instrument.sector
            underlying[isin]["market_cap"]        = h.instrument.market_cap_bucket
            underlying[isin]["effective_weight"] += holding_weight
            underlying[isin]["sources"].append({
                "type":          "direct",
                "fund_name":     h.instrument.name,
                "contribution":  round(holding_weight * 100, 3),
            })
            continue

        # Mutual fund — recursively decompose
        if h.instrument.fund_constituents:
            for underlying_isin, fund_weight in h.instrument.fund_constituents.items():
                effective_contrib = holding_weight * fund_weight
                underlying[underlying_isin]["effective_weight"] += effective_contrib
                underlying[underlying_isin]["sources"].append({
                    "type":          "via_fund",
                    "fund_name":     h.instrument.name,
                    "fund_weight":   round(holding_weight * 100, 3),
                    "fund_constituent_weight": round(fund_weight * 100, 3),
                    "contribution":  round(effective_contrib * 100, 3),
                })

    # Normalize + sort
    result = {}
    for isin, data in underlying.items():
        result[isin] = {
            **data,
            "effective_weight_pct": round(data["effective_weight"] * 100, 3),
            "is_held_via_multiple_funds": len(data["sources"]) > 1,
        }

    return dict(sorted(
        result.items(),
        key=lambda x: x[1]["effective_weight_pct"],
        reverse=True
    ))


# ── FUND-VS-FUND OVERLAP ────────────────────────────────────────
def fund_pairwise_overlap(holdings: List) -> List[Dict]:
    """
    For every pair of mutual funds in the portfolio, compute % overlap.
    Overlap = sum of MIN(weight in fund A, weight in fund B) for each shared holding.

    Returns sorted list of fund pairs with overlap >5%.
    """
    funds = [h for h in holdings
             if h.instrument and h.instrument.fund_constituents]
    pairs = []
    for i, fund_a in enumerate(funds):
        for fund_b in funds[i+1:]:
            ca = fund_a.instrument.fund_constituents
            cb = fund_b.instrument.fund_constituents
            shared      = set(ca) & set(cb)
            overlap_pct = sum(min(ca[isin], cb[isin]) for isin in shared) * 100
            if overlap_pct >= 5:
                pairs.append({
                    "fund_a":      fund_a.instrument.name,
                    "fund_b":      fund_b.instrument.name,
                    "overlap_pct": round(overlap_pct, 2),
                    "shared_holdings_count": len(shared),
                    "shared_isins": list(shared)[:10],
                })

    return sorted(pairs, key=lambda x: x["overlap_pct"], reverse=True)


# ── HIDDEN CONCENTRATION ────────────────────────────────────────
def detect_hidden_concentration(holdings: List, threshold_pct: float = 5.0) -> List[Dict]:
    """
    Find stocks held across multiple funds where TOTAL effective exposure exceeds threshold.
    Example: Investor owns 5 large-cap funds — each holds 8% HDFC Bank.
    Direct HDFC Bank position: 0%. Effective: 5 × 8% × avg_weight.

    Returns instruments where effective exposure > threshold AND held via 2+ vehicles.
    """
    decomp = lookthrough_decompose(holdings)
    hidden = []
    for isin, data in decomp.items():
        if (data["effective_weight_pct"] >= threshold_pct
                and data["is_held_via_multiple_funds"]):
            hidden.append({
                "isin":                 isin,
                "name":                 data["name"],
                "sector":               data["sector"],
                "effective_weight_pct": data["effective_weight_pct"],
                "sources_count":        len(data["sources"]),
                "sources":              data["sources"],
                "warning":              "high" if data["effective_weight_pct"] > 10 else "medium",
            })
    return hidden


# ── EFFECTIVE SECTOR EXPOSURE (POST LOOK-THROUGH) ──────────────
def effective_sector_exposure(holdings: List) -> Dict[str, float]:
    """
    True sector exposure AFTER decomposing every fund.
    Compare with surface-level sector exposure to surface hidden tilts.
    """
    decomp = lookthrough_decompose(holdings)
    sectors = defaultdict(float)
    for data in decomp.values():
        sector = data.get("sector") or "Unclassified"
        sectors[sector] += data["effective_weight_pct"]

    # Sort descending
    return dict(sorted(sectors.items(), key=lambda x: x[1], reverse=True))


def effective_market_cap_exposure(holdings: List) -> Dict[str, float]:
    """True market-cap exposure after look-through."""
    decomp = lookthrough_decompose(holdings)
    caps   = defaultdict(float)
    for data in decomp.values():
        cap = data.get("market_cap") or "unclassified"
        caps[cap] += data["effective_weight_pct"]
    return {
        "large":         round(caps.get("large", 0), 2),
        "mid":           round(caps.get("mid", 0), 2),
        "small":         round(caps.get("small", 0), 2),
        "multi":         round(caps.get("multi", 0), 2),
        "unclassified":  round(caps.get("unclassified", 0), 2),
    }


# ── MASTER LOOK-THROUGH REPORT ──────────────────────────────────
def compute_lookthrough_report(holdings: List) -> Dict:
    """Complete look-through report — for the dashboard."""
    if not holdings:
        return {}

    decomp        = lookthrough_decompose(holdings)
    overlap_pairs = fund_pairwise_overlap(holdings)
    hidden        = detect_hidden_concentration(holdings)
    eff_sector    = effective_sector_exposure(holdings)
    eff_cap       = effective_market_cap_exposure(holdings)

    # Top 20 underlying positions
    top_underlying = []
    for isin, data in list(decomp.items())[:20]:
        top_underlying.append({
            "isin":                 isin,
            "name":                 data["name"],
            "sector":               data["sector"],
            "market_cap":           data["market_cap"],
            "effective_weight_pct": data["effective_weight_pct"],
            "vehicles_count":       len(data["sources"]),
        })

    return {
        "total_underlying_positions": len(decomp),
        "top_underlying_holdings":    top_underlying,
        "effective_sector_exposure":  eff_sector,
        "effective_market_cap":       eff_cap,
        "fund_overlap_pairs":         overlap_pairs[:10],
        "hidden_concentration":       hidden,
        "methodology_version":        "lookthrough_v1.0",
    }
