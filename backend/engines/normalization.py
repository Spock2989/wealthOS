import re
from sqlalchemy.orm import Session
from models import Instrument

NAME_ALIASES = {
    "hdfc bank": ["hdfc bank ltd", "hdfcbank eq", "hdfc bank limited"],
    "infosys": ["infosys ltd", "infosys limited", "infy"],
    "reliance industries": ["reliance ind", "ril", "reliance industries ltd"],
    "tcs": ["tata consultancy services", "tata consultancy services ltd"],
    "icici bank": ["icici bank ltd", "icici bank limited"],
    "sbi": ["state bank of india", "state bank of india eq", "sbin"],
    "bharti airtel": ["airtel", "bharti airtel ltd"],
    "larsen & toubro": ["l&t", "larsen and toubro", "larsen & toubro ltd"],
    "asian paints": ["asian paints ltd", "asian paints limited"],
    "hindustan unilever": ["hul", "hindustan unilever ltd", "hindustan lever"],
    "wipro": ["wipro ltd", "wipro limited"],
    "axis bank": ["axis bank ltd", "axis bank limited"],
    "kotak mahindra bank": ["kotak bank", "kotak mahindra bank ltd"],
    "sun pharmaceutical": ["sun pharma", "sun pharmaceutical industries"],
    "itc": ["itc ltd", "itc limited"],
    "maruti suzuki": ["maruti suzuki india ltd", "maruti"],
    "bajaj finance": ["bajaj finance ltd", "bajaj finance limited"],
}

_CANONICAL_MAP = {}
for canonical, aliases in NAME_ALIASES.items():
    for alias in aliases:
        _CANONICAL_MAP[alias.lower().strip()] = canonical

def normalize_instrument(raw: dict, db: Session) -> Instrument:
    isin        = raw.get("isin")
    amfi_code   = raw.get("amfi_code")
    raw_name    = raw.get("name", "").strip()
    asset_class = raw.get("asset_class", "equity")

    if isin:
        inst = db.query(Instrument).filter(Instrument.isin == isin).first()
        if inst:
            return inst

    if amfi_code:
        inst = db.query(Instrument).filter(Instrument.amfi_code == amfi_code).first()
        if inst:
            return inst

    canonical_name = _CANONICAL_MAP.get(raw_name.lower().strip())
    if canonical_name:
        inst = db.query(Instrument).filter(Instrument.canonical_name == canonical_name).first()
        if inst:
            if isin and not inst.isin:
                inst.isin = isin
                db.commit()
            return inst

    normalised = _normalise_name(raw_name)
    candidates = db.query(Instrument).filter(
        Instrument.name.ilike(f"%{normalised[:20]}%")
    ).limit(5).all()
    if candidates:
        best = _best_match(normalised, candidates)
        if best:
            return best

    inst = Instrument(
        isin=isin, amfi_code=amfi_code,
        name=raw_name,
        canonical_name=canonical_name or normalised,
        asset_class=asset_class,
        sector=_infer_sector(raw_name, asset_class),
        market_cap_bucket=_infer_market_cap(raw_name),
        factor_exposure=_default_factors(asset_class),
        macro_sensitivity=_default_macro(asset_class),
    )
    db.add(inst); db.commit(); db.refresh(inst)
    return inst

def _normalise_name(name: str) -> str:
    result = re.sub(r"\s*-\s*(growth|idcw|dividend|direct|regular|option|plan|series|gr)\s*", " ", name, flags=re.IGNORECASE)
    result = re.sub(r"\(.*?\)", " ", result)
    return result.strip().lower()

def _best_match(target, candidates):
    def overlap(a, b):
        wa = set(a.lower().split())
        wb = set(b.lower().split())
        if not wa or not wb: return 0
        return len(wa & wb) / max(len(wa), len(wb))
    scored = [(overlap(target, _normalise_name(c.name)), c) for c in candidates]
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[0][1] if scored and scored[0][0] > 0.5 else None

def _infer_sector(name: str, asset_class: str):
    if asset_class in ("debt", "liquid"): return "Fixed Income"
    n = name.lower()
    sectors = {
        "Banking & Financial Services": ["bank","bfsi","financial","finance"],
        "Technology": ["it","tech","software","digital","infotech"],
        "Healthcare": ["pharma","health","medic"],
        "Infrastructure": ["infra","infrastructure","construction"],
        "FMCG": ["fmcg","consumer","consumption"],
        "Auto": ["auto","automobile"],
        "Energy": ["energy","power","oil","gas"],
    }
    for sector, kws in sectors.items():
        if any(k in n for k in kws): return sector
    return "Diversified"

def _infer_market_cap(name: str):
    n = name.lower()
    if any(k in n for k in ["small cap","smallcap"]): return "small"
    if any(k in n for k in ["mid cap","midcap"]):     return "mid"
    if any(k in n for k in ["large cap","largecap"]): return "large"
    if any(k in n for k in ["flexi","multi cap"]):    return "multi"
    return None

def _default_factors(asset_class: str):
    if asset_class == "equity":
        return {"growth":0.5,"quality":0.5,"momentum":0.5,"value":0.5,"size":0.5,"volatility":0.5}
    if asset_class == "debt":
        return {"duration":0.7,"credit_quality":0.6}
    return {}

def _default_macro(asset_class: str):
    if asset_class == "equity":
        return ["market_returns","inflation","gdp_growth"]
    if asset_class == "debt":
        return ["interest_rates","inflation","credit_spread"]
    return ["market_returns"]