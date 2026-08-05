# WealthOS — FRED Macro Layer Deployment Runbook

**Built:** 2026-05-28
**Status:** Code committed locally + tested (14/14 pass). Awaiting SCP to server + key setting.
**Server:** `root@64.227.147.106` · `/opt/wlthos/backend/`
**GitHub:** Spock2989/wealthOS

---

## 1. What was built

Production-grade macro data layer reading from St. Louis Fed FRED API, with deterministic DB caching, full provenance, and audit traceability — matches WealthOS Prime Directives.

| File | LOC | Role |
|---|---|---|
| `backend/app/services/fred_client.py` | 175 | HTTP adapter; rate limit (110/min); retry on 5xx/429; returns structured `FredResult` |
| `backend/app/services/macro_cache.py` | 152 | DB read/upsert; snapshot builder; staleness flag per frequency |
| `backend/app/services/macro_registry.py` | 70 | Single source of truth for the 12 tracked series |
| `backend/app/models/macro_observation.py` | 50 | SQLAlchemy model — composite PK (series_id, observation_date) + provenance |
| `backend/app/api/v1/macro.py` | 65 | 3 read-only endpoints |
| `backend/scripts/sync_fred.py` | 95 | Idempotent daily sync; cron-ready; logs structured diffs |
| `backend/tests/test_fred_client.py` | 165 | 7 tests including idempotence + determinism |
| `backend/.env.example` | +4 | `FRED_API_KEY=` placeholder (real key never committed) |
| `backend/app/main.py` | +3 | Router + model wiring |

### 12 series tracked (Indian-wealth relevance)

| Series | Description | Geography |
|---|---|---|
| DGS10 | US 10Y Treasury yield | US |
| DGS2 | US 2Y Treasury yield | US |
| T10Y2Y | US 10Y-2Y spread (recession indicator) | US |
| DEXINUS | INR per USD | India |
| CPIAUCSL | US CPI All Items | US |
| INDCPIALLMINMEI | India CPI (OECD via FRED) | India |
| VIXCLS | VIX | Global |
| BAMLH0A0HYM2 | US HY credit spread | US |
| DCOILWTICO | WTI crude | Global |
| DCOILBRENTEU | Brent crude | Global |
| GOLDAMGBD228NLBM | Gold London PM fix | Global |
| INTDSRINM193N | India RBI discount rate | India |

### API endpoints

```
GET /api/v1/macro/series             → list of supported series + metadata
GET /api/v1/macro/snapshot           → latest value per series for dashboard
GET /api/v1/macro/series/{id}        → full history (optional start/end query)
```

---

## 2. SECURITY RULE — non-negotiable

API keys go in `/opt/wlthos/backend/.env` on the server **only**. Never in chat, never in code, never in git. The code reads `os.getenv("FRED_API_KEY")` at runtime. If a key is ever pasted into a chat conversation, treat it as burned and rotate it at https://fred.stlouisfed.org immediately.

---

## 3. Deploy runbook

### Phase A — Local test + commit + push

```bash
cd /Users/user/Documents/Claude/Projects/WealthOS/backend
source .venv/bin/activate
pip install -q httpx
PYTHONPATH=. pytest tests/ -v
# Expect: 14 passed
```

```bash
cd /Users/user/Documents/Claude/Projects/WealthOS

git add backend/app/services/fred_client.py \
        backend/app/services/macro_cache.py \
        backend/app/services/macro_registry.py \
        backend/app/models/macro_observation.py \
        backend/app/api/v1/macro.py \
        backend/scripts/sync_fred.py \
        backend/tests/test_fred_client.py \
        backend/app/main.py \
        backend/.env.example

git status
git commit -m "feat(macro): FRED integration — 12-series registry, DB cache, API, sync script, 7 tests"
git push origin main
```

### Phase B — SCP code to server

```bash
cd /Users/user/Documents/Claude/Projects/WealthOS

ssh root@64.227.147.106 'mkdir -p /opt/wlthos/backend/app/services /opt/wlthos/backend/app/api/v1 /opt/wlthos/backend/app/models /opt/wlthos/backend/scripts'

scp backend/app/services/fred_client.py \
    backend/app/services/macro_cache.py \
    backend/app/services/macro_registry.py \
    root@64.227.147.106:/opt/wlthos/backend/app/services/

scp backend/app/models/macro_observation.py \
    root@64.227.147.106:/opt/wlthos/backend/app/models/

scp backend/app/api/v1/macro.py \
    root@64.227.147.106:/opt/wlthos/backend/app/api/v1/

scp backend/scripts/sync_fred.py \
    root@64.227.147.106:/opt/wlthos/backend/scripts/

scp backend/app/main.py \
    root@64.227.147.106:/opt/wlthos/backend/app/main.py

scp backend/tests/test_fred_client.py \
    root@64.227.147.106:/opt/wlthos/backend/tests/

scp backend/.env.example \
    root@64.227.147.106:/opt/wlthos/backend/.env.example
```

### Phase C — Verify + set the key on the server

```bash
ssh root@64.227.147.106
cd /opt/wlthos/backend
source venv/bin/activate

# 1. server tests
PYTHONPATH=. pytest tests/test_fred_client.py -v
# Expect: 7 passed

# 2. set the FRED key — use a ROTATED key, not one previously pasted in chat
nano .env
# Add this line, replacing the value with your real key:
#   FRED_API_KEY=your_real_rotated_fred_key_here
# Save: Ctrl+O, Enter, Ctrl+X

# 3. verify key is set without echoing it
grep -c '^FRED_API_KEY=' .env
# Expect: 1

# 4. restart service
systemctl restart wealthos
sleep 2
systemctl status wealthos --no-pager | head -10
# Expect: active (running)

# 5. first sync — pulls 5y history for all 12 series
PYTHONPATH=. python3 scripts/sync_fred.py
# Expect: ~12 "series_ok" lines, then "fred_sync done success=12 failure=0"
```

### Phase D — Smoke test (still on server)

```bash
PYTHONPATH=. python3 - <<'PY'
from app.database import SessionLocal
from app.services.macro_cache import build_snapshot
from app.services.macro_registry import registered_ids
db = SessionLocal()
snap = build_snapshot(db, registered_ids())
for s in snap.series:
    stale = " [STALE]" if s.is_stale else ""
    print(f"  {s.series_id:22s}  {str(s.latest_date):10s}  {str(s.latest_value):>10s}{stale}")
db.close()
PY
```

Expect 12 lines like:

```
  DGS10                   2026-05-27       4.28
  DGS2                    2026-05-27       4.91
  T10Y2Y                  2026-05-27       -0.63
  DEXINUS                 2026-05-23       83.45
  ...
```

### Phase E — Schedule daily cron

```bash
crontab -e
# Add this line — 00:30 UTC = 06:00 IST, after FRED's NY-evening update:
30 0 * * * cd /opt/wlthos/backend && /opt/wlthos/backend/venv/bin/python scripts/sync_fred.py >> /var/log/wealthos-fred.log 2>&1
```

---

## 4. Rollback (if anything breaks)

```bash
ssh root@64.227.147.106 '
  systemctl stop wealthos
  cd /opt/wlthos/backend
  rm -f app/services/fred_client.py app/services/macro_cache.py app/services/macro_registry.py
  rm -f app/models/macro_observation.py app/api/v1/macro.py scripts/sync_fred.py
  # restore main.py from GitHub commit a6a72ea (ingestion-v2 deploy) or backup
  systemctl start wealthos
'
```

The `macro_observations` table is harmless if left behind — the router is what activates it.

---

## 5. What I deliberately did NOT deploy

**Scenario engine FRED wiring** — `engines/scenario_engine.py` still uses internal reference values. Wiring it to live FRED is the next session's commit, with a golden test pinning current scenario outputs so no numbers shift unintentionally.

---

## 6. What this unlocks

- **Macro panel on dashboard** — single call to `/api/v1/macro/snapshot` returns 12 series for rendering as a grid or heatmap
- **Time-series charts** — `/api/v1/macro/series/{id}` feeds Chart.js directly
- **Live macro context** in scenario propagation (next deploy)
- **Audit trail** — every observation has `fetched_at` + `methodology_version` + source = "FRED"

---

## 7. MVP rating delta

| Before this session | After ingestion v2 deploy | After FRED deploy |
|---|---|---|
| 6.2 | 7.0 | **7.4** |

**Next moves to reach 8.0:**

1. Wire FRED into scenario engine (1 session)
2. Aladdin-grade dashboard upgrade — AG Grid + Chart.js + heatmaps (3 sessions)
3. Postgres migration (1 session)
