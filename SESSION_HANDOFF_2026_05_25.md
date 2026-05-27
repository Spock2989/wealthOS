# WealthOS — Full Session Handoff
**Date:** 2026-05-25  
**Use this document to resume in a new chat.**

---

## 🚀 FIRST THING TO DO IN NEW CHAT

Open a **fresh Mac terminal** and run these 3 blocks in order:

### Block 1 — Commit & push fixes (Mac terminal)
```bash
cd /Users/user/Documents/Claude/Projects/WealthOS && git add backend/routers/users.py && git add -f frontend/dist/landing.html && git commit -m "fix: 5 auth bugs" && git push origin main
```

### Block 2 — Deploy to server (Mac terminal)
```bash
rsync -avz /Users/user/Documents/Claude/Projects/WealthOS/backend/ root@64.227.147.106:/opt/wlthos/backend/
```
```bash
rsync -avz /Users/user/Documents/Claude/Projects/WealthOS/frontend/dist/ root@64.227.147.106:/var/www/wlthos/
```

### Block 3 — SSH in, restart backend, seed admin (server terminal)
```bash
ssh -o ServerAliveInterval=30 root@64.227.147.106
```
Then once inside:
```bash
systemctl restart wealthos && sleep 3 && python3 /opt/wlthos/backend/scripts/seed_admin.py
```

After these 3 blocks, login works at **wlthos.in/app.html** with:
- Email: `tiwarikshitij20@gmail.com`
- Password: `WealthOS2026!`

---

## 📁 PROJECT STRUCTURE

```
/Users/user/Documents/Claude/Projects/WealthOS/
├── backend/
│   ├── main.py              ← RUNNING server (not backend/app/)
│   ├── models.py            ← User model (name, password_hash, firm, is_active, is_admin)
│   ├── auth.py              ← bcrypt hash + JWT token
│   ├── database.py          ← SQLAlchemy, reads DATABASE_URL env var
│   ├── routers/
│   │   ├── users.py         ← Auth router (/v1/auth/*) — FIXED this session
│   │   ├── portfolios.py
│   │   ├── ingestion.py
│   │   ├── demo.py
│   │   ├── data.py
│   │   └── memos.py
│   └── scripts/
│       └── seed_admin.py    ← Creates/updates admin user
├── frontend/
│   └── dist/
│       ├── app.html         ← Main dashboard app — FIXED & DEPLOYED
│       ├── landing.html     ← Marketing site — FIXED, not deployed yet
│       └── index.html
└── SESSION_HANDOFF_2026_05_25.md  ← this file
```

---

## 🐛 BUGS FIXED THIS SESSION (in local code, not yet deployed)

### backend/routers/users.py
1. **Register field name**: `full_name=` → `name=` (User model has `name` not `full_name`)
2. **Activation**: `is_active=False` → `is_active=True` (no SMTP = users stuck forever)
3. **is_verified**: removed (column doesn't exist in User model)
4. **Email verification flow**: removed (no SMTP configured on server)
5. **Firm field**: `getattr(user, "firm_name", "")` → `getattr(user, "firm", "")`

### frontend/dist/landing.html
6. **API URL**: `https://wlthos.in/api/v1` → `https://api.wlthos.in/v1`
7. **Signup endpoint**: `/auth/signup` → `/auth/register`
8. **Redirect URL**: `https://wlthos.in/dashboard` → `https://wlthos.in/app.html`
9. **Token key**: now writes both `wlthos_token` AND `wos_token` (app.html reads `wos_token`)

---

## 🏗️ ARCHITECTURE FACTS

| Item | Value |
|------|-------|
| Server IP | 64.227.147.106 |
| Server OS | Ubuntu 24.04 |
| Backend path | /opt/wlthos/backend/ |
| Frontend path | /var/www/wlthos/ |
| Backend service | `systemctl restart wealthos` |
| API base URL | https://api.wlthos.in |
| App URL | https://wlthos.in/app.html |
| Landing URL | https://wlthos.in (serves landing.html) |
| DB | PostgreSQL — wealthos:WealthOS_DB_2026!@localhost/wealthosdb |
| Deployment | rsync from Mac (server is NOT a git repo) |
| Python on server | python3 (not python) |

### User model fields (backend/models.py)
```python
id            String (UUID)
email         String, unique
name          String  ← NOT full_name
password_hash String
is_active     Boolean
is_admin      Boolean
firm          String  ← NOT firm_name
role          String
```

### Two backends — only one matters:
- ✅ RUNNING: `backend/main.py` with `backend/routers/`
- ❌ NOT RUNNING: `backend/app/` (ignore this)

---

## 🎯 REMAINING WORK (v4.1 Engine Completion)

### Task 15 — Missing institutional engines
- EWMA volatility forecasting
- PCA factor decomposition
- Bai-Perron structural break detection
- Factor DNA wiring to API

### Task 16 — Wire analytics to API endpoints
- Connect analytics_core.py outputs to portfolio endpoints
- Verify /v1/portfolios/{id}/analytics response shape
- Test reanalyze button in dashboard

---

## 🔑 ALL CREDENTIALS

| Item | Value |
|------|-------|
| Admin email | tiwarikshitij20@gmail.com |
| Admin password | WealthOS2026! |
| GitHub repo | https://github.com/Spock2989/wealthOS |
| Server SSH | `ssh -o ServerAliveInterval=30 root@64.227.147.106` |
| DB URL | postgresql://wealthos:WealthOS_DB_2026!@localhost/wealthosdb |

---

## 💬 CONTEXT FOR NEW CHAT

Paste this at the start of the new chat:

> "I'm building WealthOS — an institutional portfolio intelligence platform for Indian wealth management. Resuming from SESSION_HANDOFF_2026_05_25.md in my project folder. The file has the full context. Start by reading it and then complete the pending deployment steps."
