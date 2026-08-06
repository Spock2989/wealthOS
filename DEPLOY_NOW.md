# WealthOS — Deploy This Session's Changes
**Date:** 2026-05-27  
**What changed this session:**
1. Fixed nginx CORS config (was using broken `$cors_origin` variable pattern)
2. Wired dashboard portfolio list, upload flow, and detail view to live API
3. Added `POST /api/v1/scenarios/{id}/run` and `GET /api/v1/scenarios/{id}` routes
4. Added `GET /api/v1/lookthrough/{id}` route
5. Registered all new routes in `main.py`

---

## STEP 1 — Push to GitHub (Mac terminal)

```bash
cd /Users/user/Documents/Claude/Projects/WealthOS
git add -A
git commit -m "Fix nginx CORS, wire dashboard to API, add scenario + lookthrough routes"
git push origin main
```

---

## STEP 2 — Deploy backend (Mac terminal)

```bash
rsync -avz /Users/user/Documents/Claude/Projects/WealthOS/backend/ \
  root@64.227.147.106:/opt/wlthos/backend/ \
  --exclude='__pycache__' --exclude='venv' --exclude='.env' \
  --exclude='*.pyc' --exclude='wealthos.db' --exclude='wealthos.db*'
```

---

## STEP 3 — Deploy frontend (Mac terminal)

```bash
rsync -avz /Users/user/Documents/Claude/Projects/WealthOS/frontend/dist/ \
  root@64.227.147.106:/opt/wlthos/frontend/dist/ && \
ssh root@64.227.147.106 "chmod 644 /opt/wlthos/frontend/dist/*.html && echo FRONTEND DONE"
```

---

## STEP 4 — Fix nginx CORS on server (SSH)

This is the **critical fix** for the browser login failure.
The old config used `$cors_origin` variable which is unreliable in nginx.
The new config hardcodes `https://wlthos.in`.

```bash
ssh root@64.227.147.106

cp /opt/wlthos/infra/nginx/wealthos-api.conf \
   /etc/nginx/sites-available/wealthos-api

nginx -t && systemctl reload nginx
```

**Verify CORS is working:**
```bash
curl -sI -X OPTIONS https://api.wlthos.in/api/v1/auth/login \
  -H "Origin: https://wlthos.in" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: Content-Type" \
  | grep -i "access-control"
```

Expected output (must see all 4 headers):
```
access-control-allow-origin: https://wlthos.in
access-control-allow-methods: GET, POST, PUT, PATCH, DELETE, OPTIONS
access-control-allow-headers: Authorization, Content-Type, Accept, X-Requested-With
access-control-allow-credentials: true
```

---

## STEP 5 — Restart backend + verify (SSH)

```bash
ssh root@64.227.147.106
systemctl restart wealthos
sleep 3
systemctl status wealthos   # must show: active (running)
curl http://127.0.0.1:8000/health
# Expected: {"status":"ok","service":"wealthos-api","version":"2.0.0","db":"..."}
```

---

## STEP 6 — End-to-end test

**Test login (from Mac, not server):**
```bash
curl -s -X POST https://api.wlthos.in/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -H "Origin: https://wlthos.in" \
  -d '{"email":"tiwarikshitij20@gmail.com","password":"WealthOS2026!"}' \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('OK' if 'access_token' in d else 'FAIL', d.get('access_token','')[:30])"
```

**Test new routes (replace TOKEN with actual token):**
```bash
# Get token first
TOKEN=$(curl -s -X POST https://api.wlthos.in/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"tiwarikshitij20@gmail.com","password":"WealthOS2026!"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# List available scenarios
curl -s https://api.wlthos.in/api/v1/scenarios/available \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool | head -20

# List portfolios
curl -s https://api.wlthos.in/api/v1/portfolios/ \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

**Browser test:**
1. Open `https://wlthos.in/app.html`
2. Enter `tiwarikshitij20@gmail.com` / `WealthOS2026!`
3. Click **Sign In to Dashboard** — should redirect to `/dashboard.html`
4. Click **Portfolios** nav — table should show "No portfolios yet. Upload a CAS file."
5. Click **+ Upload CAS / Excel** — upload a test PDF

---

## WHAT'S NOW LIVE (after this deploy)

### API routes (10 total)
| Route | Description |
|-------|-------------|
| `POST /api/v1/auth/login` | JWT login |
| `GET  /api/v1/auth/me` | Current user |
| `POST /api/v1/upload/` | CAS PDF / Excel upload + async pipeline |
| `GET  /api/v1/portfolios/` | List portfolios (live data) |
| `GET  /api/v1/portfolios/{id}` | Portfolio detail |
| `GET  /api/v1/portfolios/{id}/holdings` | Holdings list |
| `GET  /api/v1/analytics/{id}` | Latest analytics snapshot |
| `POST /api/v1/analytics/{id}/rerun` | Recompute analytics |
| `GET  /api/v1/scenarios/available` | List 20 scenarios + 11 macro events |
| `GET  /api/v1/scenarios/{id}` | Run all scenarios for portfolio |
| `POST /api/v1/scenarios/{id}/run` | Run specific/custom scenario |
| `GET  /api/v1/lookthrough/{id}` | Sector, cap, overlap, concentration |
| `POST /api/v1/insights/{id}/generate` | AI narrative |
| `GET  /api/v1/reports/{id}/summary` | Portfolio summary report |

### Frontend
- Login → real JWT auth, token stored in localStorage/sessionStorage
- Dashboard → loads real portfolios from API on page load
- Upload → CAS PDF / Excel → polls status → refreshes list
- Portfolio detail → loads real analytics from API
- Auth guard on dashboard — no token = redirect to login

---

## WHAT'S NEXT

### Priority 1 — Test CAS upload end-to-end
Upload a real CAMS/KFin PDF and verify:
- Parse succeeds → holdings in DB
- Analytics runs → snapshot created
- Lookthrough endpoint returns real sector/cap data
- Scenario endpoint returns portfolio-specific results

### Priority 2 — Wire scenario cards in dashboard
The dashboard client detail view has scenario cards but they're still hardcoded.
Add `loadScenarios(portfolioId)` call in `openPortfolio()` to populate from the API.

### Priority 3 — Wire lookthrough tab in dashboard
The Exposures tab in the client detail view is hardcoded.
Add `loadLookthrough(portfolioId)` call to populate sector/cap bars from the API.

### Priority 4 — PostgreSQL migration
Current state: service connects to PostgreSQL (`.env` or systemd env has PG URL).
The SQLite seed was run but the service uses PG.
- Confirm what DATABASE_URL the service actually uses: `systemctl cat wealthos | grep DATABASE`
- If PG: run the admin seed against PG using the psycopg2 URL
- If SQLite: all is fine

### Priority 5 — AMFI integration for full look-through
The lookthrough route currently computes from reported holdings only.
Full fund → stock decomposition requires fetching AMFI portfolio disclosure data.
This is a Phase 2 feature — the current output is correctly labelled `methodology_version: "lookthrough_v1.0_direct"`.

---

## FILE MAP (what changed this session)

| File | Change |
|------|--------|
| `infra/nginx/wealthos-api.conf` | Hardcoded CORS, added HTTP→HTTPS redirect, ssl http2, proxy_http_version |
| `infra/nginx/wealthos-api-cors-fix.conf` | DEPRECATED — replaced by wealthos-api.conf |
| `frontend/dist/dashboard.html` | Portfolios view wired to API; upload flow; `openPortfolio()` replaces `openClient()`; `loadPortfolios()` on page load |
| `backend/app/api/v1/scenarios.py` | NEW — scenario route, all 20 scenarios + custom + macro matrix |
| `backend/app/api/v1/lookthrough.py` | NEW — lookthrough route, sector/cap/overlap/concentration |
| `backend/main.py` | Added scenarios + lookthrough routers |
| `scripts/fix_nginx_cors.sh` | One-shot nginx fix script |

---

## CREDENTIALS

| Item | Value |
|------|-------|
| Admin email | tiwarikshitij20@gmail.com |
| Admin password | WealthOS2026! |
| Server | root@64.227.147.106 |
| Frontend | https://wlthos.in |
| API | https://api.wlthos.in |
| API docs | https://api.wlthos.in/docs |

---

## IF BROWSER LOGIN STILL FAILS AFTER NGINX FIX

Open browser DevTools → Console, then try login. Look for:

**CORS error** (e.g. "has been blocked by CORS policy"):
→ nginx still not sending headers. Check `nginx -t` output on server, check which config is symlinked: `ls -la /etc/nginx/sites-enabled/`

**401 Unauthorized**:
→ Admin user may not exist in the DB the service is using. Check: `systemctl cat wealthos | grep DATABASE` to see which DB URL is active. If PostgreSQL, the sqlite-seeded admin doesn't apply. Run the seed against the correct DB.

**Network Error (fetch failed)**:
→ API is down. Check `systemctl status wealthos` on server.

**"Invalid email or password"**:
→ User exists but password hash mismatch. The seed uses HMAC-SHA256 with pepper `"wealthos-pepper"`. If PW_PEPPER env var is different on server, hashes won't match. Check `systemctl cat wealthos | grep PW_PEPPER`.
