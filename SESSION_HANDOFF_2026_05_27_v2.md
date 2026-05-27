# WealthOS — v2.0 Migration Deploy Instructions
**Date:** 2026-05-27  
**What changed:** Switched running backend from legacy `routers/` to full `app/` stack. Wired real JWT auth in frontend.

---

## WHAT THIS MIGRATION DOES

| Before | After |
|--------|-------|
| `backend/main.py` → old routers, no real engines | `backend/main.py` → full `app/` stack, all v1 routes |
| `DATABASE_URL` pointed at non-existent PostgreSQL | `DATABASE_URL=sqlite:///./wealthos.db` |
| Login is a fake `<a href>` redirect | Login POSTs to `/api/v1/auth/login`, stores JWT |
| No auth guard on dashboard | Redirects to `/app.html` if no token |

---

## STEP 1 — Push to GitHub (Mac terminal)

```bash
cd /Users/user/Documents/Claude/Projects/WealthOS
git add -A
git commit -m "v2.0: switch to app/ backend, real JWT auth, fix DB URL"
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

> ⚠️ `--exclude='wealthos.db*'` is critical — do NOT overwrite the server DB file. The reset script handles that separately.

---

## STEP 3 — Deploy frontend (Mac terminal)

```bash
rsync -avz /Users/user/Documents/Claude/Projects/WealthOS/frontend/dist/ \
  root@64.227.147.106:/opt/wlthos/frontend/dist/ && \
ssh root@64.227.147.106 "chmod 644 /opt/wlthos/frontend/dist/*.html && echo FRONTEND DONE"
```

---

## STEP 4 — Update systemd service on server (SSH)

```bash
ssh root@64.227.147.106

# Copy updated service file
cp /opt/wlthos/backend/../infra/systemd/wealthos-api.service \
   /etc/systemd/system/wealthos.service
# OR manually update the service file:
nano /etc/systemd/system/wealthos.service
# Change: Environment="DATABASE_URL=sqlite:///./wealthos.db"
# Remove: After=network.target postgresql.service  →  After=network.target
# Add:    EnvironmentFile=-/opt/wlthos/backend/.env  (note the - prefix = ignore if missing)

systemctl daemon-reload
```

---

## STEP 5 — Install new Python deps on server (SSH)

```bash
ssh root@64.227.147.106
cd /opt/wlthos/backend
source venv/bin/activate
pip install python-jose[cryptography] passlib bcrypt python-multipart pymupdf openpyxl
pip install -r requirements.txt
```

---

## STEP 6 — ONE-TIME DB RESET (SSH) ⚠️ DESTRUCTIVE

This drops the old schema and creates the new one. Run once only.

```bash
ssh root@64.227.147.106
cd /opt/wlthos/backend
source venv/bin/activate
python3 scripts/reset_and_seed.py
```

Expected output:
```
✅ Backed up old DB → wealthos.db.pre_v2
🔄 Dropping all tables...
🔄 Creating new schema from app/models/...
✅ Schema created
✅ Admin user seeded: tiwarikshitij20@gmail.com
🚀 Migration complete. Restart the service: systemctl restart wealthos
```

---

## STEP 7 — Restart and verify (SSH)

```bash
ssh root@64.227.147.106
systemctl restart wealthos
sleep 3
systemctl status wealthos   # should show: active (running)
curl http://127.0.0.1:8000/health
# Expected: {"status":"ok","service":"wealthos-api","version":"2.0.0","db":"sqlite"}
```

---

## STEP 8 — End-to-end test

1. Open `https://wlthos.in/app.html`
2. Enter: `tiwarikshitij20@gmail.com` / `WealthOS2026!`
3. Click **Sign In to Dashboard**
4. Should redirect to `/dashboard.html` ✅
5. Open `/dashboard.html` directly in new tab — should redirect to `/app.html` ✅

---

## ROLLBACK

If anything breaks, revert to old backend:

```bash
ssh root@64.227.147.106

# Restore old main.py
cat > /opt/wlthos/backend/main.py << 'EOF'
from fastapi import FastAPI
from database import engine, Base
from routers import demo, users, portfolios, ingestion
Base.metadata.create_all(bind=engine)
app = FastAPI(title="WealthOS API", version="1.6.0")
app.include_router(demo.router)
app.include_router(users.router)
app.include_router(portfolios.router)
app.include_router(ingestion.router)
@app.get("/health")
def health():
    return {"status": "ok", "service": "wealthos-api", "version": "1.0.0"}
EOF

systemctl restart wealthos
```

---

## CREDENTIALS

| Item | Value |
|------|-------|
| Admin email | tiwarikshitij20@gmail.com |
| Admin password | WealthOS2026! |
| Server | root@64.227.147.106 |
| API health | https://api.wlthos.in/health |
| API docs | https://api.wlthos.in/docs |

---

## WHAT'S NOW LIVE (after this migration)

- ✅ Real JWT auth — login validates credentials, returns token
- ✅ Auth guard on dashboard — no token = redirect to login
- ✅ `/api/v1/auth/login` + `/api/v1/auth/signup` + `/api/v1/auth/me`
- ✅ `/api/v1/upload/` — CAS PDF + Excel ingestion pipeline
- ✅ `/api/v1/portfolios/` — list, get, holdings, delete
- ✅ `/api/v1/analytics/{id}` — run/rerun analytics on portfolio
- ✅ `/api/v1/reports/{id}/summary` — portfolio summary report
- ✅ `/api/v1/insights/{id}/generate` — AI narrative generation

## WHAT'S NEXT

1. **Test CAS upload end-to-end** — upload a real CAMS/KFin PDF and verify parse → analytics → DB
2. **Replace hardcoded dashboard data** — wire portfolios list and holdings table to live API
3. **Wire scenario cards to `scenario_engine.py`** — expose `POST /api/v1/scenarios/run`
4. **PostgreSQL migration** — provision PG, run Alembic, switch DATABASE_URL
