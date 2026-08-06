# WealthOS — What Is Real vs What Is Modelled

**As of:** 2026-08-05
**Reference portfolio:** `portfolio_kt.pdf` —
`f1bb14dc-f680-49ed-ba06-562538e971a9`, 17 holdings, ₹169,044.35

Read this before quoting any WealthOS number to a client or investor. The
system currently produces a mix of real computation over real data and real
computation over **modelled** data, and until commit `5bc3116` the UI did not
distinguish them.

---

## ✅ REAL — derived from the actual uploaded CAS

These come from holdings parsed out of the user's own statement. Deterministic,
reproducible, safe to quote.

| Output | Value for reference portfolio | Source |
|---|---|---|
| Holdings | 17 | parsed from CAS |
| ISINs | 17 distinct | parsed from CAS |
| Weights / allocation % | per holding | `current_value / total` |
| Total value | ₹169,044.35 | summed from CAS |
| **HHI** | **1184.0** (= 0.118) | `app/analytics/concentration.py` |
| **Neff** | **8.4** (10000 / 1184) | derived from HHI |
| Top-N concentration | top-5 weight | `concentration.py` |
| Asset-class split | equity 14 / debt 1 / alternate 1 / international 1 | parsed `asset_class` |
| Diversification score | 78.8 | `app/analytics/diversification.py` |

All verified directly against the prod analytics snapshot.

---

## ⚠️ SYNTHETIC — modelled, NOT from AMFI disclosures

**Every fund constituent in the system is modelled.** None of the 17 funds has
real AMFI portfolio data. All 381 `fund_constituents` rows were produced by
`generate_synthetic_portfolio()` — a hardcoded SEBI-mandate template drawn from
a shared pool of ~35 large-cap names — and written in a **3-second window** on
2026-05-27, which is generation, not 17 HTTP fetches.

Because the constituents are modelled, **everything computed on top of them is
modelled**, no matter how sound the maths:

| Output | Why it is not real |
|---|---|
| **Holdings X-Ray** — all underlying stock exposure | built entirely from modelled constituents |
| The ~247 "underlying positions" | modelled; a real look-through would differ |
| **Cross-fund overlap** ("×17 funds") | artifact of every fund drawing from one template pool. Before `80831a6`, a **silver ETF FoF and a Nasdaq feeder were both assigned HDFC Bank 8% / ICICI 6.5% / Reliance 6%** |
| **Fund-pair overlap matrix** | same cause |
| **Effective sector exposure** (post look-through) | rolled up from modelled stock sectors |
| **Effective market-cap split** | same |
| **All 20 scenarios + macro sensitivity matrix** | fed by sector exposure, which is modelled — and worse, currently fed the *scheme-category* label, not real sectors (see BROKEN) |

The maths is deterministic and correct. **The inputs are invented.** Treat every
figure in this table as illustrative only.

After `80831a6`, commodity/precious-metal FoFs and international feeders return
no constituents at all (shown as opaque) rather than a fabricated Indian
portfolio — for the reference portfolio that is 3 of 17 funds, leaving 14
modelled.

---

## ❌ BROKEN — known defects, root cause identified

### AI Memo returns 500
`/opt/wlthos/backend/.env` holds `sk-ant-api03-YOUR_ACTUAL_KEY_HERE` — a
28-char placeholder that was never replaced. The old `if not key` guard passed
on the truthy stub, so the SDK was called and returned a generic auth error.
Commit `5642cc3` makes the failure legible; **the key itself still needs to be
set by an operator.**

### Factor DNA overlap is a stub
`app/analytics/fund_overlap.py` matches against **5 hardcoded fund-name pairs**
(`KNOWN_OVERLAPS`, lines 5–11) — HDFC Mid-Cap/Mirae Emerging, Axis
Bluechip/ICICI Pru Bluechip, and 3 more. None of this portfolio's 17 funds
match, so it reports **Portfolio Overlap 0.0%**.

`duplicate_isin_count` counts repeated ISINs *in the raw holdings rows*, not
duplicate underlying stocks across funds — so it reports **0** while X-Ray shows
heavy overlap. Both verified in the prod snapshot: `0.0` and `0`.

Two independent overlap implementations disagree because only one does real
work. A third, `engines/factor_engine.py:factor_dna()`, is imported solely by
`engines/analytics_core.py` and appears unreachable from the live API.

### Sector card shows a scheme category, not a sector
The Overview/Exposures sector card reads `AnalyticsResult.sector_exposure`,
which sums **one label per fund** from `sector_mapper.classify_sector()`. That
function falls back to `"Diversified"` for any name containing a generic fund
word — so the card reads **"Diversified 54.9%"**, a scheme category, not a
sector.

Real look-through sectors already exist and are computed correctly
(`lookthrough.py:_aggregate_sector()`); the card was simply never wired to them.

**The scenario engine inherits this.** `engines/scenario_engine.py:606` has an
explicit shock keyed on the literal string `"Diversified"` — so a market shock
is applied uniformly across 54.9% of the portfolio as if it were one sector.

---

## ▶️ NEXT — the unblocker

**Build the AMFI constituents crawler + NAV history pipeline.**

This is the single dependency that converts most of the SYNTHETIC table into
REAL. Nothing else in the roadmap changes the honesty of the output as much,
and further analytics work on modelled constituents compounds the problem
rather than reducing it.

Two pieces:

1. **AMFI constituents crawler** — real monthly portfolio disclosures per
   scheme, replacing `generate_synthetic_portfolio()` as the primary path.
   Note AMFI appears to geo-restrict the server's IP; solving fetch access is
   part of the work. Provenance plumbing (`dffcb5a`) is already in place, so
   real rows will land tagged `amfi_live` and the estimated-data banner will
   switch itself off per fund as coverage arrives.

2. **NAV history pipeline** — real time series, which is the prerequisite for
   volatility, drawdown and correlation being measured rather than assumed.

Until then: X-Ray, overlap, effective sector exposure and all scenario outputs
are **illustrative, not analytical**, and must be labelled as such wherever
they appear.
