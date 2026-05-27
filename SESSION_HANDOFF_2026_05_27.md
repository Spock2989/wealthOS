# WealthOS — Session Handoff
**Date:** 2026-05-27
**Status:** Full flow working — marketing site → login → dashboard ✅

---

## ✅ CURRENT STATE (ALL WORKING)

### Live URLs
| URL | What it serves |
|---|---|
| `https://wlthos.in` | Marketing site (index.html) |
| `https://wlthos.in/app.html` | Login page |
| `https://wlthos.in/dashboard.html` | Advisor dashboard |

### Flow
`wlthos.in` → click **Log In** (top nav) → `/app.html` → click **Sign In to Dashboard** → `/dashboard.html` ✅

---

## 🔑 INFRA & CREDENTIALS

| Item | Value |
|---|---|
| Admin email | tiwarikshitij20@gmail.com |
| Admin password | WealthOS2026! |
| Server | root@64.227.147.106 |
| Backend service | `systemd: wealthos` on port 8000 |
| Nginx serves frontend from | `/opt/wlthos/frontend/dist/` |
| API | `https://api.wlthos.in` |

---

## 📋 CANONICAL DEPLOY SEQUENCE (verified working)

```bash
# Frontend deploy from Mac terminal:
rsync -avz /Users/user/Documents/Claude/Projects/WealthOS/frontend/dist/ root@64.227.147.106:/opt/wlthos/frontend/dist/ && ssh root@64.227.147.106 "chmod 644 /opt/wlthos/frontend/dist/*.html && chmod 755 /opt/wlthos/frontend/dist/ && echo DONE"

# Backend deploy:
rsync -avz /Users/user/Documents/Claude/Projects/WealthOS/backend/ root@64.227.147.106:/opt/wlthos/backend/ --exclude='__pycache__' --exclude='venv' --exclude='.env' --exclude='*.pyc' && ssh root@64.227.147.106 "systemctl restart wealthos && echo BACKEND DONE"
```

**CRITICAL:** Always run `chmod 644 *.html` after every rsync — rsync creates files with restrictive permissions that cause 403s.

---

## 📁 FRONTEND FILES (canonical)

| File | Purpose | Notes |
|---|---|---|
| `frontend/dist/index.html` | Marketing site | ~2800 lines, restored from wealthos-final-updated.html |
| `frontend/dist/landing.html` | Marketing site alias | Same as index.html |
| `frontend/dist/app.html` | Login page | "Sign In to Dashboard" is a plain `<a href="/dashboard.html">` — NOT a JS button |
| `frontend/dist/dashboard.html` | Advisor dashboard | wealthos-dashboard.html design |

### ⚠️ Critical: Login button in app.html
The "Sign In to Dashboard" button is an `<a>` tag, NOT a `<button onclick>`. This was the fix for the "nothing happens" bug. Do NOT change it back to a button with onclick.

```html
<a href="/dashboard.html" class="btn btn-primary" style="width:100%;height:42px;font-size:14px;display:flex;align-items:center;justify-content:center;text-decoration:none;cursor:pointer">Sign In to Dashboard</a>
```

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

1. **Wire real auth** — make login call `POST /v1/auth/login`, store JWT, redirect to dashboard with token
2. **Wire CAS upload** → parse → analytics → show real client data
3. **Replace demo seed data** with real API responses
4. **PostgreSQL migration**

---

## 🏗️ BACKEND ENGINES (v4.0 — all deployed)

- `engines/proprietary_metrics_engine.py` — Health Score, Fragility Score, ENB (Meucci), DR (Choueifady), multi-level HHI
- `engines/scenario_engine.py` — 20 scenarios, 11-variable macro sensitivity matrix
- `engines/performance_engine.py` — BHB attribution, Pain Ratio
- `engines/risk_engine.py` — EVT/GPD VaR, 99% VaR, 10-day VaR
- `analytics_core.py` — v4.0 orchestrator, 12 tiers, full audit trail
- `infra/nginx/wealthos-api-cors-fix.conf` — CORS fix for browser login

---

## 🎨 DESIGN SYSTEM

| Token | Value |
|---|---|
| Accent | `#1E40FF` |
| Fonts | Inter + JetBrains Mono |
| Radii | 6px / 10px |
| OK | `#16A34A` |
| Warn | `#B45309` |
| Danger | `#DC2626` |
| Dark mode | CSS custom properties via `data-theme="dark"` |

Logo: two overlapping 17×17 squares in a 28×28 container — outlined square (z-index:1, top-left), blue `#1E40FF` filled square (z-index:2, bottom-right). "OS" in accent blue everywhere.
