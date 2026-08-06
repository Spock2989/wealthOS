# AMFI disclosure fixtures — Phase A evidence

Real monthly portfolio disclosures, downloaded 2026-08-06. Public regulatory
filings. These are the evidence base for `docs/AMFI_LAYOUTS.md` — keep them so
its claims stay reproducible and so parser work can start without re-fetching.

| File | AMC | Source |
|---|---|---|
| `nippon_monthly_2026-06.xls` | Nippon | `mf.nipponindiaim.com/InvestorServices/FactsheetsDocuments/NIMF-MONTHLY-PORTFOLIO-30-Jun-26.xls` |
| `nippon_monthly_2026-05.xls` | Nippon | same path, `…-31-May-26.xls` |
| `sbi_all_schemes_2026-04.xlsx` | SBI | `sbimf.com/docs/default-source/scheme-portfolios/all-schemes-monthly-portfolio---as-on-30th-april-2026.xlsx` |
| `mirae_mamcf_2026-06.xlsx` | Mirae | `miraeassetmf.co.in/docs/default-source/portfolios/mamcf-june2026.xlsx` |
| `dsp_month_end_2013-09.zip` | DSP | hashed URL under `dspim.com/media/pages/mandatory-disclosures/portfolio-disclosures/` |

## Traps these fixtures exist to pin down

- **Both `nippon_*.xls` are XLSX**, not XLS. `openpyxl` rejects them on
  *extension alone* — load from `BytesIO`, sniff magic bytes (`PK\x03\x04`).
- **`dsp_month_end_2013-09.zip`** is served from a link ending `.xlsx` but is a
  ZIP containing legacy `.xls` members. Renamed here to reflect reality. It is
  **Sept 2013** — DSP's link list is unordered and spans 2013→2026; period must
  come from link text, never position.
- **Units differ by AMC.** Summing the pct column over ISIN rows:
  Nippon `0.9869` (fraction), Mirae `0.9863` (fraction), SBI `96.17` (percentage).
- **`mirae_mamcf_2026-06.xlsx` may be irreplaceable** — Mirae appeared to expose
  only the current month, so this may be the only copy we can obtain.
