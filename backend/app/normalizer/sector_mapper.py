
# Sector names aligned with engines/scenario_engine.py MACRO_SENSITIVITY keys
# so fuzzy matching in _apply_scenario() hits exactly without needing heuristics.

SECTOR_KEYWORDS = {
    # Specific sectors — checked first (order matters: most specific → most general)
    "Banking & Financial Services": [
        "bank","hdfc","icici","axis","kotak","sbi","finance","nbfc","insurance",
        "bajaj fin","financial","bfsi","psu bank","banking",
    ],
    "IT": [
        "tech","infy","infosys","tcs","wipro","hcl","software","technology",
        "digital","coforge","mphasis","l&t tech","ltts","it fund","it sector",
    ],
    "Energy": [
        "reliance","oil","gas","petroleum","energy","power","ntpc","ongc",
        "coal","bpcl","hpcl","iocl","tata power","adani green","renewable",
    ],
    "Pharma": [
        "pharma","health","sun pharma","cipla","dr reddy","hospital","healthcare",
        "biocon","alkem","lupin","torrent pharma","med","diagnostic",
    ],
    "FMCG": [
        "fmcg","hul","hindustan","consumer","dabur","nestle","britannia","marico",
        "godrej","itc","emami","colgate","consumption",
    ],
    "Auto": [
        "auto","maruti","tata motors","bajaj auto","hero","mahindra","automobile",
        "eicher","m&m","tvs","vehicle","mobility",
    ],
    "Infrastructure": [
        "infra","l&t","larsen","cement","construction","irb","bhel",
        "gmr","adani port","transport","highway","road",
    ],
    "Metals": [
        "steel","metal","tata steel","jsw","hindalco","vedanta","copper",
        "aluminium","zinc","mining","mineral",
    ],
    "Fixed Income": [
        "bond","debt","gilt","liquid","money market","overnight","credit",
        "duration","corporate bond","income fund","banking and psu","floater",
        "short term","medium term","long term","dynamic bond",
    ],
    # Diversified — broad equity funds that don't have a single sector bias
    # Must come AFTER specific sectors so it doesn't over-capture
    "Diversified": [
        "diversified","multi cap","multi-cap","multicap",
        "flexi cap","flexi-cap","flexicap",
        "balanced advantage","balanced fund",
        "hybrid","elss","tax saver","tax saving",
        "value fund","contra","momentum",
        "bluestar","bluechip","blue chip",
        "large cap","large & mid","large mid",
        "mid cap","midcap","small cap","smallcap",
        "nifty","sensex","index fund","etf",
        "pms","aif","folio","portfolio",
    ],
}

ASSET_CLASS_KEYWORDS = {
    "equity":        ["equity","stock","share","bluechip","midcap","smallcap","large cap","mid cap","small cap","flexi","elss","index","nifty","sensex"],
    "debt":          ["debt","bond","gilt","income","credit","liquid","overnight","money market","fixed maturity","banking and psu","corporate bond","short term","medium term","long term","duration"],
    "hybrid":        ["hybrid","balanced","aggressive","conservative","dynamic asset","multi asset","equity savings"],
    "cash":          ["liquid","overnight","cash","savings","ultra short"],
    "international": ["international","global","us equity","nasdaq","s&p","world","emerging market","foreign"],
    "alternate":     ["gold","silver","commodity","reit","invit","real estate","infrastructure inv"],
}

MARKET_CAP_KEYWORDS = {
    "large_cap": ["large cap","largecap","bluechip","blue chip","top 100","nifty 50","sensex","large & mid"],
    "mid_cap":   ["mid cap","midcap","mid & small","emerging"],
    "small_cap": ["small cap","smallcap","micro cap","microcap"],
}

def classify_sector(name: str) -> str:
    """
    Classify a holding's sector by matching its name against keyword lists.
    Order in SECTOR_KEYWORDS matters: specific sectors checked before Diversified.
    Fallback: if name contains any mutual-fund indicator, return 'Diversified'.
    Returns 'Unclassified' only for names with no recognisable pattern.
    """
    n = name.lower()
    for sector, kws in SECTOR_KEYWORDS.items():
        if any(k in n for k in kws):
            return sector
    # Fallback: most unnamed equity instruments in India are diversified MFs
    FUND_INDICATORS = ["fund","plan","growth","direct","regular","option","scheme",
                       "series","class","tranche","folio","nav"]
    if any(k in n for k in FUND_INDICATORS):
        return "Diversified"
    return "Unclassified"

def classify_asset_class(name: str) -> str:
    n = name.lower()
    for ac, kws in ASSET_CLASS_KEYWORDS.items():
        if any(k in n for k in kws):
            return ac
    return "equity"

def classify_market_cap(name: str) -> str:
    n = name.lower()
    for cap, kws in MARKET_CAP_KEYWORDS.items():
        if any(k in n for k in kws):
            return cap
    return "n_a"

RISK_SCORES      = {"equity":7.0,"hybrid":5.0,"debt":3.0,"cash":1.0,"international":7.5,"alternate":6.0}
LIQUIDITY_SCORES = {"cash":10.0,"debt":8.0,"hybrid":7.0,"equity":8.0,"international":6.0,"alternate":4.0}

def get_risk_score(asset_class: str, market_cap: str) -> float:
    base = RISK_SCORES.get(asset_class, 6.0)
    if market_cap == "small_cap": base = min(base + 1.5, 10.0)
    elif market_cap == "mid_cap": base = min(base + 0.5, 10.0)
    return round(base, 1)

def get_liquidity_score(asset_class: str) -> float:
    return LIQUIDITY_SCORES.get(asset_class, 7.0)
