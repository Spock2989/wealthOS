
from typing import List, Dict
from app.normalizer.canonical_schema import CanonicalHolding
import math

def run(holdings: List[CanonicalHolding], total: float) -> Dict:
    if not holdings or not total:
        return {"score": 0, "grade": "F"}
    weights = [h.current_value / total for h in holdings if h.current_value > 0]
    entropy = -sum(w * math.log(w) for w in weights if w > 0)
    max_entropy = math.log(len(weights)) if len(weights) > 1 else 1
    norm = entropy / max_entropy if max_entropy else 0

    classes = len(set(h.asset_class for h in holdings))
    sectors = len(set(h.sector for h in holdings if h.sector and h.sector != "Unclassified"))
    class_bonus  = min(classes / 5, 1.0) * 0.15
    sector_bonus = min(sectors / 8, 1.0) * 0.10

    score = round((norm * 0.75 + class_bonus + sector_bonus) * 100, 1)
    score = max(0, min(100, score))

    if score >= 80: grade = "A"
    elif score >= 70: grade = "B"
    elif score >= 60: grade = "C"
    elif score >= 50: grade = "D"
    else: grade = "F"
    return {"score": score, "grade": grade, "entropy": round(entropy, 4),
            "asset_class_count": classes, "sector_count": sectors}
