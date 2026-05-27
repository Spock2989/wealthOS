# WealthOS — Session Handoff
**Date:** 2026-05-27
**GitHub:** https://github.com/Spock2989/wealthOS.git (commit f30f06d)
**Status:** Full flow working — marketing site → login → dashboard ✅

---

## ✅ CURRENT STATE (ALL WORKING)

### Live URLs
| URL | What it serves |
|---|---|
| `https://wlthos.in` | Marketing site (index.html) |
| `https://wlthos.in/app.html` | Login page |
| `https://wlthos.in/dashboard.html` | Advisor dashboard |

### User Flow (end to end)
`wlthos.in` → click **Log In** (top nav) → `/app.html` → click **Sign In to Dashboard** → `/dashboard.html` ✅

---

## 🔑 INFRA & CREDENTIALS

| Item | Value |
|---|---|
| Admin email | tiwarikshitij20@gmail.com |
| Admin password | WealthOS2026! |
| Server | root@64.227.147.106 |
| Backend service | `systemd: wealthos` on port 8000 |
| Nginx serves frontend from | `/opt/wlthos/frontend/dist/` ← CRITICAL, not /var/www/ |
| API | `https://api.wlthos.in` |
| GitHub | https://github.com/Spock2989/wealthOS.git |

---

## 📋 CANONICAL DEPLOY SEQUENCE (verified working)

```bash
# Frontend deploy from Mac terminal:
rsync -avz /Users/user/Documents/Claude/Projects/WealthOS/frontend/dist/ root@64.227.147.106:/opt/wlthos/frontend/dist/ && ssh root@64.227.147.106 "chmod 644 /opt/wlthos/frontend/dist/*.html && chmod 755 /opt/wlthos/frontend/dist/ && echo DONE"

# Backend deploy:
rsync -avz /Users/user/Documents/Claude/Projects/WealthOS/backend/ root@64.227.147.106:/opt/wlthos/backend/ --exclude='__pycache__' --exclude='venv' --exclude='.env' --exclude='*.pyc' && ssh root@64.227.147.106 "systemctl restart wealthos && echo BACKEND DONE"

# GitHub push:
cd /Users/user/Documents/Claude/Projects/WealthOS && git add -A && git commit -m "your message" && git push origin main
```

**CRITICAL after every rsync:** Always run `chmod 644 *.html && chmod 755 dist/` — rsync creates files with restrictive permissions that cause 403 Forbidden errors.

**If git add fails with index.lock error:**
```bash
rm /Users/user/Documents/Claude/Projects/WealthOS/.git/index.lock
```

---

## 📁 FRONTEND FILES (canonical, do not change structure)

| File | Purpose | Notes |
|---|---|---|
| `frontend/dist/index.html` | Marketing site | ~2800 lines, restored from wealthos-final-updated.html |
| `frontend/dist/landing.html` | Marketing site alias | Same content as index.html |
| `frontend/dist/app.html` | Login page | Sign In button is `<a href="/dashboard.html">` — NOT a JS button |
| `frontend/dist/dashboard.html` | Advisor dashboard | wealthos-dashboard.html design |

### ⚠️ CRITICAL — Login button in app.html
The "Sign In to Dashboard" button is a plain `<a>` tag, NOT `<button onclick="doLogin()">`.
This was the fix for the persistent "nothing happens on click" bug. Do NOT revert to a JS button.

```html
<a href="/dashboard.html" class="btn btn-primary" style="width:100%;height:42px;font-size:14px;display:flex;align-items:center;justify-content:center;text-decoration:none;cursor:pointer">Sign In to Dashboard</a>
```

### ⚠️ CRITICAL — Do NOT replace index.html with app_3 design
The marketing site lives at `index.html`. The app_3 design (login+dashboard) lives at `app.html` and `dashboard.html`. Keep them separate.

---

## ❌ WHAT'S STILL FAKE / PENDING

1. **No real auth** — login accepts any credentials (demo mode), no JWT validation on frontend
2. **Dashboard data is demo** — Rajesh Mehta, Priya Patel etc. are hardcoded seed clients
3. **CAS Upload** — Upload zone exists in UI but backend parse → analytics pipeline not wired end-to-end
4. **Portfolios view** — Reads from real API `/v1/portfolios` but no real portfolios exist yet
5. **Scenarios** — Scenario cards are static; not wired to `scenario_engine.py`
6. **PostgreSQL migration** — Still on SQLite on server

---

## 🔜 NEXT LOGICAL BUILD ORDER

1. **Wire real auth** — make login POST to `api.wlthos.in/v1/auth/login`, store JWT in localStorage, redirect to dashboard with token
2. **Wire CAS upload** → parse → analytics → show real client data
3. **Replace demo seed data** with real API responses from backend
4. **PostgreSQL migration** from SQLite

---

## 🏗️ BACKEND ENGINES (v4.0 — all deployed on server)

| Engine | What it does |
|---|---|
| `analytics_core.py` | v4.0 orchestrator, 12 computation tiers, full audit trail |
| `proprietary_metrics_engine.py` | Health Score, Fragility Score, ENB (Meucci 2009), DR (Choueifady 2008), multi-level HHI |
| `scenario_engine.py` | 20 scenarios, 11-variable macro sensitivity matrix (India-calibrated) |
| `risk_engine.py` | EVT/GPD VaR, 99% VaR, 10-day VaR (FRTB), full VaR ladder |
| `risk_models_engine.py` | Ledoit-Wolf, OAS, MCD covariance |
| `performance_engine.py` | BHB attribution (1986), Pain Ratio |
| `statistical_engine.py` | Descriptive stats, correlation, regression |
| `volatility_models_engine.py` | GARCH(1,1), GJR-GARCH, EGARCH |
| `regime_detection_engine.py` | HMM 2/3 state regime detection |
| `factor_engine.py` | Factor loading and exposure |
| `optimization_engine.py` | Black-Litterman, HRP |
| `backtesting_engine.py` | Walk-forward, PSR, DSR, MinBTL |
| `fixed_income_engine.py` | Duration, DV01, KRD |
| `cas_parser.py` | CAS PDF parsing |
| `lookthrough_engine.py` | Fund → stock → sector → macro decomposition |
| `normalization.py` | ISIN resolution, alias mapping |

---

## 🎨 DESIGN SYSTEM

| Token | Value |
|---|---|
| Accent | `#1E40FF` |
| Fonts | Inter + JetBrains Mono |
| Border radius | 6px / 10px |
| Status OK | `#16A34A` |
| Status Warn | `#B45309` |
| Status Danger | `#DC2626` |
| Dark mode | CSS custom properties via `data-theme="dark"` |

**Logo:** two overlapping 17×17 squares in a 28×28 container — outlined square (z-index:1, top-left), blue `#1E40FF` filled square (z-index:2, bottom-right). "OS" text is always `#1E40FF` (accent blue).

---

## 📂 PROJECT STRUCTURE (key paths)

```
WealthOS/
├── frontend/dist/          ← deployed to server, served by Nginx
│   ├── index.html          ← marketing site
│   ├── landing.html        ← marketing site (alias)
│   ├── app.html            ← login page
│   └── dashboard.html      ← advisor dashboard
├── backend/
│   ├── main.py             ← FastAPI entry point
│   ├── engines/            ← all 16 quant engines
│   ├── app/api/v1/         ← REST endpoints
│   ├── app/models/         ← SQLAlchemy models
│   └── wealthos.db         ← SQLite (to be migrated to PostgreSQL)
├── infra/nginx/            ← Nginx configs
└── SESSION_HANDOFF_*.md    ← this file
```
