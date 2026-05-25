Below is your institutional-grade “Claude Build Document”. This is structured so Claude behaves like a staff-level fintech architect + quant engineer, not a generic AI.
Use this as-is inside your project.

🧠 WEALTHOS CORE
INSTITUTIONAL FINANCIAL INTELLIGENCE SYSTEM — BUILD INSTRUCTIONS FOR CLAUDE
0. SYSTEM DEFINITION
You are building WealthOS Core, a financial intelligence infrastructure system for Indian mutual fund and equity portfolios.
This is NOT:

a dashboard
a chatbot
a reporting tool
a robo-advisor
This IS:
A deterministic financial data + exposure + scenario propagation engine
1. CORE OBJECTIVE
Design a system that converts raw financial inputs into:
OUTPUTS
portfolio truth layer
fund + stock overlap map
concentration risk metrics
macro + micro exposure graph
scenario-based impact analysis
explainable risk decomposition
2. HARD DESIGN PRINCIPLES (NON-NEGOTIABLE)
2.1 Deterministic First
Every output must be reproducible.
If result cannot be recomputed exactly → reject design.

2.2 No AI Dependency for Core Math
AI is NOT allowed for:
portfolio calculation
risk computation
exposure modeling
aggregation logic
AI allowed ONLY for:
text explanation layer (optional later)
parsing assistance
2.3 Canonical Data Model
There must be a single source of truth:
Instrument ID is mandatory
ISIN preferred key
AMC scheme code secondary
name matching is fallback only
2.4 Traceability Required
Every output must be traceable back to:
source file
transformation step
calculation logic
2.5 Indian Market Reality Assumption
System must handle:
inconsistent AMC naming
missing ISINs
multiple scheme variants
delayed portfolio disclosures
duplicate holdings across funds
3. SYSTEM ARCHITECTURE (MANDATORY DESIGN)
Design system with the following layers:
3.1 INGESTION LAYER
Responsibilities:
ingest CAS PDFs
ingest CAMS / KFin Excel files
ingest manual uploads
extract raw holdings
Output:
raw_portfolio_data
No cleaning yet.
3.2 NORMALIZATION ENGINE (CRITICAL CORE)
Responsibilities:
map all instruments to canonical IDs
resolve AMC + scheme naming conflicts
normalize ISINs
maintain alias dictionary
create reconciliation logs
Output:
canonical_instruments_table
MUST INCLUDE:
ISIN mapping
instrument identity resolution
duplicate detection logic
3.3 PORTFOLIO RECONSTRUCTION ENGINE
Responsibilities:
rebuild actual portfolio holdings
compute weights
unify multiple CAS sources
resolve duplicates
Output:
portfolio_snapshot
Includes:
holdings
weights
valuation date
scheme breakdown
3.4 LOOKTHROUGH ENGINE (CRITICAL DIFFERENTIATOR)
Responsibilities:
Break mutual funds into:
Mutual Fund → Underlying Stocks → Sectors → Macro exposure

Example:
HDFC Flexi Cap Fund →
Reliance (8%)
HDFC Bank (6%)
Then expand:
sectors
macro sensitivity
Output:
lookthrough_exposure_map
3.5 EXPOSURE GRAPH ENGINE
Build a weighted graph:
NODES:
Portfolio
Mutual Fund
Stock
Sector
Macro variable
EDGES:
exposure weight
dependency strength
correlation (derived, not guessed)
Output:
Graph structure (adjacency list or graph DB model)
3.6 QUANT ANALYTICS ENGINE (DETERMINISTIC MATH CORE)
This is the mathematical brain.
A. Portfolio Weight
w_i = value_i / total_portfolio_value
B. Concentration Risk (HHI)
HHI = Σ (w_i²)
C. Effective Diversification
Neff = 1 / HHI
D. Volatility (Historical)
log returns
rolling std deviation
annualized volatility
E. Drawdown Engine
peak-to-trough analysis
max drawdown per asset and portfolio
F. Overlap Engine
Compute:
fund vs fund overlap
stock duplication across funds
direct + indirect exposure aggregation
OUTPUT:
quant_metrics
3.7 SCENARIO PROPAGATION ENGINE (MOST IMPORTANT)
This is your institutional differentiator.
STEP 1: Macro event input
Example:
oil price spike
interest rate change
geopolitical shock
STEP 2: Macro → Sector mapping
Rule-based system:
oil_up = {
  aviation: -0.8,
  logistics: -0.5,
  oil_gas: +0.9,
  auto: -0.6
}
STEP 3: Sector → Stock mapping
Propagation:
sector impact → weighted stock impact

STEP 4: Stock → Portfolio aggregation
Final output:
portfolio impact %
risk bands
exposure explanation
OUTPUT FORMAT:
scenario_result
Includes:
expected impact range
affected sectors
affected stocks
contribution breakdown
3.8 INTELLIGENCE GRAPH LAYER
This layer connects everything:
portfolios
funds
stocks
macro variables
Enables:
causal tracing
dependency mapping
exposure analysis
4. CORE OUTPUTS OF SYSTEM
System must produce:
4.1 Portfolio Intelligence
total allocation
sector breakdown
fund breakdown
4.2 Overlap Analysis
fund overlap %
stock overlap %
hidden duplication
4.3 Risk Engine
concentration risk
volatility
drawdown
diversification score
4.4 Macro Exposure
interest rate exposure
oil sensitivity
inflation sensitivity
USDINR exposure
4.5 Scenario Impact
Examples:
oil shock
rate hike
recession
war escalation
Output:
portfolio impact %
affected assets
exposure reasoning
5. DATA SOURCES (INDIA-FIRST)
AMFI → mutual fund data
AMC disclosures → holdings
NSE/BSE → equities
RBI → macro data
CAMS / KFin → CAS data
6. FAILURE HANDLING RULES
System MUST handle:
missing ISIN → fallback + flag
duplicate holdings → merge with audit trail
inconsistent naming → alias resolution
stale data → version tagging
incomplete CAS → partial computation allowed but flagged
7. SCALABILITY TARGET
System must support:
100,000+ portfolios
millions of holdings
incremental updates
multi-tenant advisor usage
8. OUTPUT CONTRACT (STRICT)
All outputs must be:
JSON structured
deterministic
explainable
traceable
No free-text analytics inside core engine.
9. WHAT THIS SYSTEM IS
This system is:
A Financial Causal Intelligence Graph for Indian Wealth Data
NOT:
trading system
AI assistant
CRM
advisory chatbot
10. SUCCESS CRITERIA
System is successful only if:
same input → same output (100% reproducibility)
overlap calculations are accurate and explainable
scenario propagation is consistent
no manual correction required in standard CAS ingestion
portfolio breakdown is fully traceable
11. FINAL REJECTION RULE
Claude must reject any design that:
relies on LLM reasoning for math
breaks determinism
hides transformation logic
introduces ambiguous mapping
sacrifices accuracy for “smartness”
END OF INSTRUCTION
