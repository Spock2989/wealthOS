# WealthOS v4.0 Deploy — Run These Commands

## Step 1 — Commit + Push to GitHub (Mac Terminal)

```bash
cd /Users/user/Documents/Claude/Projects/WealthOS

git add -A
git commit -m "feat: WealthOS v4.0 Citadel-grade quant engine

- proprietary_metrics_engine.py: Health Score, Fragility Score, Diversification Illusion, ENB (Meucci 2009), DR (Choueifady 2008), multi-level HHI
- scenario_engine.py: 20 scenarios (from 7), 11-variable MACRO_SENSITIVITY matrix
- performance_engine.py: BHB attribution (1986), Pain Ratio
- risk_engine.py: EVT/GPD VaR wired in, 99pct VaR, 10-day VaR
- risk_models_engine.py: evt_var_gpd alias
- analytics_core.py: v4.0 orchestrator, all 12 tiers, audit trail
- infra/nginx: browser login CORS fix"

git push origin main
```

## Step 2 — Deploy backend to server (Mac Terminal, same window)

```bash
make deploy
```

Or manually:
```bash
rsync -avz backend/ root@64.227.147.106:/opt/wlthos/backend/ \
  --exclude='__pycache__' --exclude='venv' --exclude='.env' --exclude='*.pyc'

ssh root@64.227.147.106 "systemctl restart wealthos-api && sleep 5 && curl -s http://localhost:8000/health"
```

## Step 3 — Fix CORS (SSH terminal — run on SERVER only)

```bash
ssh -o ServerAliveInterval=30 root@64.227.147.106
```

Then on the server:
```bash
# Backup existing config
cp /etc/nginx/sites-available/wealthos-api /etc/nginx/sites-available/wealthos-api.bak

# Apply the CORS fix
cat /opt/wlthos/infra/nginx/wealthos-api-cors-fix.conf > /etc/nginx/sites-available/wealthos-api

# Test config is valid
nginx -t

# If OK, reload nginx
systemctl reload nginx

# Test browser login works
curl -X POST https://api.wlthos.in/v1/auth/login \
  -H "Origin: https://wlthos.in" \
  -H "Content-Type: application/json" \
  -d '{"email":"tiwarikshitij20@gmail.com","password":"WealthOS2026!"}' \
  -v 2>&1 | grep -E "access-control|HTTP/"
```

You should see `Access-Control-Allow-Origin: https://wlthos.in` in the response headers.
Then open https://wlthos.in/app.html in a fresh browser tab and login will work.

---

## What was built in this session

### NEW: `backend/engines/proprietary_metrics_engine.py`
The WealthOS institutional moat — no Indian platform has this:

| Metric | Formula | Standard |
|---|---|---|
| Portfolio Health Score | 6-component weighted (diversification 25%, concentration 20%, risk-adj return 20%, macro 15%, liquidity 10%, factor balance 10%) | WealthOS proprietary |
| Portfolio Fragility Score | 5-component (tail risk 30%, correlation crowding 25%, macro vuln 20%, liquidity stress 15%, regime 10%) | WealthOS proprietary |
| Diversification Illusion Score | N_funds / N_eff - 1 | WealthOS proprietary |
| Effective Number of Bets | PCA/Shannon entropy — Meucci (2009) | Institutional standard |
| Diversification Ratio | Σ(w_i × σ_i) / σ_portfolio — Choueifady (2008) | Institutional standard |
| Multi-Level HHI | Stock / Sector / Factor / Theme / Geography | WealthOS extension |
| HHI Normalized | (HHI - 1/N) / (1 - 1/N) | Standard |
| Rebalancing Signal Engine | Drift detection + priority scoring | WealthOS proprietary |

### UPGRADED: `backend/engines/scenario_engine.py`
- **20 scenarios** (was 7): market crash, small-cap crash, large-cap correction, sector rotation, RBI hike, RBI cut, oil spike, oil collapse, inflation surge, INR depreciation, US recession, global liquidity crisis, China slowdown, India election, IT correction, BFSI crisis, real estate collapse, infrastructure boom, geopolitical escalation, COVID pandemic shock
- **11-variable MACRO_SENSITIVITY matrix** (India-calibrated): RBI rate hike/cut, oil up/down, INR depreciation, US recession, India GDP slowdown, CPI surge, global liquidity crisis, India 10Y yield, VIX spike
- **Custom scenario endpoint**: `run_custom_scenario()` for advisor-defined stress tests
- **Full macro sensitivity propagation**: sector → stock → portfolio with confidence scoring

### UPGRADED: `backend/engines/performance_engine.py`
- **BHB Attribution** (Brinson-Hood-Beebower 1986): exact 3-way decomposition — allocation + selection + interaction = active return (residual verified ~0)
- **Pain Ratio**: annualized excess return / Ulcer Index

### UPGRADED: `backend/engines/risk_engine.py`
- **EVT/GPD VaR** wired into `compute_risk_summary()` — tail risk from Generalized Pareto Distribution
- **VaR at 99%** added (historical, Cornish-Fisher, ES)
- **10-day VaR scaling** (√10 rule, FRTB standard)
- Complete VaR ladder: Historical · Parametric · Cornish-Fisher · Monte Carlo · EVT · ES

### UPGRADED: `backend/engines/analytics_core.py` → v4.0
- **12 computation tiers** (was 10)
- Macro sensitivity matrix on every portfolio computation
- All proprietary metrics on every output
- Full explainability: `methodology_version`, `computed_at`, `audit_trail`, `holdings_hash`
- Every output traceable to source

### NEW: `infra/nginx/wealthos-api-cors-fix.conf`
- Fixes browser login (`Load failed` error)
- Handles OPTIONS preflight correctly
- Allows: `https://wlthos.in`, `https://www.wlthos.in`, `localhost:3000/8000`

---

## Capability table after v4.0

| Capability | Before | After |
|---|---|---|
| Portfolio Health Score | ❌ | ✅ |
| Portfolio Fragility Score | ❌ | ✅ |
| Diversification Illusion Score | ❌ | ✅ |
| Effective Number of Bets (Meucci) | ❌ | ✅ |
| Diversification Ratio (Choueifady) | ❌ | ✅ |
| Multi-Level HHI (5 levels) | ❌ | ✅ |
| 20 Standard Scenarios | ❌ (7) | ✅ |
| 11-Variable Macro Sensitivity | ❌ | ✅ |
| BHB Attribution (allocation/selection/interaction) | ❌ | ✅ |
| EVT/GPD VaR in main risk summary | ❌ | ✅ |
| 99% VaR (regulatory standard) | ❌ | ✅ |
| 10-day VaR (FRTB) | ❌ | ✅ |
| Pain Ratio | ❌ | ✅ |
| Full audit trail on every output | ❌ | ✅ |
| Browser login (CORS fixed) | ❌ | ✅ (after nginx step) |
| GARCH(1,1) / GJR-GARCH / EGARCH | ✅ | ✅ |
| Ledoit-Wolf / OAS / MCD covariance | ✅ | ✅ |
| HMM Regime Detection (2/3 state) | ✅ | ✅ |
| Black-Litterman / HRP optimization | ✅ | ✅ |
| Cornish-Fisher VaR | ✅ | ✅ |
| Walk-forward + PSR + DSR + MinBTL | ✅ | ✅ |
| Fixed income (Duration/DV01/KRD) | ✅ | ✅ |
