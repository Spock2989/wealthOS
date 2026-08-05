# Phase 1 Status — Stop Presenting Synthetic Data As Real

**Branch:** `fix/phase1-synthetic-data-disclosure`
**Base:** `main` @ `2d1da82`
**Status:** 5 of 6 items complete. **NOT merged. NOT deployed.**
**Date:** 2026-08-05

Phase 1 goal: the system was showing modelled fund constituents as if they
were real AMFI disclosures. The fix is **disclosure, not removal** —
`generate_synthetic_portfolio()` stays as a labelled fallback.

---

## Commits on this branch

| # | SHA | What it fixed |
|---|---|---|
| 1 | `dffcb5a` | Provenance is persisted and threaded through look-through |
| 2 | `80831a6` | Commodity + international FoFs no longer get a fake Nifty portfolio |
| 3 | `5642cc3` | Placeholder `ANTHROPIC_API_KEY` rejected with an actionable message |
| 4 | `0130065` | Duplicate uploads return 409 instead of silently creating a twin |
| 5 | `5bc3116` | X-Ray banner states how many funds are modelled |

### 1 — `dffcb5a` provenance persistence
`get_fund_constituents()` returned `"synthetic_estimated"` on first generation,
but `store_constituents()` dropped the tag and every later read returned
`"cache"`. Modelled data was laundered into apparent fact from the second call
onward.

- added `fund_constituents.source` + `ALTER TABLE` for existing tables
- provenance now follows the data through the cache, not the access path
- rows predating the column read as `unknown_legacy`, **never** `amfi_live`
- `_dominant_source()` biases to honesty: a fund is `amfi_live` only if every
  constituent is
- `build_portfolio_lookthrough()` emits `data_source` / `is_estimated` per
  source entry, and `funds_real_count` vs `funds_synthetic_count` separately
  from `funds_with_constituents`

Verified: synthetic tag survives a cache round-trip; a legacy table with no
`source` column reads back as `unknown_legacy`.

### 2 — `80831a6` no template for commodity/international
`_detect_fund_category()` mapped silver/gold/commodity FoFs and international
feeders to the `"diversified"` Nifty-50 proxy. **HDFC Silver ETF FoF was
reported holding HDFC Bank 8%, ICICI Bank 6.5%, Reliance 6%** — securities it
cannot own. This was the main driver of the "×17 funds" overlap, since all 17
funds drew from one large-cap pool.

Also fixed punctuation matching: `Franklin U.S. Opportunities` did not match the
`us opportunities` keyword and was still being modelled.

Verified: all 3 offending prod funds now return `[]`; ELSS/flexi-cap/debt
fallbacks still return their templates (25/15/10 holdings).

### 3 — `5642cc3` API key validation
Prod holds `sk-ant-api03-YOUR_ACTUAL_KEY_HERE`. The old `if not key` guard
passed on that truthy stub, so the SDK was called and the operator saw a generic
auth error — the cause of the **AI Memo 500**.

`startup_check()` logs the exact problem at boot. It deliberately does **not**
raise: per CLAUDE.md §2.2 the AI layer is optional and must not gate auth,
uploads or analytics.

### 4 — `0130065` duplicate upload guard
Filename comparison flattens separators, so `portfolio kt.pdf` and
`portfolio_kt.pdf` are recognised as the same file. Returns **409** with the
existing `portfolio_id`, not a hard block — a refreshed monthly CAS legitimately
reuses its filename, so callers can repeat with `allow_duplicate=true`.

### 5 — `5bc3116` X-Ray disclosure banner
The banner already had a `hasSynthetic` branch, but it tested
`s.data_source === 'synthetic_estimated'` on entries the backend never
populated — so it could never fire. Now reads real counts and says:

> **Estimated data: N of M funds use modelled constituents, not AMFI
> disclosures.**

Driven by `funds_synthetic_count`, *not* `funds_with_constituents` (which counts
modelled and real together — the original bug).

---

## What's left of Phase 1

### Item 6 — header labels (NOT STARTED)
In `frontend/dist/dashboard.html`:

1. **Neff** — currently renders bare `8.4` (element `#clientNeff`, set at
   ~line 1583). Should read **"Neff 8.4 of 17"** so the number is interpretable
   against the position count. `holding_count` is on the analytics result.
2. **Underlying position count** — the results footer (~line 2496) reads
   `'// ' + total_underlying_positions + ' UNIQUE POSITIONS'`, printing **247**
   with no qualification. Should read **"underlying positions (estimated)"**
   whenever modelled constituents contributed.
   A global `var _xrayHasEstimated` is **already declared and set** for exactly
   this (set in `_runXRay` from `funds_synthetic_count`) — it is wired but not
   yet consumed.

### Item 5, DB half — delete duplicate portfolio (NOT EXECUTED)

⚠️ **BLOCKED ON A BACKUP. Do not run this until a fresh backup exists.**

**There is no backup of the current production database.** What exists on the
server is stale and does **not** contain this data:

| File | Date | Size | Contains the portfolio? |
|---|---|---|---|
| `wealthos.db` (live) | 2026-05-27 19:24 | 3.3 MB | yes |
| `wealthos.db.bak` | 2026-05-22 04:27 | 3.2 MB | **no** — predates both uploads |
| `wealthos.db.pre_v2` | 2026-05-27 07:12 | 86 KB | **no** — near-empty, predates both |

Both duplicates were created 2026-05-27 at 18:05 and 19:07, *after* every
backup. No backup was taken during the investigation sessions — those were
strictly read-only.

**Take a backup first:**

```bash
ssh root@64.227.147.106 "cd /opt/wlthos/backend && sqlite3 wealthos.db \".backup wealthos.db.$(date +%Y%m%d_%H%M%S).bak\" && ls -la wealthos.db*"
```

**Rows that would be deleted** (verified 2026-08-05):

| Table | Rows | Note |
|---|---|---|
| `portfolios` | 1 | `5285f0cc-d08a-4780-8149-edb9a305e3d9` — "portfolio kt.pdf" |
| `holdings` | 17 | |
| `analytics_snapshots` | 1 | |
| `ai_reports` | 0 | |

The row being **kept** is `f1bb14dc-f680-49ed-ba06-562538e971a9`
("portfolio_kt.pdf", the later upload, also 17 holdings, same ₹169,044.35).

```sql
-- Verify first — expect exactly 1 row, name 'portfolio kt.pdf'
SELECT id, name, filename, total_value, created_at
FROM portfolios WHERE id = '5285f0cc-d08a-4780-8149-edb9a305e3d9';

-- Then, inside a transaction:
BEGIN;
DELETE FROM analytics_snapshots WHERE portfolio_id = '5285f0cc-d08a-4780-8149-edb9a305e3d9';
DELETE FROM holdings           WHERE portfolio_id = '5285f0cc-d08a-4780-8149-edb9a305e3d9';
DELETE FROM ai_reports         WHERE portfolio_id = '5285f0cc-d08a-4780-8149-edb9a305e3d9';
DELETE FROM portfolios         WHERE id           = '5285f0cc-d08a-4780-8149-edb9a305e3d9';
-- Confirm the keeper is intact: must return 17
SELECT COUNT(*) FROM holdings WHERE portfolio_id = 'f1bb14dc-f680-49ed-ba06-562538e971a9';
COMMIT;
```

The ORM has `cascade="all, delete-orphan"`, but raw SQLite does not enforce it
here — hence the explicit child deletes, children first.

---

## Other open items

### Prod `.env` still has a placeholder ANTHROPIC_API_KEY
`/opt/wlthos/backend/.env` contains `sk-ant-api03-YOUR_ACTUAL_KEY_HERE`
(28 chars). **AI Memo will keep returning 500 until this is replaced.**

I did not set this — supplying API credentials is an operator action, not
something I do on your behalf. Generate a key at
<https://console.anthropic.com>, then:

```bash
ssh root@64.227.147.106 "nano /opt/wlthos/backend/.env"   # replace the line
ssh root@64.227.147.106 "systemctl restart wealthos-api"
ssh root@64.227.147.106 "journalctl -u wealthos-api -n 20 --no-pager | grep -i 'ANTHROPIC\|AI memo'"
```

After commit `5642cc3` the log states plainly whether the key validated or why
it was rejected.

### Local `.venv` is broken
`backend/.venv` is Python **3.14.4** and is missing most of `requirements.txt`
(`sqlalchemy`, `fastapi`, `uvicorn`, `pyjwt`, `bcrypt`, `python-multipart`,
`pymupdf`, `anthropic`). `pytest tests/` aborts during collection, so **0 of 21
tests run**. Prod runs Python 3.12 — match it:

```bash
cd /Users/user/Documents/Claude/Projects/WealthOS/backend
rm -rf .venv && python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
PYTHONPATH=. .venv/bin/pytest tests/ -v
```

Phase 1 logic was verified with standalone assertion scripts against the real
prod values instead, since the suite could not run.

### Deploy state
**Nothing in this branch is on the server.** Note prod boots
`/opt/wlthos/backend/main.py` (root) via systemd — **not** `app/main.py`. See
the earlier investigation: `app/main.py` is served by a PM2 process on port 8765
that nginx does not route to.

The `source` column migration runs automatically via `_ensure_source_column()`
on first constituent read/write after deploy.

**Existing prod `fund_constituents` rows (381, all synthetic) will read back as
`unknown_legacy`** — correctly flagged as not-real, though not specifically as
"synthetic". To label them precisely, after deploying run:

```sql
UPDATE fund_constituents SET source = 'synthetic_estimated' WHERE source IS NULL;
```

---

## Resume from here

```bash
cd /Users/user/Documents/Claude/Projects/WealthOS && git checkout fix/phase1-synthetic-data-disclosure && git log --oneline main..HEAD
```

Then pick up **item 6** in `frontend/dist/dashboard.html` (`_xrayHasEstimated`
is already wired and waiting to be consumed), and **item 5's DELETE** once a
fresh backup exists.
