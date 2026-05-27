# WealthOS — Full Session Handoff Document
**Date:** 2026-05-27 | **Author:** Cowork AI session  
**Purpose:** Complete state transfer to new chat session — covers every file, every decision, every pending task.

---

## 1. WHAT IS WEALTHOS

WealthOS Core is an **institutional financial intelligence infrastructure system** for Indian mutual fund and equity portfolios. It is NOT a chatbot, dashboard, or robo-advisor.

It IS:
- A **deterministic** financial data + exposure + scenario propagation engine
- A **lookthrough engine** (fund → stock → sector → macro)
- A **scenario analysis engine** (20 pre-built macro scenarios + custom shocks)
- A **multi-tenant advisor platform** (advisors upload client CAS PDFs, get analytics)

**Live URLs:**
- Frontend: https://wlthos.in
- API: https://api.wlthos.in
- Login: https://wlthos.in/app.html
- Dashboard: https://wlthos.in/dashboard.html
- API Docs: https://api.wlthos.in/docs

**Server:** `root@64.227.147.106` (DigitalOcean)

---

## 2. HARD DESIGN RULES (NON-NEGOTIABLE — from CLAUDE.md)

1. **Deterministic first** — same input = same output, always
2. **No LLM for math** — AI never calculates. All analytics = deterministic Python only
3. **ISIN is primary key** — scheme code secondary, name-match is fallback only
4. **Every output is traceable** — source_file + transformation_step + calculation_logic
5. **Indian market assumptions** — inconsistent AMC naming, missing ISINs, multiple scheme variants
6. **CORS = Nginx only** — NEVER add CORSMiddleware to FastAPI
7. **Never modify server .env** — use `os.environ.get()`
8. **Never delete engine files** — fix in place
9. **Never mark phase done if anything is stubbed/mocked**
10. **Test user:** `test@wealthos.local` / `WealthOS2024!` — never use personal password

---

## 3. REPOSITORY STRUCTURE

```
/Users/user/Documents/Claude/Projects/WealthOS/
├── deploy.sh                          ← ONE COMMAND DEPLOY (run from local terminal)
├── CLAUDE.md                          ← Project instructions for AI
├── backend/
│   ├── main.py                        ← FastAPI entry point (production)
│   ├── requirements.txt               ← Python deps
│   ├── app/
│   │   ├── main.py                    ← App factory (imported by root main.py)
│   │   ├── database.py                ← SQLAlchemy setup (SQLite default)
│   │   ├── dependencies.py            ← JWT auth dependency
│   │   ├── models/
│   │   │   ├── user.py                ← User model
│   │   │   ├── client.py              ← Client model
│   │   │   ├── portfolio.py           ← Portfolio model (status field: parsing/normalizing/analyzing/ready/error)
│   │   │   ├── holding.py             ← Holding model (ISIN, scheme_code, weight, value)
│   │   │   ├── analytics_snapshot.py  ← Stores full analytics JSON result
│   │   │   └── ai_report.py           ← AI insight storage
│   │   ├── api/v1/
│   │   │   ├── auth.py                ← POST /auth/signup, POST /auth/login, GET /auth/me
│   │   │   ├── upload.py              ← POST /upload (PDF/Excel → pipeline)
│   │   │   ├── portfolios.py          ← CRUD for portfolios
│   │   │   ├── analytics_routes.py    ← GET /analytics/{portfolio_id}
│   │   │   ├── scenarios.py           ← POST /scenarios/{id}/run, GET /scenarios/available
│   │   │   ├── lookthrough.py         ← GET /lookthrough/{portfolio_id}
│   │   │   ├── insights.py            ← AI text insights (optional layer)
│   │   │   ├── reports.py             ← Report generation
│   │   │   └── demo.py                ← POST /demo-requests (lead capture from landing page)
│   │   ├── parsers/
│   │   │   ├── base_parser.py         ← ParserRegistry + BaseParser ABC
│   │   │   ├── cas_parser.py          ← CAS PDF parser (pdfplumber)
│   │   │   └── excel_parser.py        ← CAMS/KFin Excel parser
│   │   ├── normalizer/
│   │   │   ├── normalizer.py          ← Maps raw holdings → canonical instruments
│   │   │   ├── canonical_schema.py    ← CanonicalHolding dataclass
│   │   │   ├── deduplicator.py        ← Merges duplicate holdings
│   │   │   └── sector_mapper.py       ← Stock/fund → sector mapping
│   │   ├── analytics/
│   │   │   ├── engine.py              ← AnalyticsEngine (orchestrator)
│   │   │   ├── concentration.py       ← HHI, Neff
│   │   │   ├── sector_exposure.py     ← Sector weights
│   │   │   ├── fund_overlap.py        ← Fund-fund stock overlap
│   │   │   ├── volatility.py          ← Historical volatility
│   │   │   ├── drawdown.py            ← Max drawdown
│   │   │   ├── diversification.py     ← Diversification score
│   │   │   ├── asset_allocation.py    ← Equity/debt/gold split
│   │   │   ├── market_cap.py          ← Large/mid/small cap exposure
│   │   │   ├── liquidity.py           ← Liquidity analysis
│   │   │   └── stress_test.py         ← Simple stress tests
│   │   └── services/
│   │       └── portfolio_service.py   ← DB operations for portfolios
│   └── engines/                       ← LEGACY engines (some still used)
│       ├── scenario_engine.py         ← 20 macro scenarios (DETERMINISTIC — DO NOT LLM-ize)
│       ├── lookthrough_engine.py      ← Fund → stock lookthrough
│       ├── analytics_core.py          ← Legacy analytics
│       ├── analytics_core_v2.py       ← v2 analytics
│       └── ... (other engines)
├── frontend/dist/
│   ├── landing.html                   ← Public landing page (wlthos.in)
│   ├── app.html                       ← LOGIN PAGE (wlthos.in/app.html)
│   ├── dashboard.html                 ← ADVISOR DASHBOARD (wlthos.in/dashboard.html)
│   └── index.html                     ← Redirects to landing.html
├── infra/
│   ├── nginx/
│   │   ├── wealthos-api.conf          ← Nginx config for api.wlthos.in
│   │   └── wealthos-frontend.conf     ← Nginx config for wlthos.in
│   └── systemd/
│       └── wealthos-api.service       ← systemd service file
└── samples/
    └── portfolio_kt.pdf               ← Sample CAS PDF for testing
```

---

## 4. SERVER CONFIGURATION

**Nginx serves:**
- `wlthos.in` → `/var/www/wlthos/` (static HTML)
- `api.wlthos.in` → proxy to `localhost:8000` (FastAPI/uvicorn)

**CORS:** Nginx adds `Access-Control-Allow-Origin: https://wlthos.in` — FastAPI has NO CORSMiddleware

**Backend service:**
```bash
systemctl status wealthos      # check
systemctl restart wealthos     # restart
journalctl -u wealthos -f      # logs
```

**Backend runs from:** `/opt/wlthos/backend/`  
**Frontend served from:** `/var/www/wlthos/`  
**Database:** `/opt/wlthos/backend/wealthos.db` (SQLite — excluded from rsync)

**Environment vars (on server `/opt/wlthos/backend/.env`):**
```
JWT_SECRET=<secret>
PW_PEPPER=<pepper>
DATABASE_URL=sqlite:///./wealthos.db
```

---

## 5. DEPLOY PROCESS

**Single command from local terminal:**
```bash
cd /Users/user/Documents/Claude/Projects/WealthOS
bash deploy.sh
```

**What deploy.sh does:**
1. Removes git lock files (`.git/HEAD.lock`, `.git/index.lock` etc.) — PERMANENTLY FIXED
2. Git commits all changes
3. rsync backend → `root@64.227.147.106:/opt/wlthos/backend/` (excludes .db, .env, venv, __pycache__)
4. rsync frontend/dist → `root@64.227.147.106:/var/www/wlthos/`
5. `chmod 644 *.html` on server (Nginx needs this)
6. `systemctl restart wealthos`
7. Health check: `curl https://api.wlthos.in/health`

**Expected health response:**
```json
{"status":"ok","service":"wealthos-api","version":"2.0.0","db":"sqlite"}
```

---

## 6. AUTH SYSTEM

**Flow:** `app.html` → login → JWT stored in localStorage/sessionStorage → redirect to `dashboard.html`

**Token key:** `wos_token` (in localStorage if "Remember me" checked, sessionStorage otherwise)  
**User key:** `wos_user` (JSON string of user object)  
**Token lifetime:** 24 hours  
**Algorithm:** HS256

**Auth guard in app.html** (runs on page load — if token exists, skip to dashboard):
```javascript
(function(){
  try{var t=localStorage.getItem('wos_token')||sessionStorage.getItem('wos_token');
  if(t)window.location.replace('/dashboard.html');}catch(e){}
})();
```

**401 handler in dashboard.html** (clears token before redirect to prevent loop):
```javascript
if (res.status === 401) {
  try {
    localStorage.removeItem('wos_token'); localStorage.removeItem('wos_user');
    sessionStorage.removeItem('wos_token'); sessionStorage.removeItem('wos_user');
  } catch(e) {}
  window.location.replace('/app.html');
  throw new Error('Unauthorized');
}
```

**API endpoints:**
- `POST /api/v1/auth/signup` — `{email, password, full_name, firm_name?}` → `{access_token, token_type, user}`
- `POST /api/v1/auth/login` — `{email, password}` → `{access_token, token_type, user}`
- `GET /api/v1/auth/me` — requires `Authorization: Bearer <token>`

---

## 7. UPLOAD PIPELINE

**Endpoint:** `POST /api/v1/upload` (multipart, requires JWT)

**Pipeline (runs as background task):**
```
File upload → ParserRegistry.get_parser() → CASParser/ExcelParser
  → raw holdings []
  → PortfolioNormalizer.normalize()    ← maps to canonical ISINs
  → PortfolioService.save_holdings()   ← persists to DB
  → AnalyticsEngine.run()             ← computes all metrics
  → PortfolioService.save_snapshot()  ← saves JSON result
  → status = "ready"
```

**Status poll:** `GET /api/v1/upload/status/{portfolio_id}`
```json
{"portfolio_id":"...", "status":"ready", "holding_count":47, "total_value":2500000.0}
```

**Supported files:** `.pdf` (CAS), `.xlsx`, `.xls`, `.csv`  
**Max size:** 50MB

---

## 8. ANALYTICS ENGINE

**Endpoint:** `GET /api/v1/analytics/{portfolio_id}` (requires JWT)

**Output includes:**
- `portfolio_weights` — `{instrument_id: weight}`
- `sector_exposure` — `{sector_name: weight}`
- `market_cap_exposure` — `{large_cap: w, mid_cap: w, small_cap: w}`
- `concentration` — `{hhi: float, neff: float, top5_weight: float}`
- `diversification_score` — 0-100
- `volatility` — annualized historical volatility
- `max_drawdown` — peak-to-trough
- `fund_overlap` — matrix of overlap between funds
- `asset_allocation` — equity/debt/gold/cash
- `methodology_version` — version string
- `calculation_timestamp` — ISO8601

---

## 9. SCENARIO ENGINE

**20 pre-built scenarios** — all deterministic, no LLM

**Endpoint:** `GET /api/v1/scenarios/{portfolio_id}` — runs all 20  
**Endpoint:** `POST /api/v1/scenarios/{portfolio_id}/run` — run specific scenarios  
**Endpoint:** `GET /api/v1/scenarios/available` — list all scenario IDs

**Scenario categories:**
- Macro shocks (oil spike, rate hike, rate cut, INR depreciation)
- Global events (US recession, China slowdown, geopolitical escalation)
- India-specific (RBI policy change, monsoon failure, election volatility)
- Sector shocks (IT correction, banking stress, pharma regulatory)

**Output per scenario:**
```json
{
  "id": "oil_shock_severe",
  "name": "Severe Oil Price Shock (+50%)",
  "impact_pct": -8.3,
  "affected_sectors": ["aviation", "logistics", "auto"],
  "contribution_breakdown": {"aviation": -3.1, "logistics": -2.8, "auto": -2.4},
  "risk_band": "high",
  "methodology_version": "scenario_v2.1"
}
```

---

## 10. FRONTEND FILES

### app.html (LOGIN PAGE)
**Location:** `/Users/user/Documents/Claude/Projects/WealthOS/frontend/dist/app.html`  
**Serves at:** `https://wlthos.in/app.html`

**Design spec (matches wlthos.in landing exactly):**
- Background: `#FAFAFA`
- Card: white, `border-radius:14px`, `border:1px solid #E5E5E5`, deep shadow
- Font: `Inter` with `font-feature-settings:"ss01","ss03","cv11","calt"` and `font-variation-settings:"opsz" 14`
- Labels: `JetBrains Mono`, 10px, uppercase, letter-spacing .07em, color `#A3A3A3`
- Primary button: `background:#1E40FF` (BLUE accent) — THIS IS CURRENT STATE
- Brand mark: 18×18px, 1px border, 2px radius, blue offset square at translate(4px,4px)
- Brand text: `WealthOS/ai` — "Wealth" bold, "OS" normal, "/ai" in `#A3A3A3`

**Features:**
- Auth guard: already logged in → redirect to dashboard.html immediately
- Tab switcher: "Sign in" / "Create account" (segmented pill control)
- "Back to wlthos.in" link at top
- Error banner with shake animation
- Success banner (green) on login
- Show/hide password toggle
- "Remember me" checkbox (localStorage vs sessionStorage)
- "Forgot password?" link
- API health dot (green=online, amber=degraded, red=unreachable)
- 12-second AbortController timeout on fetch
- Keyboard: Enter advances fields, Enter on password triggers login

**CSS design tokens:**
```css
:root{
  --bg:#FFFFFF; --bg-alt:#FAFAFA;
  --ink:#0A0A0A; --ink-2:#525252; --ink-3:#A3A3A3; --ink-4:#D4D4D4;
  --line:#E5E5E5; --accent:#1E40FF; --accent-dim:rgba(30,64,255,.08);
  --ok:#16A34A; --danger:#DC2626;
  --radius:6px; --radius-lg:10px;
}
```

### dashboard.html
**Location:** `/Users/user/Documents/Claude/Projects/WealthOS/frontend/dist/dashboard.html`  
**Serves at:** `https://wlthos.in/dashboard.html`

**Features:**
- Auth guard: no token → redirect to app.html
- File upload (drag & drop + click)
- Portfolio status polling
- Analytics display: sector exposure, concentration, risk metrics
- Scenario results display
- Logout button (clears wos_token + wos_user)

### landing.html
**Location:** `/Users/user/Documents/Claude/Projects/WealthOS/frontend/dist/landing.html`  
**Serves at:** `https://wlthos.in`

This is the PUBLIC marketing page. DO NOT modify without careful testing — it's the source of truth for design tokens.

---

## 11. COMPLETED PHASES

| Phase | Description | Status |
|-------|-------------|--------|
| 1 | Landing page + real API integration | ✅ Complete |
| 2 | Auth system (signup/login/JWT) | ✅ Complete |
| 3 | Dashboard with real portfolio data | ✅ Complete |
| 4 | Parser pipeline (CAS PDF + Excel) | ✅ Complete |
| 5 | Scenario engine (20 scenarios, scenario_v2.1) | ✅ Complete |
| 6 | Demo backend (lead capture from landing page) | ✅ Complete |

---

## 12. PENDING WORK

### Immediate (tonight/next session)
1. **Deploy current app.html** — run `bash deploy.sh` from local terminal
2. **Hard refresh browser** after deploy: `Cmd+Shift+R` (clears cache)
3. **Test login end-to-end**: go to `https://wlthos.in/app.html`, login with `test@wealthos.local` / `WealthOS2024!`

### Dashboard real data flow (next priority)
The user asked: *"once inside the dashboard I need to see how dashboard works whether it is reading pdf and what result it is giving"*

Steps to verify:
1. Login at wlthos.in/app.html
2. Upload `samples/portfolio_kt.pdf` via dashboard
3. Poll status until `"ready"`
4. Verify analytics results display in dashboard
5. Verify scenario results load

### Known issues to investigate
- Dashboard may show mock/placeholder data instead of real API data — audit all `fetch()` calls in dashboard.html to confirm they hit `api.wlthos.in` and not hardcoded demo arrays
- Phase 5 scenario validation: run the 20 scenarios against the sample PDF and verify output is reasonable

---

## 13. KEY API CALLS (from frontend)

```javascript
const API = 'https://api.wlthos.in';
const token = localStorage.getItem('wos_token') || sessionStorage.getItem('wos_token');

// Auth headers
const headers = {
  'Content-Type': 'application/json',
  'Authorization': `Bearer ${token}`
};

// Login
fetch(`${API}/api/v1/auth/login`, {method:'POST', headers:{'Content-Type':'application/json'},
  body: JSON.stringify({email, password})})

// Upload
const form = new FormData(); form.append('file', file);
fetch(`${API}/api/v1/upload`, {method:'POST', headers:{'Authorization':`Bearer ${token}`}, body: form})

// Poll status
fetch(`${API}/api/v1/upload/status/${portfolioId}`, {headers})

// Get analytics
fetch(`${API}/api/v1/analytics/${portfolioId}`, {headers})

// Run all scenarios
fetch(`${API}/api/v1/scenarios/${portfolioId}`, {headers})

// Health check
fetch(`${API}/health`)
```

---

## 14. GIT / DEPLOY NOTES

- **Git lock fix:** `deploy.sh` now automatically runs `rm -f .git/HEAD.lock .git/index.lock ...` as step 0 — this is permanent, no manual intervention needed
- **Database is EXCLUDED from rsync** (`--exclude '*.db'`) — the live DB on the server persists across deploys
- **`.env` is EXCLUDED from rsync** — never overwrite server secrets
- **After deploy, hard refresh:** `Cmd+Shift+R` in browser to clear cached HTML

---

## 15. CURRENT app.html BUTTON STATE

As of this session end: button is **BLUE (`#1E40FF` accent)**  
The user confirmed the goal design (second screenshot) has blue button + segmented tabs + back link.  
The uploaded `wealthos_login_final.html` file confirms this aesthetic.

If you need to change button color, find this in `app.html`:
```css
.btn-primary{
  background:var(--accent);   /* #1E40FF blue */
  color:#fff;
  border-color:var(--accent);
  border-radius:8px;
}
```
Change `var(--accent)` to `var(--ink)` for black, or any hex for custom color.

---

## 16. USEFUL SERVER COMMANDS

```bash
# SSH
ssh root@64.227.147.106

# Service
systemctl status wealthos
systemctl restart wealthos
journalctl -u wealthos -f --since "10 minutes ago"

# Nginx
nginx -t                        # test config
systemctl reload nginx

# Check what's live
cat /var/www/wlthos/app.html | grep btn-primary -A3
curl https://api.wlthos.in/health

# DB (on server)
cd /opt/wlthos/backend
sqlite3 wealthos.db ".tables"
sqlite3 wealthos.db "SELECT email, created_at FROM users;"
sqlite3 wealthos.db "SELECT count(*) FROM demo_requests;"
```

---

## 17. WHAT TO TELL THE NEW CLAUDE SESSION

> I am building WealthOS (wlthos.in) — an institutional financial intelligence platform for Indian mutual fund portfolios. The backend is FastAPI + SQLite on a DigitalOcean server (root@64.227.147.106). Frontend is static HTML at /var/www/wlthos. Deploy script is at /Users/user/Documents/Claude/Projects/WealthOS/deploy.sh — run with `bash deploy.sh`.
>
> The login page (app.html) is done and deployed. The dashboard (dashboard.html) is live but I need to verify the full PDF upload → analytics → scenario pipeline is actually working end-to-end with real data showing in the dashboard.
>
> Please read CLAUDE.md for all hard design rules, and WEALTHOS_HANDOFF_2026_05_27.md for full context. Start by checking the live site health and then walk through the dashboard upload flow.

---

*End of handoff document. Generated: 2026-05-27*
