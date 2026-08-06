# Phase 1 Status — Stop Presenting Synthetic Data As Real

**Branch:** `fix/phase1-synthetic-data-disclosure`
**Base:** `main` @ `2d1da82`
**Status:** all 6 items complete in code. **NOT merged. NOT deployed.**
The one remaining action is an operator task: set a real `ANTHROPIC_API_KEY`
in prod `.env` (see below). Item 5's production DELETE was executed 2026-08-06.
**Date:** 2026-08-05, updated 2026-08-06

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

### Item 6 — header labels ✅ DONE — commit `7c72b45`
In `frontend/dist/dashboard.html`:

1. **Neff** now renders **"8.4 of 17"** instead of a bare `8.4`, which read like
   a score out of 10 rather than the effective number of independent bets.
   Falls back to the bare value when `holding_count` is absent, rather than
   printing "of undefined".
2. **Underlying position count** now reads **"247 UNDERLYING POSITIONS
   (ESTIMATED)"** whenever modelled constituents contributed, instead of
   "247 UNIQUE POSITIONS" presented as counted fact.

Consumes `_xrayHasEstimated`, which `5bc3116` declared and set from
`funds_synthetic_count` but left unread. When real AMFI coverage lands and
`funds_synthetic_count` reaches 0, the "(ESTIMATED)" qualifier disappears on
its own — no further code change needed.

### Item 5, DB half — delete duplicate portfolio ✅ DONE 2026-08-06

Executed against production. Backup taken first:
**`/opt/wlthos/backend/wealthos.db.20260806_044233.bak`** (3,612,672 bytes,
`integrity_check: ok`).

The WAL was checkpointed (`PRAGMA wal_checkpoint(TRUNCATE)`) **before** the
backup — it held 4.6 MB of data and the main file grew ~208 KB when folded in.
A plain `cp` of `wealthos.db` would have produced a backup missing that data.

Backup verified to contain, before any delete: 381 `fund_constituents`, both
portfolio rows, 17 holdings each, 2 users, 1 demo_request.

Deleted in one `BEGIN IMMEDIATE` transaction — 19 rows, matching the
pre-flight count exactly:

| Table | Rows deleted |
|---|---|
| `analytics_snapshots` | 1 |
| `holdings` | 17 |
| `ai_reports` | 0 |
| `portfolios` | 1 |

Post-delete verification: target returns 0/0/0; keeper
`f1bb14dc-f680-49ed-ba06-562538e971a9` intact at 1 portfolio / 17 holdings /
1 snapshot; `fund_constituents` still 381; users 2; demo_requests 1;
`integrity_check: ok`.

One other portfolio remains and was untouched: `holdings-ZC0726.xlsx`
(status `error`, 0 holdings, 2026-05-28) — a pre-existing failed upload.

<details>
<summary>Original pre-execution analysis (why a fresh backup was required)</summary>

**There was no backup of the production database.** What existed on the
server was stale and did **not** contain this data:

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

</details>

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
ssh root@64.227.147.106 "systemctl restart wealthos"
ssh root@64.227.147.106 "journalctl -u wealthos -n 20 --no-pager | grep -i 'ANTHROPIC\|AI memo'"
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

> 🚨 **CORRECTION (2026-08-06).** An earlier revision of this document said the
> live systemd unit was `wealthos-api`. **That was wrong.** The live unit is
> **`wealthos`**. `wealthos-api` is a duplicate that cannot bind port 8000 and
> has crash-looped since May; restarting it is a silent no-op. It was disabled
> on 2026-08-06. Full explanation in
> [`WEALTHOS_FULL_STATE_2026_05_27.md`](../WEALTHOS_FULL_STATE_2026_05_27.md) §2
> and [`CLAUDE.md`](../CLAUDE.md) §12.1.

Prod boots `/opt/wlthos/backend/main.py` (**root**, not `app/main.py`) via
`wealthos.service`: `uvicorn main:app --host 127.0.0.1 --port 8000 --workers 2`,
`WorkingDirectory=/opt/wlthos/backend`.

A PM2 process (`wlthos-api`) also runs `app.main:app` on port **8765**. Nginx
does not route to it — it is unreachable and its code is stale. Do not deploy
to `app/main.py` expecting it to go live.

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
