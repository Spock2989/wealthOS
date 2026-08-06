# AMFI Disclosure Layouts — Phase A Findings

**Date:** 2026-08-06
**Status:** 4 of 10 AMCs documented from real workbooks. 6 unresolved.
**Method:** curl from the production box (Indian IP, correct vantage) for
reachability; headless Chromium (Playwright) locally for JS-rendered sites.
No WAF evasion attempted.

Exit criterion from the spec was "≥3 layouts documented from real workbooks" —
**met, with 4**.

---

## 1. Acquisition results — all 10

| AMC | curl (from prod) | Headless browser | Files obtained | Structure |
|---|---|---|---|---|
| **Nippon** | ✅ 200, **336 direct links** | not needed | ✅ yes | 1 workbook, 108 sheets |
| **SBI** | 200, 0 links | ✅ **25 files** | ✅ yes | 1 workbook, 124 sheets |
| **Mirae** | 200, 0 links | ✅ **10 files** | ✅ yes | **1 file per scheme** |
| **DSP** | ❌ 403 | ✅ **25 files** | ✅ yes | **ZIP of .xls files** |
| **HDFC** | ❌ 403 | ❌ **403** | ✗ | **blocked** |
| **ICICI Pru** | ❌ **404** | — | ✗ | **AMFI's link is dead** |
| **Kotak** | 200, 0 links | 200, 0 links | ✗ | JS/POST download |
| **Aditya Birla SL** | 200, 0 links | 200, 0 links | ✗ | JS/POST download |
| **UTI** | 200, 0 links | 200, 0 links | ✗ | JS/POST download |
| **Axis** | 200, 0 links | 200, 0 links | ✗ | JS/POST download (Next.js) |

**4 obtainable, 1 hard-blocked, 1 dead link, 4 need deeper interaction.**

Notes:
- **DSP 403s to curl but serves a headless browser** — so a 403 alone does not
  mean "blocked", and the spec's §9 rule (3 retries then give up) would have
  wrongly written DSP off. Probe with a browser before declaring an AMC blocked.
- **HDFC 403s a real headless Chromium too.** Per the standing instruction, this
  is recorded as blocked and left alone. HDFC funds stay `synthetic_estimated`.
- **ICICI Prudential's URL in AMFI's own directory returns 404**, as do
  `/news-and-media/downloads` and `/downloads`. AMFI's directory is stale. This
  matters because ICICI is the **single largest real-data gain** for
  `portfolio_kt.pdf` (3 of 17 funds). Finding the live URL is the highest-value
  remaining acquisition task.
- The 4 "JS/POST" AMCs render fine but expose no `<a href>` to a file — the
  download is triggered by script. None showed a month `<select>`. Resolving
  these needs network-request interception (watch for the XHR the button fires),
  not more scraping.

### 1.1 Is there an AMFI-hosted copy for blocked AMCs?

**No.** Checked explicitly:

- Zero `amfiindia.com`-hosted `.xls/.xlsx/.zip` links anywhere in the disclosure
  page payload.
- `/modules/PortfolioDisclosure`, `/nav-history-download`,
  `/research-information/other-data/portfolio-disclosure` → all **404**.
- `/research-information/amfi-monthly` → 200, but contains **no** portfolio or
  holdings content (it is AUM/industry data).

AMFI publishes **links only**. There is no fallback copy. If an AMC blocks us,
those funds stay modelled — there is no second source.

---

## 2. Layouts — verified from real workbooks

### 2.1 Nippon India — `NIMF-MONTHLY-PORTFOLIO-30-Jun-26.xls`

Direct link, no browser needed. **1,354,789 bytes.**

> ⚠️ **The extension lies.** The file is named `.xls` but the magic bytes are
> `PK\x03\x04` with `[Content_Types].xml` — it is **XLSX**. `openpyxl` rejects it
> on *extension alone* (`_validate_archive` checks `os.path.splitext`), so a path
> load raises `InvalidFileException`. **Load from `BytesIO`, never a path**, and
> sniff magic bytes rather than trusting the name.

- **108 sheets.** Sheet 1 = `Index`, mapping 2-char code → scheme name (col A, col B).
- **One sheet per scheme**, named by the 2-char code (`TS`, `EA`, `IP`, …).
- Per-scheme sheet:
  - `r1`: col A = AMC scheme code (`RLMF046`), col B = scheme name (merged B1:D1)
  - `r2`: `Monthly Portfolio Statement as on June 30,2026` — **disclosure date**
    (note: no space after the comma)
  - **`r4` = HEADER ROW**
  - `r5`+: data and section markers

| Col | Header | Content |
|---|---|---|
| A | *(none)* | internal security code (`IBCL05`) |
| **B** | `ISIN` | **ISIN** |
| C | `Name of the Instrument` | name |
| D | `Industry / Rating` | industry (equity) **or credit rating** (debt) |
| E | `Quantity` | quantity |
| F | `Market/Fair Value\n( Rs. in Lacs)` | value, **₹ lakhs** |
| **G** | `% to NAV` | **FRACTION — see §3** |
| H | `YIELD` | yield (debt) |

- **Section markers** are rows with text in col C and no ISIN in col B:
  `Equity & Equity related` → `(a) Listed / awaiting listing on Stock Exchanges`
  → `Subtotal` → `(b) UNLISTED` → `Subtotal` → `Total` →
  `Money Market Instruments` → `Triparty Repo/ Reverse Repo Instrument` →
  `Triparty Repo` → `Total` → `OTHERS` → `Cash Margin - CCIL` → `Total` →
  `Net Current Assets` → **`GRAND TOTAL`** (= 1.0)
- `NIL` appears as a **string** in the pct column for empty sections — must not
  be coerced to a number.
- Merged cells: few and confined to titles/footers (`B1:D1`, `B2:D2`, `C87:H87`).
- **Footnote block** after `GRAND TOTAL`: sections `C.`–`F.` (hedging, options,
  swaps), `Additional notes`, NAV-per-unit table, and risk-o-meter rows. All
  must be excluded — they sit *below* `GRAND TOTAL`, which is a reliable
  terminator.
- **Debt sheets use the same structure**, but col D holds a rating
  (`CRISIL AAA`, `SOVEREIGN`) and section markers are `Debt Instruments`,
  `Floating Rate Note`, `Government Securities`.
- **Month-to-month:** header row and columns are **stable**; the *sheet set is
  not* — June had 108 sheets, May 109 (`HG` present in May, absent in June). Do
  not cache the sheet list.

### 2.2 SBI — `all-schemes-monthly-portfolio---as-on-30th-april-2026.xlsx`

Headless browser required. **2,602,627 bytes.**

- **124 sheets.** Sheet 1 = `Index` with a real header at `r2`:
  `Scheme Code | Scheme Short code | Scheme Name` — a **3-column mapping**,
  better than Nippon's 2-column index.
- **One sheet per scheme**, named by short code (`SLTEF` = SBI ELSS Tax Saver).
- Per-scheme sheet:
  - `r2`: col C `SBI Mutual Fund`, col D scheme code (`018`)
  - `r3`: `SCHEME NAME :` / scheme name
  - `r4`: `PORTFOLIO STATEMENT AS ON :` / **date as a real `datetime`** (not text)
  - **`r6` = HEADER ROW** (≠ Nippon's r4)

| Col | Header | Content |
|---|---|---|
| B | *(none)* | internal code (`100012`) |
| C | `Name of the Instrument / Issuer` | name |
| **D** | `ISIN` | **ISIN** (≠ Nippon's col B) |
| E | `Rating / Industry^` | **order reversed** vs Nippon |
| F | `Quantity` | quantity |
| G | `Market value\n(Rs. in Lakhs)` | value, ₹ lakhs |
| **H** | `% to AUM` | **PERCENTAGE — see §3** |
| I–K | `YTM %`, `YTC % ##`, `Notes & Symbols` | |

- Section markers: `EQUITY & EQUITY RELATED` → `a) Listed/awaiting listing…` →
  `Equity Shares`.
- `max_column` reports **256** — a large block of trailing empty columns. Do not
  size the parser off `max_column`.
- File format **alternates between `.xls` and `.xlsx` across months** in the same
  directory (Feb-2026 is `.xls`, Apr-2026 is `.xlsx`). Sniff, never assume.

### 2.3 Mirae Asset — `mamcf-june2026.xlsx`

Headless browser required. **364,723 bytes.**

- **Fundamentally different: one file per scheme per month**, not one workbook.
  Filename is `<schemecode>-<month><year>.xlsx` (`mamcf-june2026.xlsx`).
- **1 sheet**, named with the scheme short code (`MAMCF`).
- `r1` scheme name; `r3` scheme category; `r5` scheme name + code (`MI014`) +
  **date as `datetime`**; `r7` `Monthly Portfolio Statement…`
- **`r8` = HEADER ROW** (≠ Nippon r4, ≠ SBI r6)

| Col | Header | Content |
|---|---|---|
| B | `Name of the Instrument` | name |
| **C** | `ISIN` | **ISIN** |
| D | `Industry ^/ Rating` | industry |
| E | `Quantity` | quantity |
| F | `Market/Fair Value \n(Rs. in Lakhs)` | value, ₹ lakhs |
| **G** | `% to Net Assets` | **FRACTION — see §3** |
| H | `YTM` | |

- Section markers: `EQUITY & EQUITY RELATED` → `(a) Listed / awaiting listing…`
- Percentages carry absurd precision (`0.0367085319272`) — round on write, and
  never compare for equality.
- **Only current-month files were exposed** (all 10 were `june2026`). See §4.

### 2.4 DSP — ZIP archives

Headless browser required (curl 403s). Sample **138,749 bytes**.

- URLs are **opaque and hashed**:
  `/media/pages/mandatory-disclosures/portfolio-disclosures/001294169e-1757771557/month_end_portfolio_…`
  — no derivable pattern, so links **must be scraped every run**.
- The download is a **ZIP whose members are `.xls` files**, despite the link
  ending `.xlsx`:
  ```
  Month_end_portfolio_disclosure_Sept2013/Factsheet _Close_Ended_Sep13.xls
  Month_end_portfolio_disclosure_Sept2013/Factsheet _Open_Ended_Sep13.xls
  ```
  Note the space in `Factsheet _Open_Ended_Sep13.xls`.
- Open-ended and close-ended schemes are **split across separate members**.
- The link list mixes `month_end_portfolio`, `half-yearly-portfolio` and
  `dsp-isin-debt-portfolio` **and spans 2013→2026** with no ordering — the
  sample retrieved was **Sept 2013**. Period must be selected from the link
  text/metadata, never by position.
- Inner-layout documentation is **incomplete** — the members are true legacy
  `.xls` (BIFF), which needs `xlrd`, not installed. Deferred.

---

## 3. 🚨 The unit convention is not consistent across AMCs

Same regulator, same disclosure month, measured by summing the `%` column over
rows with a valid ISIN:

| AMC | Column header | ISIN rows | Sum | Convention |
|---|---|---|---|---|
| Nippon | `% to NAV` | 64 | **0.9869** | **fraction** — ×100 needed |
| Mirae | `% to Net Assets` | 66 | **0.9863** | **fraction** — ×100 needed |
| SBI | `% to AUM` | 74 | **96.1700** | **percentage** — use as-is |

**Three AMCs, three different header captions, two incompatible conventions, and
none of them declares its units.** A single generic parser applying one
convention is silently 100× wrong on the others — a portfolio reported as 0.99%
invested, or 9,869%.

Gate **G1 (weight sum within 95–105)** catches both directions. This is the
strongest evidence so far that the validation gates are load-bearing rather than
ceremonial, and that **unit handling must be per-AMC configuration, never
inferred from the header text.**

---

## 4. Question 1 — are past-month archives retrievable?

**Mixed. Mostly yes, with one important exception.**

| AMC | Archive depth | Evidence |
|---|---|---|
| **Nippon** | ✅ **2013 → 2026** | 335 distinct file links on one page |
| **SBI** | ✅ **2023 → 2026** | files for Feb-2023, Apr-2024, Apr-2025, Apr-2026 |
| **DSP** | ✅ **2013 → 2026** | link list spans them; sample retrieved was Sept-2013 |
| **Mirae** | ⚠️ **current month only** | all 10 exposed files were `june2026` |
| HDFC, ICICI, Kotak, ABSL, UTI, Axis | unknown | not reachable yet |

**Answer: look-through history does NOT only accrue forward.** For Nippon, SBI
and DSP, a decade of monthly disclosures is retrievable today, so historical
back-fill and genuine time-series look-through are feasible for those AMCs.

Caveats worth planning around:
- Mirae appears to expose only the current month. If that holds, Mirae history
  accrues forward from first run — **so start collecting now**, since each
  missed month may be unrecoverable.
- Nippon's archive filenames are wildly inconsistent — `Debt-Portfolio-June-21.xls`,
  `Debt-Portfolio-as-at-15-07-2021.xls`, `Debt-Portfolo-31st-July-2021.xls`
  (typo), `FORNIGHTLY-PORTFOLIO-JUNE-23.xls` (typo), plus the pre-rebrand
  `Reliance-Monthly-Portfolios-*`. Period **must** be parsed from link text with
  a tolerant matcher, and unparseable names skipped rather than guessed.

---

## 5. Question 2 — operational cost of Playwright on the prod box

### Measured

| Item | Size |
|---|---|
| `ms-playwright` browser cache (Chromium headless shell) | **580 MB** |
| `playwright` Python package | **136 MB** |
| **Total install footprint** | **~716 MB** |
| Download | 98.8 MB compressed |

### The box

```
RAM:   1968 MB total | 1191 MB available
Swap:  NONE
CPU:   1 vCPU
Disk:  48 GB, 41 GB free
API:   186 MB resident (wealthos.service, 2 uvicorn workers)
```

### Assessment — **do not install on this box as-is**

- **Disk is fine.** 716 MB against 41 GB free is a non-issue.
- **Memory is not.** Headless Chromium commonly peaks at 300–700 MB for a single
  page, more on script-heavy sites. Against **1191 MB available with zero swap**,
  a crawl running beside the API has little headroom.
- **The failure mode is the problem.** With no swap, memory pressure goes
  straight to the OOM killer, which targets the largest RSS — that is Chromium,
  but under a spike it can take `wealthos.service` instead. **A crawler bug would
  take the API down.** That is a poor trade for a nightly job.
- **1 vCPU** means browser rendering directly contends with request serving.

### Options, in preference order

1. **Add swap (2–4 GB) before installing.** Cheapest fix; turns a hard OOM into
   degraded performance. Disk is available. *Recommended minimum.*
2. **Avoid Playwright entirely for now.** Nippon needs only plain HTTP, and it is
   in scope. Ship the Nippon adapter with `httpx`, defer browser-dependent AMCs.
   Zero new operational risk, real coverage gain.
3. **Run the crawler off-box** (a laptop, CI runner, or a short-lived droplet)
   and ship results to the API. Best isolation; more moving parts.
4. **Resize the droplet** to 4 GB. Simplest robust answer if the budget allows.

**Recommendation:** do (2) now — Nippon is reachable without a browser — and
require (1) before any browser-dependent adapter runs on this host. 3 of the 4
obtainable AMCs currently need a browser, so this decision blocks most of the
rollout and should be made early.

---

## 6. Architecture verdict — adapter per AMC, confirmed

The spec deferred this pending evidence. The evidence is now in:

| Dimension | Nippon | SBI | Mirae | DSP |
|---|---|---|---|---|
| Acquisition | direct link | browser | browser | browser |
| Packaging | 1 workbook | 1 workbook | **1 file/scheme** | **ZIP of .xls** |
| Header row | **4** | **6** | **8** | ? |
| ISIN column | **B** | **D** | **C** | ? |
| Industry/Rating order | `Industry / Rating` | `Rating / Industry^` | `Industry ^/ Rating` | ? |
| Pct header | `% to NAV` | `% to AUM` | `% to Net Assets` | ? |
| **Pct units** | **fraction** | **percentage** | **fraction** | ? |
| Date location | r2 text | r4 datetime | r5 datetime | ? |
| File format | xlsx named `.xls` | `.xls`/`.xlsx` varies | `.xlsx` | zip of `.xls` |

No two agree on header row, ISIN column, or percentage caption — and they
disagree on **units**, which is a silent-corruption axis rather than a cosmetic
one. **A genuine adapter per AMC is required for both fetch and parse.** A
config-driven generic parser is not viable.

The shared layer is narrow and worth keeping: magic-byte sniffing, BytesIO
loading, section-marker/terminator handling, ISIN validation, and the §4 gates.

---

## 7. Corrections this forces on AMFI_CRAWLER_SPEC.md

1. **G2 ISIN regex is wrong.** `^INE[0-9A-Z]{9}$` **rejects 26.4% of real
   ISINs** — measured on 1,856 distinct ISINs from the Nippon workbook: 490
   rejected, every government security (`IN0…`), SDL (`IN1/IN2/IN3…`), T-bill,
   and mutual-fund unit (`INF…`). Corrected to **`^IN[A-Z0-9]{10}$`**, which
   matches 1,856/1,856.
2. **Units must be per-adapter configuration** with an explicit
   `pct_is_fraction: bool`, never inferred from the header caption (§3).
3. **A 403 does not mean blocked** — DSP 403s curl and serves a browser. Probe
   with a browser before recording an AMC as blocked (§1).
4. **Never load workbooks by path** — openpyxl rejects on extension, and
   extensions lie. Sniff magic bytes, load from `BytesIO` (§2.1).
5. **`funds_without_constituents` handling for ICICI** — AMFI's own directory
   link is dead, so URL discovery cannot rely on the AMFI index alone.
6. **Playwright is not free on this host** — see §5; it gates most of the
   rollout.

---

## 8. Recommended next steps

1. **Nippon adapter first**, not ICICI. It needs no browser, has a decade of
   archive, and is fully documented here. It proves the pipeline end to end at
   zero operational risk. *(It contributes 0 funds to `portfolio_kt.pdf` — the
   value is a proven pipeline, not coverage.)*
2. **Find ICICI's live URL.** 3 of 17 funds — the largest single coverage gain.
3. **Decide the Playwright/swap question** (§5) — it blocks SBI, Mirae and DSP.
4. **Intercept the download XHR** on Kotak, ABSL, UTI and Axis to learn their
   real endpoints.
5. **Leave HDFC blocked** and honestly labelled.

Sample workbooks are in the session scratchpad, not committed — they are several
MB each. Re-fetch with the URLs recorded here, or commit trimmed fixtures when
the first adapter is built.
