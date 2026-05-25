
from typing import List, Dict
from app.normalizer.canonical_schema import CanonicalHolding

KNOWN_OVERLAPS = [
    {"fund_a": "HDFC Mid-Cap", "fund_b": "Mirae Emerging", "overlap_pct": 28.0},
    {"fund_a": "Axis Bluechip", "fund_b": "ICICI Pru Bluechip", "overlap_pct": 42.0},
    {"fund_a": "HDFC Flexi Cap", "fund_b": "HDFC Mid-Cap", "overlap_pct": 22.0},
    {"fund_a": "Parag Parikh Flexi", "fund_b": "Axis Flexi Cap", "overlap_pct": 18.0},
    {"fund_a": "SBI Small Cap", "fund_b": "Nippon Small Cap", "overlap_pct": 35.0},
]

def run(holdings: List[CanonicalHolding]) -> Dict:
    names = [h.instrument_name.lower() for h in holdings]
    found_pairs = []
    total_overlap = 0.0
    for pair in KNOWN_OVERLAPS:
        a_match = any(pair["fund_a"].lower() in n for n in names)
        b_match = any(pair["fund_b"].lower() in n for n in names)
        if a_match and b_match:
            found_pairs.append(pair)
            total_overlap += pair["overlap_pct"] * 0.1
    isin_counts = {}
    for h in holdings:
        if h.isin:
            isin_counts[h.isin] = isin_counts.get(h.isin, 0) + 1
    isin_overlaps = sum(1 for c in isin_counts.values() if c > 1)
    return {"known_pair_overlaps": found_pairs,
            "total_overlap_pct_of_portfolio": round(min(total_overlap + isin_overlaps * 2, 40), 2),
            "duplicate_isin_count": isin_overlaps}
