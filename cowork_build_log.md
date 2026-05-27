# WealthOS MVP Build Log
**Session started:** 2026-05-27
**Engineer:** Claude (lead)

---

## PHASE 0 — AUDIT FINDINGS

### Backend Architecture
- **Live server uses:** `backend/main.py` → imports from `backend/app/` (new stack)
- **API prefix:** `/api/v1/` (NOT `/v1/` — frontend must use this)
- **Auth:** HMAC-sha256 + pepper (not bcrypt) — in `app/api/v1/auth.py`
- **Endpoints wired:** auth, upload, portfolios, analytics, insights, reports, scenarios, lookthrough

### Backend — BROKEN / MISSING
- ❌ `demo-requests` router (`backend/routers/demo.py`) imports OLD stack, NOT wired into `main.py`
- ❌ No `app/api/v1/demo.py` in new stack
- ⚠️ `backend/engines/scenario_engine.py` imported from scenarios route via `sys.path` hack — fragile

### Frontend index.html (Landing Page)
- ✅ "Book Demo" button → `openDemoModal()` — modal opens
- ✅ "Log In" → `/app.html` anchor link — works
- ✅ "Book Institutional Demo" → `#contact` anchor — works
- ✅ Demo modal form — UI complete
- ❌ `wosSubmit()` — DEAD: saves to localStorage only, API call COMMENTED OUT (setTimeout fake)
- ⚠️ Nav links "Docs" and "Pricing" → `href="#"` — dead anchors (no page)
- ⚠️ "Run a Sample Portfolio" button — currently opens demo modal (acceptable)

### Frontend app.html (Login page)
- ✅ Login calls `API_BASE + '/api/v1/auth/login'` — REAL
- ✅ On success: stores JWT, redirects to `/dashboard.html`
- ✅ Logout clears storage
- ❌ NO registration form — spec requires "Create Account" link
- ❌ "Forgot password?" → `alert()` — must be inline message
- ⚠️ `appShell` div has fake dashboard (dead code — never reached since login redirects to dashboard.html)

### Frontend dashboard.html (Dashboard)
- ✅ Auth guard — redirects to /app.html if no token
- ✅ `_apiFetch()` — Bearer token on every call
- ✅ `loadPortfolios()` — calls `/api/v1/portfolios/` (real)
- ✅ `openPortfolio()` — calls `/api/v1/portfolios/{id}` + `/api/v1/analytics/{id}` (real)
- ✅ File upload — real multipart POST to `/api/v1/upload/`
- ✅ Empty state handling present
- ❌ Sidebar badge counts hardcoded (3, 7, 48) — must be removed or dynamic
- ❌ Scenario tab in client view — NOT wired to API
- ❌ Several `alert()` calls remain (Settings sync, API key copy, etc.)
- ❌ "Export PDF" button — not real (exportPDF function undefined or stub)
- ❌ Intelligence/Alerts views have hardcoded fake content

### samples/ directory
- ❌ DOES NOT EXIST — Phase 4 parser testing blocked
- This is a STOP condition for Phase 4 per spec

### Git Status
- Repo exists, commits present. Latest: "handoff: session 2026-05-27 complete"

---

## PHASE 0 — ACTIONS

### 0a. Local run test
- [ ] pip install deps, start uvicorn, curl /health

### 0b. Git baseline commit
- [ ] `git commit -am "baseline before MVP build 2026-05-27"`

### 0c. Server backup
- [ ] SSH backup of dist + db

### 0d. Rollback command
```bash
ssh root@64.227.147.106 "cp -r /opt/wlthos/frontend/dist.bak.TIMESTAMP /opt/wlthos/frontend/dist && cp /opt/wlthos/backend/wealthos.db.bak.TIMESTAMP /opt/wlthos/backend/wealthos.db && systemctl restart wealthos && echo ROLLBACK OK"
```

---

## BUILD PLAN

### Phase 1 — Landing page fixes
- Wire `wosSubmit()` to POST `/api/v1/demo-requests`
- Fix "Docs"/"Pricing" dead nav links (make them scroll to sections or remove)

### Phase 2 — Auth
- Add registration form to app.html
- Fix "Forgot password" alert → inline message

### Phase 3 — Dashboard real data
- Remove hardcoded badge counts (3, 7, 48)
- Remove/fix remaining alert() calls
- Remove "Export PDF" button (not real this session)
- Remove/fix fake Intelligence/Alerts hardcoded content
- Wire scenario tab to real API

### Phase 4 — Parser pipeline
- BLOCKED: No samples/ directory
- Will note STOP when reached

### Phase 5 — Scenario engine
- Verify scenario endpoint works
- Wire dashboard scenario tab to API

### Phase 6 — Demo backend
- Create `backend/app/api/v1/demo.py`
- Wire into `backend/main.py`

### Phase 7 — Deploy + smoke test

---

## BUILD LOG

