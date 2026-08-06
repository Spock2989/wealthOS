# WealthOS

**Institutional-grade financial intelligence infrastructure for Indian mutual fund and equity portfolios.**

Live: [https://wlthos.in](https://wlthos.in) · API: [https://api.wlthos.in/docs](https://api.wlthos.in/docs)

---

## Architecture

```
WealthOS/
├── backend/
│   ├── engines/            ← Analytics engines (deterministic math)
│   │   ├── price_provider.py
│   │   ├── normalization.py
│   │   ├── lookthrough.py
│   │   ├── overlap.py
│   │   ├── quant_analytics.py
│   │   └── scenario_engine.py
│   ├── routers/            ← FastAPI route handlers
│   │   ├── users.py
│   │   ├── portfolio.py
│   │   └── analytics.py
│   ├── scripts/
│   │   └── seed_amfi.py    ← AMFI instrument master seeder
│   ├── models.py           ← SQLAlchemy models
│   ├── models_amfi.py      ← AMFIInstrument model
│   ├── database.py         ← DB session + engine
│   └── main.py             ← FastAPI app entry
├── frontend/
│   └── dist/
│       ├── index.html      ← Landing page
│       └── app.html        ← Advisor dashboard
├── infra/                  ← Server config (auto-pulled)
│   ├── nginx/
│   └── systemd/
├── scripts/
│   ├── deploy.sh           ← Deploy local → production
│   ├── pull-from-server.sh ← Pull production → local
│   ├── setup-github.sh     ← One-time GitHub setup
│   └── status.sh           ← Check server health
├── Makefile                ← All commands
├── CLAUDE.md               ← AI build instructions
└── wealthos.code-workspace ← Open in VSCode
```

---

## Quick Start

### Open in VSCode
```bash
open wealthos.code-workspace
# or: code wealthos.code-workspace
```

### One-time setup (after cloning)
```bash
# Pull current code from production server
make pull

# Connect to GitHub (already at github.com/Spock2989/wealthOS)
git remote add origin git@github.com:Spock2989/wealthOS.git
git push -u origin main
```

---

## Daily Workflow

```bash
# 1. Edit files in VSCode
# 2. Commit + deploy in one command:
make deploy

# Or separately:
make backend     # deploy backend only
make frontend    # deploy frontend only (app.html, index.html)
make restart     # just restart API service

# Check status
make status

# Live logs
make logs

# SSH into server
make ssh
```

---

## Server

| Item | Value |
|------|-------|
| VPS | DigitalOcean 64.227.147.106 |
| OS | Ubuntu 24.04 |
| Backend | FastAPI + uvicorn (systemd, 2 workers) |
| Database | PostgreSQL `wealthosdb` |
| Web server | Nginx |
| Backend path | `/opt/wlthos/backend/` |
| Frontend path | `/opt/wlthos/frontend/dist/` |

### Key commands on server
```bash
# SSH
ssh -o ServerAliveInterval=30 root@64.227.147.106

# Restart API
systemctl restart wealthos && sleep 12 && curl https://api.wlthos.in/health

# Logs
journalctl -u wealthos -n 50 --no-pager

# Seed AMFI data
make seed
# or: cd /opt/wlthos/backend && source venv/bin/activate && python3 scripts/seed_amfi.py
```

---

## Environment Variables (server)

Set in `/opt/wlthos/backend/.env` and `/etc/systemd/system/wealthos-api.service`:

```
DATABASE_URL=postgresql://wealthos:WealthOS_DB_2026!@localhost/wealthosdb
```

---

## GitHub

Repo: [https://github.com/Spock2989/wealthOS](https://github.com/Spock2989/wealthOS)

```bash
# Push to GitHub
git add -A && git commit -m "your message" && git push origin main
```

---

## Design System

```css
--accent: #1E40FF;
--ok: #16A34A;
--warn: #B45309;
--danger: #DC2626;
font-family: 'Inter', sans-serif;
font-family: 'JetBrains Mono', monospace; /* numbers */
```

---

## Next Up

- [ ] Wire real portfolio analytics to dashboard API endpoints
- [ ] Build AMC monthly holdings crawler (look-through engine)
- [ ] Add Redis caching for analytics results
- [ ] Add Celery for async CAS processing
- [ ] Mobile responsive layout
- [ ] RBI + FRED macro data connector
