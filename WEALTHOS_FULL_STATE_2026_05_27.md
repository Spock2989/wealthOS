# WealthOS — Complete System State & Fix Instructions
**Date:** 2026-05-27  
**Purpose:** Full handoff document. Read this entire file before touching anything.

---

## 0. WHAT THIS SYSTEM IS

WealthOS is a **financial intelligence infrastructure system** for Indian mutual fund and equity portfolios. It is NOT a chatbot or dashboard tool. It is a deterministic analytics engine with a professional advisor-facing frontend.

**Live domain:** `https://wlthos.in`  
**API:** `https://api.wlthos.in`  
**Server:** `root@64.227.147.106` (DigitalOcean Ubuntu 24.04)  
**GitHub:** `https://github.com/Spock2989/wealthOS.git`

---

## 1. CREDENTIALS

| Item | Value |
|------|-------|
| Admin email | tiwarikshitij20@gmail.com |
| Admin password | WealthOS2026! |
| Server SSH | `ssh root@64.227.147.106` |
| Backend service name | **`wealthos`** — NOT `wealthos-api` (corrected 2026-08-06, see §2) |
| Backend port | 8000 (127.0.0.1 only, nginx proxies) |
| DB | PostgreSQL (running) + SQLite fallback |
| Nginx frontend | `/opt/wlthos/frontend/dist/` |
| Nginx API proxy | `/etc/nginx/sites-enabled/wealthos-api` |
| systemd service | `/etc/systemd/system/wealthos-api.service` |
| Backend code | `/opt/wlthos/backend/` |
| Backend venv | `/opt/wlthos/backend/venv/` |

---

## 2. SERVER ARCHITECTURE

```
Browser → Nginx (wlthos.in:443) → /opt/wlthos/frontend/dist/  (static files)
Browser → Nginx (api.wlthos.in:443) → 127.0.0.1:8000 (FastAPI)
FastAPI → PostgreSQL (running, tables exist) or SQLite fallback
```

> ## 🚨 CRITICAL — CORRECTED 2026-08-06
>
> **The live service is `wealthos`. It is NOT `wealthos-api`.**
>
> This document previously stated the opposite, and that single line cost
> **ten weeks of deploys that silently did nothing.**
>
> Two systemd units exist, both titled "WealthOS API", both with an identical
> `ExecStart` on port 8000:
>
> | Unit | Created | Reality |
> |---|---|---|
> | `wealthos.service` | 2026-05-27 20:17 | **Holds port 8000. This serves all traffic.** |
> | `wealthos-api.service` | 2026-05-27 07:30 | Duplicate. Cannot bind — port already taken. Crash-loops on `Address already in use`, then systemd gives up. |
>
> `wealthos-api` was correct when this doc was written that morning. Someone
> created `wealthos.service` at 20:17 the same evening; it took the port, and
> the doc was never updated. Every `systemctl restart wealthos-api` since has
> been a **no-op against a dead unit** — the real process kept running stale
> code and stale environment variables.
>
> This is why the AI Memo held a placeholder `ANTHROPIC_API_KEY` for weeks
> after it was "fixed", and why code deployed since May appeared never to go
> live.
>
> **Always use:**
> ```bash
> systemctl restart wealthos
> systemctl status wealthos
> journalctl -u wealthos -n 50
> ```
>
> `wealthos-api.service` was disabled on 2026-08-06. If you ever see it come
> back, something re-enabled it — remove it rather than restarting it.
>
> Note the **nginx** config file genuinely is named `wealthos-api`
> (`/etc/nginx/sites-available/wealthos-api`) — that name is correct and
> unrelated to the systemd unit. The live vhost is
> `/etc/nginx/sites-enabled/wlthos`.

---

## 3. WHAT IS CONFIRMED WORKING (AS OF 2026-05-27)

✅ Server is live and reachable  
✅ FastAPI service running: `http://127.0.0.1:8000/health` returns `{"status":"ok","version":"2.0.0"}`  
✅ New backend stack (`backend/app/`) is running (NOT the old `backend/routers/`)  
✅ Login API works from server: `curl -X POST http://127.0.0.1:8000/api/v1/auth/login` returns valid JWT  
✅ Admin user exists in DB: `tiwarikshitij20@gmail.com` / `WealthOS2026!`  
✅ Nginx CORS config is the good version (`wealthos-api-cors-fix.conf`) at `/etc/nginx/sites-enabled/wealthos-api`  
✅ Frontend files deployed: `app.html` has real JS auth (not fake `<a href>`)  
✅ Dashboard has auth guard (redirects to `/app.html` if no token)  

---

## 4. WHAT IS BROKEN — THE LOGIN FLOW

### The exact problem
The login form at `https://wlthos.in/app.html` submits credentials to `https://api.wlthos.in/api/v1/auth/login`. The API works perfectly when called directly from the server. But **the browser cannot complete the login**.

### Confirmed facts
1. `curl http://127.0.0.1:8000/api/v1/auth/login` → ✅ returns JWT (API is fine)
2. No `PW_PEPPER` in `.env` → default `"wealthos-pepper"` used → consistent between seed and service
3. No `DATABASE_URL` in `.env` → systemd Environment= takes effect
4. Nginx CORS config is deployed and running

### Most likely causes (in priority order)

**CAUSE A — CORS preflight failing silently**  
The nginx config uses `set $cors_origin $http_origin` inside `if` blocks. There is a known nginx bug where `if` + `set` + `add_header` interactions can produce empty headers under certain conditions. If `Access-Control-Allow-Origin` comes back empty, browsers silently fail and JavaScript catches it as a network error.

**CAUSE B — Browser showing no error message**  
The `doLogin()` function should show an inline error. If the user sees no error at all (nothing changes after clicking), there may be a JavaScript syntax error in `app.html` preventing the click handler from registering.

**CAUSE C — DATABASE_URL mismatch**  
The `sed` command that changed the systemd service file from PostgreSQL to SQLite may not have applied correctly. The service may be connecting to PostgreSQL. The admin user was seeded BOTH into SQLite (via reset_and_seed.py) AND into PostgreSQL (via the Python one-liner that showed "User updated"). So credentials should work either way — but verify.

---

## 5. THE FIX — EXACT STEPS IN ORDER

### Step 1: Verify what the browser actually sees
From your **Mac terminal** (not the server), run this to test CORS from outside:

```bash
# Test 1: Does the CORS preflight respond correctly?
curl -v -X OPTIONS https://api.wlthos.in/api/v1/auth/login \
  -H "Origin: https://wlthos.in" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: content-type" 2>&1 | grep -i "access-control\|< HTTP"

# Test 2: Does the actual login work through nginx (not bypassing it)?
curl -s -X POST https://api.wlthos.in/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -H "Origin: https://wlthos.in" \
  -d '{"email":"tiwarikshitij20@gmail.com","password":"WealthOS2026!"}'
```

**If Test 1 shows no `Access-Control-Allow-Origin` header → CORS is the bug → go to Fix A**  
**If Test 1 shows the header but Test 2 fails → auth bug → go to Fix B**  
**If both work → JavaScript bug → go to Fix C**

---

### Fix A: Replace nginx CORS config with bulletproof version

SSH into server:
```bash
ssh root@64.227.147.106
```

Replace the nginx config with a version that hardcodes the CORS origin (no variable tricks):
```bash
cat > /etc/nginx/sites-available/wealthos-api << 'NGINXEOF'
server {
    listen 80;
    server_name api.wlthos.in;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name api.wlthos.in;

    ssl_certificate     /etc/letsencrypt/live/api.wlthos.in/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.wlthos.in/privkey.pem;
    ssl_protocols       TLSv1.2 TLSv1.3;

    location / {
        # Handle CORS preflight
        if ($request_method = OPTIONS) {
            add_header 'Access-Control-Allow-Origin' 'https://wlthos.in' always;
            add_header 'Access-Control-Allow-Methods' 'GET, POST, PUT, DELETE, OPTIONS' always;
            add_header 'Access-Control-Allow-Headers' 'Authorization, Content-Type, Accept' always;
            add_header 'Access-Control-Allow-Credentials' 'true' always;
            add_header 'Access-Control-Max-Age' 86400 always;
            add_header 'Content-Length' 0;
            return 204;
        }

        # CORS headers on all responses
        add_header 'Access-Control-Allow-Origin' 'https://wlthos.in' always;
        add_header 'Access-Control-Allow-Credentials' 'true' always;

        proxy_pass         http://127.0.0.1:8000;
        proxy_set_header   Host              $host;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
    }
}
NGINXEOF

ln -sf /etc/nginx/sites-available/wealthos-api /etc/nginx/sites-enabled/wealthos-api
nginx -t && systemctl reload nginx
echo "Nginx reloaded"
```

Then re-run Test 1 and Test 2 from your Mac.

---

### Fix B: Re-seed admin user (if auth is failing through nginx)

SSH into server and run:
```bash
ssh root@64.227.147.106
cd /opt/wlthos/backend && source venv/bin/activate

python3 - << 'EOF'
import os, sys, uuid, hashlib, hmac
from datetime import datetime
sys.path.insert(0, '/opt/wlthos/backend')
from app.models.user import User
from app.models.client import Client
from app.models.portfolio import Portfolio
from app.models.holding import Holding
from app.models.analytics_snapshot import AnalyticsSnapshot
from app.models.ai_report import AIReport
from app.database import SessionLocal, create_tables
create_tables()
PW_PEPPER = os.getenv("PW_PEPPER", "wealthos-pepper")
def hp(pw): return hmac.new(PW_PEPPER.encode(), pw.encode(), hashlib.sha256).hexdigest()
db = SessionLocal()
e = db.query(User).filter(User.email=="tiwarikshitij20@gmail.com").first()
if e:
    e.hashed_password = hp("WealthOS2026!"); e.is_active = True; db.commit()
    print("User password reset. Active:", e.is_active)
    print("Stored hash:", e.hashed_password[:20], "...")
else:
    db.add(User(id=str(uuid.uuid4()), email="tiwarikshitij20@gmail.com",
        hashed_password=hp("WealthOS2026!"), full_name="Kshitij Tiwari",
        firm_name="WealthOS", role="admin", is_active=True, created_at=datetime.utcnow()))
    db.commit(); print("Admin created fresh")
# Verify
u = db.query(User).filter(User.email=="tiwarikshitij20@gmail.com").first()
print("Verification — email:", u.email, "active:", u.is_active)
print("Hash matches:", u.hashed_password == hp("WealthOS2026!"))
db.close()
EOF
```

You should see `Hash matches: True`. If you see `False`, the PW_PEPPER in the running service differs from the default. Check:
```bash
grep PEPPER /opt/wlthos/backend/.env 2>/dev/null
grep PEPPER /etc/systemd/system/wealthos-api.service
```

---

### Fix C: Debug JavaScript in browser (if CORS is fine but login still fails)

1. Open `https://wlthos.in/app.html` in Chrome
2. Press `F12` → Console tab
3. Try to log in
4. Look for red errors in Console
5. Switch to Network tab → look for the `/api/v1/auth/login` request → check Status and Response

The `app.html` login function shows inline errors. If you see **nothing change** after clicking (button doesn't say "Signing in..."), there is a JavaScript error. The most common cause: a syntax error introduced in the HTML file.

**Quick fix — replace the button click entirely:**
Open browser console and paste:
```javascript
fetch('https://api.wlthos.in/api/v1/auth/login', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({email: 'tiwarikshitij20@gmail.com', password: 'WealthOS2026!'})
}).then(r => r.json()).then(d => console.log(d)).catch(e => console.error(e))
```

This bypasses the form entirely. If it logs an object with `access_token`, the API is reachable and CORS is fine — the bug is in the form JS. If it logs a CORS error, Fix A is needed.

---

## 6. FULL FILE STRUCTURE (what's deployed)

```
/opt/wlthos/
├── backend/
│   ├── main.py                    ← ENTRY POINT (v2.0 — imports from app/)
│   ├── app/
│   │   ├── main.py                ← NOT the entry point (main.py at root is)
│   │   ├── api/v1/
│   │   │   ├── auth.py            ← POST /api/v1/auth/login, /signup, GET /me
│   │   │   ├── upload.py          ← POST /api/v1/upload/ (CAS PDF ingestion)
│   │   │   ├── portfolios.py      ← GET/DELETE /api/v1/portfolios/
│   │   │   ├── analytics_routes.py← GET /api/v1/analytics/{id}
│   │   │   ├── insights.py        ← POST /api/v1/insights/{id}/generate
│   │   │   └── reports.py         ← GET /api/v1/reports/{id}/summary
│   │   ├── models/
│   │   │   ├── user.py            ← fields: id, email, hashed_password, full_name, firm_name, role, is_active
│   │   │   ├── portfolio.py       ← fields: id, advisor_id, name, filename, status, total_value
│   │   │   ├── holding.py         ← fields: instrument_name, isin, asset_class, sector, current_value...
│   │   │   ├── analytics_snapshot.py
│   │   │   ├── ai_report.py
│   │   │   └── client.py
│   │   ├── analytics/             ← 10 analytics modules (asset_allocation, concentration, etc.)
│   │   ├── normalizer/            ← ISIN resolution, deduplication
│   │   ├── parsers/               ← CAS PDF + Excel parsers
│   │   └── services/
│   │       └── portfolio_service.py
│   ├── engines/                   ← 15+ quant engines (NOT yet wired to API routes)
│   │   ├── analytics_core.py      ← v4.0 orchestrator
│   │   ├── scenario_engine.py     ← 20 scenarios, 11-variable macro matrix
│   │   ├── risk_engine.py         ← EVT/GPD VaR, FRTB
│   │   ├── lookthrough_engine.py  ← fund→stock→sector→macro
│   │   ├── cas_parser.py          ← CAMS + KFin PDF parser
│   │   └── [12 more engines]
│   └── wealthos.db                ← SQLite DB (or ignored if PostgreSQL is used)
├── frontend/dist/
│   ├── index.html                 ← Marketing site
│   ├── app.html                   ← Login page (REAL JWT auth wired)
│   └── dashboard.html             ← Advisor dashboard (has auth guard)
└── infra/
    ├── nginx/wealthos-api-cors-fix.conf  ← The good CORS config (should be live)
    └── systemd/wealthos-api.service
```

---

## 7. PASSWORD HASHING — HOW IT WORKS

Auth uses HMAC-SHA256 with a pepper:
```python
import hashlib, hmac
PW_PEPPER = os.getenv("PW_PEPPER", "wealthos-pepper")
hashed = hmac.new(PW_PEPPER.encode(), password.encode(), hashlib.sha256).hexdigest()
```

**The pepper must match between:**
- The seed script that created the user
- The running service that validates login

If `.env` has no `PW_PEPPER`, both use `"wealthos-pepper"`. If `.env` has `PW_PEPPER=something`, the service uses that and the seed must also use it.

**To verify the user's password hash is correct:**
```bash
ssh root@64.227.147.106
cd /opt/wlthos/backend && source venv/bin/activate
python3 -c "
import os, sys, hashlib, hmac
sys.path.insert(0, '.')
from app.models.user import User
from app.models.client import Client
from app.models.portfolio import Portfolio
from app.models.holding import Holding
from app.models.analytics_snapshot import AnalyticsSnapshot
from app.models.ai_report import AIReport
from app.database import SessionLocal
PW_PEPPER = os.getenv('PW_PEPPER', 'wealthos-pepper')
def hp(pw): return hmac.new(PW_PEPPER.encode(), pw.encode(), hashlib.sha256).hexdigest()
db = SessionLocal()
u = db.query(User).filter(User.email=='tiwarikshitij20@gmail.com').first()
print('User found:', bool(u))
print('Active:', u.is_active if u else 'N/A')
print('Hash matches:', u.hashed_password == hp('WealthOS2026!') if u else 'N/A')
print('Pepper used:', PW_PEPPER)
db.close()
"
```

---

## 8. DEPLOY COMMANDS (canonical, verified working)

```bash
# Deploy backend (NEVER overwrite DB files)
rsync -avz /Users/user/Documents/Claude/Projects/WealthOS/backend/ \
  root@64.227.147.106:/opt/wlthos/backend/ \
  --exclude='__pycache__' --exclude='venv' --exclude='.env' \
  --exclude='*.pyc' --exclude='wealthos.db' --exclude='wealthos.db-shm' --exclude='wealthos.db-wal'

# Deploy frontend (always chmod after)
rsync -avz /Users/user/Documents/Claude/Projects/WealthOS/frontend/dist/ \
  root@64.227.147.106:/opt/wlthos/frontend/dist/ && \
  ssh root@64.227.147.106 "chmod 644 /opt/wlthos/frontend/dist/*.html"

# Restart backend (correct service name)
ssh root@64.227.147.106 "systemctl restart wealthos && sleep 3 && systemctl status wealthos"

# Verify health
ssh root@64.227.147.106 "curl -s http://127.0.0.1:8000/health"
```

---

## 9. WHAT IS NOT YET BUILT (after login works)

These are the next features in priority order:

1. **Dashboard data from real API** — dashboard.html shows hardcoded demo data (Rajesh Mehta etc). Wire it to `GET /api/v1/portfolios/` and `GET /api/v1/analytics/{id}`

2. **CAS Upload end-to-end test** — the upload pipeline exists (`POST /api/v1/upload/`) but has never been tested with a real CAS PDF. Test it.

3. **Scenario engine API route** — `engines/scenario_engine.py` has 20 scenarios but no API route. Add `POST /api/v1/scenarios/run`.

4. **Lookthrough engine API route** — `engines/lookthrough_engine.py` exists but not wired to any route.

5. **PostgreSQL confirmed** — the DB is ambiguous (SQLite or PG). Confirm which one the service is using and ensure it's consistent.

6. **Multi-tenant isolation** — all DB queries must filter by `advisor_id`. The portfolio service does this. Verify it's consistent across all routes.

---

## 10. DESIGN SYSTEM (do not deviate)

| Token | Value |
|-------|-------|
| Accent | `#1E40FF` |
| Fonts | Inter (UI) + JetBrains Mono (data/numbers) |
| Border radius | 6px cards, 10px modals |
| Status OK | `#16A34A` |
| Status Warn | `#B45309` |
| Status Danger | `#DC2626` |
| Dark mode | `data-theme="dark"` on `<html>` |
| Logo | Two overlapping 17×17 squares, blue filled square offset bottom-right |

---

## 11. NON-NEGOTIABLE RULES (from project brief)

1. **LLMs never calculate** — every number comes from deterministic Python. AI only narrates.
2. **ISIN is the primary key** — never match instruments by name alone.
3. **Determinism is law** — same input → same output, always.
4. **Explainability is mandatory** — every metric has a methodology version and audit trail.
5. **No CORSMiddleware in FastAPI** — nginx handles CORS exclusively. Adding it causes duplicate headers that break Safari.
6. **Service name is `wealthos`** — NOT `wealthos-api`. Corrected 2026-08-06; the
   old instruction caused ten weeks of no-op deploys. See §2.

---

## 12. SUMMARY OF TODAY'S SESSION (2026-05-27)

**What was done:**
- Rewrote `backend/main.py` to run the `app/` stack (proper auth, upload pipeline, analytics)
- Fixed `infra/systemd/wealthos-api.service` (removed PostgreSQL dependency)
- Wrote `backend/scripts/reset_and_seed.py` (DB migration + admin seed)
- Wired real JWT auth in `frontend/dist/app.html` (replaces fake `<a href>` redirect)
- Added auth guard to `frontend/dist/dashboard.html` (no token → redirect to login)
- Deployed all changes to server
- Confirmed API works via direct curl (returns valid JWT)
- Seeded admin user in database (confirmed "User updated")

**What is still broken:**
- Browser login flow does not complete — the browser cannot reach the API successfully
- Root cause is unconfirmed: CORS response headers OR JavaScript error in app.html
- Dashboard data is still 100% hardcoded demo data (not from API)

**Immediate next action:**
Run the Mac-side CORS test from Section 5 Step 1 to identify the exact failure point, then apply Fix A (nginx) or Fix C (JavaScript) accordingly.
