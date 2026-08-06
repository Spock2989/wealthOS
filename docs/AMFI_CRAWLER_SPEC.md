# AMFI Constituents Crawler — Specification

**Status:** Spec only. No code written.
**Date:** 2026-08-06
**Goal:** replace `generate_synthetic_portfolio()` as the primary source of fund
constituents with real monthly portfolio disclosures. `funds_real_count` is
currently **0**.

Look-through, cross-fund overlap, effective sector exposure and all 20 scenarios
are computed from constituents. Until this lands they are deterministic
arithmetic over invented inputs — see [`STATE.md`](STATE.md).

---

## 0. Findings that change the brief

The task brief described the source as: *"amfiindia.com/online-center/portfolio-disclosure
aggregates every AMC's monthly disclosure. One workbook per AMC per month."*

**Investigation shows that is not how it works.** Verified 2026-08-06 from the
production box.

### 0.1 AMFI publishes links, not files

`https://www.amfiindia.com/online-center/portfolio-disclosure` is a Next.js page
whose embedded payload contains **51 AMC records**, each carrying:

```
amc_name
amc_monthly_portfolio_disclosure      → URL on the AMC's OWN website
amc_fortnightly_portfolio_disclosure  → URL on the AMC's OWN website
amc_halfYearly_portfolio_disclosure   → URL on the AMC's OWN website
```

There is no AMFI-hosted workbook, no per-month archive, and no consistent file
naming. AMFI is a **directory**, not a repository. Every one of the 10 in-scope
AMCs resolves to a different domain with a different site framework:

| AMC | Monthly disclosure URL |
|---|---|
| HDFC | `hdfcfund.com/statutory-disclosure/portfolio/monthly-portfolio` |
| SBI | `sbimf.com/portfolios` |
| ICICI Prudential | `icicipruamc.com/news-and-media/downloads?currentTabFilter=Disclosures&subCatTabFilter=MonthlyPortfolioDisclosures` |
| Nippon | `mf.nipponindiaim.com/investor-service/downloads/factsheet-portfolio-and-other-disclosures` |
| Kotak | `kotakmf.com/Information/forms-and-downloads` |
| Aditya Birla SL | `mutualfund.adityabirlacapital.com/forms-and-downloads/portfolio` |
| UTI | `utimf.com/downloads/consolidate-all-portfolio-disclosure` |
| Axis | `axismf.com/statutory-disclosures` |
| Mirae | `miraeassetmf.co.in/downloads/portfolio` |
| DSP | `dspim.com/about-us/mandatory-disclosure/portfolio-disclosures` |

All 10 were located and mapped. **This is 10 site-specific crawlers, not one.**

### 0.2 The geo-restriction belief was wrong

`amfi_holdings_service.py` and the old X-Ray banner both claimed AMFI live data
was unavailable because the server IP is geo-restricted. Measured:

```
ipinfo:  64.227.147.106 → Bāshettihalli, Karnataka, IN (DigitalOcean AS14061)
GET https://www.amfiindia.com/online-center/portfolio-disclosure → HTTP 200
GET https://www.amfiindia.com/                                   → HTTP 200
```

The box is **in India** and AMFI answers normally. Whatever caused the original
fetch failures, it was not geography. Remove that claim from the code comments
and UI copy — it sent this project down a wrong path for months.

### 0.3 No workbook could be retrieved by plain HTTP

Three AMCs were probed with a browser User-Agent and redirect following:

| AMC | Result | Barrier |
|---|---|---|
| HDFC | **HTTP 403 Access Denied** | WAF/bot protection, returns a reference ID |
| UTI | HTTP 200, 14 KB shell, **0 file links** | client-rendered |
| Mirae | HTTP 200, 147 KB, **0 file links** | Sitecore + JS (`/DownloadPortfolio.js`), month selector rendered client-side |

**Zero sample workbooks were obtained, so this spec does not describe workbook
internals.** Header row positions, column names, merged cells, footnote rows and
equity/debt/cash row markers are *unknown* and are deliberately **not** guessed
here. Inventing them would reproduce, in the spec, the exact failure Phase 1 was
built to remove.

Documenting layouts is therefore **Phase A below, a prerequisite** — not an
assumption this spec is allowed to make.

### 0.4 Consequence for architecture

The brief's question *"one generic parser with config, or a genuine adapter per
AMC?"* cannot be answered from evidence yet. But **acquisition** is already
proven heterogeneous: a 403-ing WAF, two distinct JS-rendered stacks, and eight
unexamined sites. Fetching needs a per-AMC adapter regardless of what the
workbooks turn out to look like.

Design assumption: **adapter per AMC for fetch; defer the parser decision to
Phase A.** If Phase A finds SEBI-mandated layout uniformity, collapse the
parsers behind one config-driven implementation and keep the fetch adapters.

---

## 1. Scope

**In scope — 10 AMCs by AUM:** HDFC, SBI, ICICI Prudential, Nippon, Kotak,
Aditya Birla Sun Life, UTI, Axis, Mirae, DSP.

Everything outside stays `synthetic_estimated`, and commodity/international FoFs
stay `not_modellable` regardless of AMC (they have no defensible Indian-equity
portfolio — see commits `80831a6`, `3a7fd3f`).

### 1.1 Coverage estimate — portfolio_kt.pdf

Computed against the live 17 holdings:

| Outcome | Funds | Share |
|---|---|---|
| **Real AMFI data** (in-scope AMC) | **10** | **59%** |
| Stays synthetic (AMC out of scope) | 4 | 24% |
| Not modellable (commodity / international) | 3 | 18% |

Of the 14 *modellable* funds, the 10 AMCs cover **71%**.

Real: 3× ICICI Prudential, 2× Aditya Birla SL, and one each of Axis, DSP, Kotak,
Mirae, UTI.
Out of scope: Franklin India ELSS, Bandhan Corporate Bond, Invesco India L&M,
Parag Parikh Flexi Cap.
Not modellable: HDFC Silver ETF FoF, Motilal Oswal Nasdaq 100 FoF, Franklin U.S.
Opportunities FoF.

Note HDFC is in scope but its only fund here is the silver FoF, so HDFC
contributes **0** real funds to this portfolio despite being a priority adapter.
Parag Parikh is a visible gap — a common holding from an out-of-scope AMC.

---

## 2. Phase A — layout discovery (prerequisite, do first)

Cannot be skipped; §0.3 means we have no layout facts.

**A1. Acquire samples.** Obtain ≥3 workbooks from ≥3 in-scope AMCs, most recent
month. Manual download in a browser is acceptable and expected — the goal is
layout facts, not automation yet. Commit them to `backend/tests/fixtures/amfi/`
(they are public regulatory filings).

**A2. Document each**, in `docs/AMFI_LAYOUTS.md`, one section per AMC:
header row index; exact column captions; whether one sheet = one scheme; sheet
naming; merged-cell usage; footnote/total rows and how they are identifiable;
how equity vs debt vs cash vs derivative rows are distinguished; ISIN column
presence; AMFI industry-classification column presence; where the disclosure date
lives; units of the value column (₹ lakhs vs crores).

**A3. Decide parser architecture** from A2, and record the decision with
evidence. Only then proceed to Phase B.

**A4. Solve acquisition per AMC.** For each of the 10, determine and record
whether the workbook is reachable by: direct link, an XHR/JSON endpoint the page
calls, a form POST, or only via a headless browser. Record whether past months
are addressable or only the current one — **archive availability is unverified
and must not be assumed.**

Exit criteria: ≥3 layouts documented, acquisition path known for ≥5 AMCs, parser
architecture decided in writing.

---

## 3. Parser architecture

```
crawler/
  registry.py          AMC → adapter mapping, scheme-code ↔ ISIN table
  adapters/
    base.py            AMCAdapter ABC
    hdfc.py  sbi.py  icici.py  nippon.py  kotak.py
    absl.py  uti.py   axis.py   mirae.py  dsp.py
  parse/
    workbook.py        shared sheet→rows extraction
    normalize.py       rows → canonical constituent dicts
  validate.py          the gates in §4
  ingest.py            run orchestration, idempotency, supersede
```

### 3.1 Adapter interface

```
class AMCAdapter(ABC):
    amc_code: str
    amc_name: str

    def discover(period: YearMonth) -> list[DiscoveredFile]
        # locate workbook(s) for the period. Raises AcquisitionError.
        # DiscoveredFile: url, period, sha256(after fetch), content_type, discovered_via

    def fetch(f: DiscoveredFile) -> bytes
        # bytes only. No parsing. Retries/backoff live here.

    def sheets(raw: bytes) -> Iterable[SheetRef]
        # split workbook into per-scheme sheets

    def parse_sheet(s: SheetRef) -> ParsedSheet
        # ParsedSheet: scheme_name, scheme_code|None, disclosure_date,
        #              rows[], units, source_sheet_name
```

Adapters return **parsed but unvalidated** output. They must never write to the
database — `ingest.py` writes, and only after §4 passes. This keeps the "parser
was wrong" failure mode away from the data.

### 3.2 Joining to our holdings

Join on **ISIN**, never on fuzzy names — CLAUDE.md §2.3. Two joins exist and
must not be conflated:

- **Scheme identity:** disclosed scheme → our `holdings.isin` (the fund's ISIN),
  resolved via `amfi_instruments`. If unresolvable → that sheet is skipped, not
  guessed.
- **Constituent identity:** each holding row's ISIN → `underlying_isin`. Rows
  without a valid ISIN are dropped and counted; if they exceed the §4 threshold
  the whole sheet fails.

AMFI industry classification, where present, populates `underlying_sector`
directly — replacing `sector_mapper` keyword guessing for real rows.

---

## 4. Validation gates — the critical section

A parser that silently misreads a workbook and writes garbage tagged
`source='amfi_disclosure'` recreates the Phase 1 problem **with the label
inverted**: fabricated data asserting it is real. That is strictly worse than
the synthetic data we started with, because the disclosure banner would go
quiet.

Gates run per sheet, after parsing, before any write.

| # | Gate | Condition | On failure |
|---|---|---|---|
| G1 | Weight sum | `95.0 ≤ Σ weight_pct ≤ 105.0` | reject sheet |
| G2 | ISIN format | ≥95% of equity rows match `^INE[0-9A-Z]{9}$`; underlying ISINs unique | reject sheet |
| G3 | Row count | `5 ≤ rows ≤ 2000` | reject sheet |
| G4 | Disclosure date | present, parseable, within 95 days, not future | reject sheet |
| G5 | Scheme identity | resolves to a known scheme ISIN | reject sheet |
| G6 | Weight sanity | every row `0 < w ≤ 100`; no NaN/negative | reject sheet |
| G7 | Non-degenerate | ≥3 distinct underlying ISINs; not all weights identical | reject sheet |
| G8 | Delta guard | vs last accepted month: ≥30% ISIN overlap **or** flagged for review | quarantine, do not publish |

**Rules, non-negotiable:**

1. **Any gate failure → that scheme becomes `data_pending`.** Never fall back to
   a template. Never write a partial sheet. Never publish a fund at
   `source='amfi_disclosure'` that did not pass every gate.
2. **Sheet-level atomicity.** A scheme's constituents are written whole or not at
   all, inside one transaction.
3. **Failure is loud but non-fatal.** One bad sheet fails that scheme only; the
   run continues and reports.
4. **Gates are not tunable per AMC.** If an AMC needs looser gates, the adapter
   is wrong — fix the adapter.
5. **G1 tolerance is deliberately tight.** Disclosures include cash/derivatives;
   if a sheet legitimately sums outside 95–105 the adapter is dropping row
   classes, which is precisely what the gate is for.

Every rejection is persisted with scheme, gate, observed value, and workbook
sha256 — a rejection nobody can inspect is a silent failure.

---

## 5. Schema changes

### 5.1 `fund_constituents` — add

| Column | Type | Purpose |
|---|---|---|
| `amc_code` | TEXT | owning AMC |
| `source_url` | TEXT | exact workbook URL |
| `source_sha256` | TEXT | workbook content hash |
| `source_sheet` | TEXT | sheet name within the workbook |
| `ingest_run_id` | TEXT | FK → `ingest_runs.id` |
| `superseded_at` | DATETIME NULL | set when a later disclosure replaces this row |

`source` gains `amfi_disclosure` alongside `synthetic_estimated`,
`unknown_legacy`, `not_modellable`. `disclosure_date` already exists and becomes
mandatory for `amfi_disclosure` rows.

Uniqueness becomes `(scheme_code, underlying_isin, disclosure_date, source)`.

### 5.2 New — `ingest_runs`

`id, started_at, finished_at, period, amc_code, status, files_discovered,
sheets_parsed, sheets_accepted, sheets_rejected, schemes_written, error_summary`

### 5.3 New — `ingest_rejections`

`id, run_id, amc_code, scheme_name, scheme_code, gate, observed, expected,
source_url, source_sha256, created_at`

Migration follows the `_ensure_source_column()` pattern already proven in
production: additive, idempotent, `ALTER TABLE` guarded by `PRAGMA table_info`.
Existing rows keep `source='synthetic_estimated'` and get NULL provenance —
never backfilled to look real.

---

## 6. Scheduling

Cron on this box. **No Celery** — one job, once a day, on one server.

```
30 1 * * *  cd /opt/wlthos/backend && venv/bin/python scripts/sync_amfi.py --period current >> /var/log/wealthos-amfi.log 2>&1
```

01:30 UTC = 07:00 IST. Large AMCs typically file by the 8th; the brief's guidance
to start on the 12th and re-scan for late filers is honoured by running **daily
all month** and letting idempotency (§7) make repeat runs free. A fund that files
late is picked up the next morning with no special handling.

Debt schemes disclose fortnightly; the same daily run collects them — cadence is
a property of the source, not the schedule.

Manual: `--amc icici`, `--period 2026-07`, `--dry-run` (parse + validate, write
nothing — the primary tool for adapter development).

---

## 7. Idempotency, re-runs, supersession

- **Content-addressed.** Fetched workbooks are hashed; a workbook whose sha256
  already exists for that `(amc, period)` is skipped before parsing. Re-running
  an unchanged month is nearly free.
- **Re-parse on adapter change.** `--force-reparse` bypasses the hash skip; the
  adapter version is recorded so a fixed parser can be replayed over stored
  workbooks without refetching.
- **Supersession, not deletion.** A newer `disclosure_date` for a scheme sets
  `superseded_at` on the prior rows; reads filter `superseded_at IS NULL`.
  History is retained — required by CLAUDE.md §2.4 traceability, and the only way
  to explain why a look-through changed between two dates.
- **Real beats modelled, never the reverse.** Accepted `amfi_disclosure` rows
  supersede `synthetic_estimated` rows for that scheme. A synthetic row must
  **never** supersede a real one; if a later run produces only synthetic output
  for a scheme that already has real data, the real data stands and the run
  reports it.

Determinism: same workbook + same adapter version → identical rows, per
CLAUDE.md §2.1.

---

## 8. Incremental rollout

Ship adapter by adapter. Each is independently valuable and independently
revertible.

1. **ICICI Prudential first** — 3 of 17 funds here, the largest single gain.
2. Aditya Birla SL (2 funds), then Axis, DSP, Kotak, Mirae, UTI (1 each).
3. SBI, Nippon, HDFC — 0 funds in this portfolio, but needed for other clients.

As each lands, `funds_real_count` climbs and `funds_synthetic_count` falls. The
existing UI needs **no change** — it already reads those counts:

- The banner already renders "N of M funds use modelled constituents" and names
  them, so it narrows automatically to only the funds still modelled.
- `lookthrough_depth` already returns `estimated` / `partial_estimated` and only
  reports `full` when `funds_synthetic_count == 0` — the green badge becomes
  reachable for the first time when an entire portfolio is covered.
- The `(ESTIMATED)` suffix on the position count clears itself.

This was the point of building disclosure before real data: the honesty
machinery is already in place and needs nothing at rollout.

Expected trajectory for `portfolio_kt.pdf`: `0/17 → 3/17` (ICICI) `→ 5/17`
(ABSL) `→ 10/17` (all ten AMCs). It will never reach 17/17 — 4 funds are
out-of-scope AMCs and 3 are legitimately un-modellable. **Plan for a permanent
mixed state**; a portfolio that is fully real is the exception, not the goal.

---

## 9. Failure handling and alerting

| Condition | Handling |
|---|---|
| Adapter `discover` fails | log, mark AMC failed for the run, continue others |
| HTTP 403 / WAF (HDFC today) | 3 retries, exponential backoff, then fail that AMC — do **not** rotate UA or evade blocks |
| Workbook unparseable | reject all its sheets, record with sha256, keep the file for inspection |
| Gate failure | scheme → `data_pending`, row in `ingest_rejections` |
| Whole AMC yields 0 accepted schemes | **alert** — usually a site redesign |
| Coverage regression (`funds_real_count` falls) | **alert** — the one condition that silently degrades user-facing truth |

Alerting reuses `email_service.py` (already wired for signup alerts). Daily
summary only on change or failure; no mail on a clean no-op run.

**Never evade blocking.** If an AMC blocks automated access, that adapter stops
and the funds stay `synthetic_estimated`, correctly labelled. Scraping around a
WAF risks the IP and, for a regulated-data product, the relationship. HDFC's 403
is a business conversation, not an engineering problem.

Rate limiting: ≥2s between requests to one AMC, ≤1 concurrent request per AMC,
identifying User-Agent. This is a once-daily job — there is no reason to be
aggressive.

---

## 10. Definition of done

- ≥3 layouts documented in `docs/AMFI_LAYOUTS.md` from real workbooks
- ≥1 adapter in production with all §4 gates enforced
- `funds_real_count > 0` on `portfolio_kt.pdf`
- Banner narrows to name only the still-modelled funds
- A deliberately corrupted fixture is **rejected** by the gates and lands in
  `ingest_rejections` — proving the gates fire before anything reaches a user
- Re-running a period writes nothing new and takes seconds

The last two matter most. A crawler that ingests real data is worth little if it
cannot prove it will refuse bad data.

---

## 11. Open questions

1. **Past-month archives** — unverified for all 10 AMCs. If only the current
   month is retrievable, history accrues forward from launch and backfill is
   impossible. Resolve in Phase A4 before promising any time-series feature.
2. **HDFC's 403** — needs a decision: headless browser (fragile, arguably
   adversarial), an official data agreement, or accept HDFC stays synthetic.
3. **Headless browser dependency** — UTI and Mirae are client-rendered. If ≥2 of
   10 need Playwright, that is a real operational dependency on this box and
   should be an explicit decision, not a quiet import.
4. **Units** — ₹ lakhs vs crores varies by AMC and is a silent 100× error class.
   Add a gate once Phase A establishes how units are declared.
5. **Parag Parikh** is out of scope but commonly held. Reconsider the top-10 cut
   against actual client portfolios rather than industry AUM.
