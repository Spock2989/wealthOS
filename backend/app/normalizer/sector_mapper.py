
SECTOR_KEYWORDS = {
    "Financial Services": ["bank","hdfc","icici","axis","kotak","sbi","finance","nbfc","insurance","bajaj fin"],
    "Technology": ["tech","infy","infosys","tcs","wipro","hcl","software","it "],
    "Energy": ["reliance","oil","gas","petroleum","energy","power","ntpc","ongc"],
    "Healthcare": ["pharma","health","sun pharma","cipla","dr reddy","med","hospital"],
    "Consumer": ["fmcg","hul","hindustan","consumer","dabur","nestle","britannia","marico"],
    "Automobile": ["auto","maruti","tata motors","bajaj auto","hero","mahindra"],
    "Infrastructure": ["infra","l&t","larsen","cement","construction","irb"],
    "Metals": ["steel","metal","tata steel","jsw","hindalco","vedanta"],
    "Diversified": ["diversified","multi","flexi","balanced","hybrid"],
    "Fixed Income": ["bond","debt","gilt","liquid","money market","overnight","credit"],
}

ASSET_CLASS_KEYWORDS = {
    "equity": ["equity","stock","share","bluechip","midcap","smallcap","large cap","mid cap","small cap","flexi","elss","index","nifty","sensex"],
    "debt": ["debt","bond","gilt","income","credit","liquid","overnight","money market","fixed maturity","banking and psu","corporate bond","short term","medium term","long term","duration"],
    "hybrid": ["hybrid","balanced","aggressive","conservative","dynamic asset","multi asset","equity savings"],
    "cash": ["liquid","overnight","cash","savings","ultra short"],
    "international": ["international","global","us equity","nasdaq","s&p","world","emerging market","foreign"],
    "alternate": ["gold","silver","commodity","reit","invit","real estate","infrastructure inv"],
}

MARKET_CAP_KEYWORDS = {
    "large_cap": ["large cap","largecap","bluechip","blue chip","top 100","nifty 50","sensex","large & mid"],
    "mid_cap": ["mid cap","midcap","mid & small","emerging"],
    "small_cap": ["small cap","smallcap","micro cap","microcap"],
}

def classify_sector(name: str) -> str:
    n = name.lower()
    for sector, kws in SECTOR_KEYWORDS.items():
        if any(k in n for k in kws):
            return sector
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

RISK_SCORES = {"equity":7.0,"hybrid":5.0,"debt":3.0,"cash":1.0,"international":7.5,"alternate":6.0}
LIQUIDITY_SCORES = {"cash":10.0,"debt":8.0,"hybrid":7.0,"equity":8.0,"international":6.0,"alternate":4.0}

def get_risk_score(asset_class: str, market_cap: str) -> float:
    base = RISK_SCORES.get(asset_class, 6.0)
    if market_cap == "small_cap": base = min(base + 1.5, 10.0)
    elif market_cap == "mid_cap": base = min(base + 0.5, 10.0)
    return round(base, 1)

def get_liquidity_score(asset_class: str) -> float:
    return LIQUIDITY_SCORES.get(asset_class, 7.0)
