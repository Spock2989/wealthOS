"""
WealthOS — AMFI constituent ingestion: normalisation, scheme identity, gates.

This module is the safety layer. Adapters parse; nothing they produce reaches
the database until it clears every gate here.

Why the gates exist (CLAUDE.md 2.4, and docs/STATE.md): the system previously
served modelled fund constituents that were indistinguishable from real AMFI
disclosures. A parser that silently misreads a workbook and writes garbage
tagged source='amfi_disclosure' recreates that failure with the label inverted —
fabricated data asserting it is real, with the estimated-data banner switched
off. That is strictly worse than the synthetic data it replaces.

Rule: on ANY gate failure the scheme is reported data_pending. Never a template,
never a partial write.

methodology_version: amfi_ingest@1.0.0
"""

from __future__ import annotations

import re
import sqlite3
import collections
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Iterable, Optional

SOURCE_AMFI_DISCLOSURE = "amfi_disclosure"

# Indian ISINs are IN + 10 alphanumerics. NOT ^INE...$ — that form rejects
# every government security (IN0…), SDL (IN1/IN2/IN3…), T-bill and mutual fund
# unit (INF…). Measured against a real Nippon workbook, ^INE[0-9A-Z]{9}$
# rejected 490 of 1,856 distinct ISINs — 26.4%, i.e. every debt scheme.
ISIN_RE = re.compile(r"^IN[A-Z0-9]{10}$")

# Words that distinguish plans/options of the SAME underlying portfolio.
# Direct vs Regular and Growth vs IDCW share one pool of securities, so they
# must collapse to a single scheme identity and all map to the one disclosure.
_PLAN_NOISE = re.compile(
    r"\b(direct|regular|growth|idcw|dividend|payout|reinvest\w*|plan|option|scheme)\b"
)


def norm_scheme(name: str) -> str:
    """
    Normalise a scheme name so plan/option variants collapse together.

    Verified against production `amfi_instruments` (13,571 ISINs → 5,821
    distinct normalised names): 9 of 9 real disclosure scheme names resolved
    exactly, each to the 2–4 ISINs of its plan variants.
    """
    s = (name or "").lower()
    s = re.sub(r"\(.*?\)", " ", s)          # drop parenthetical notes
    s = re.sub(r"[^a-z0-9& ]", " ", s)
    s = _PLAN_NOISE.sub(" ", s)
    s = re.sub(r"\bfund\b", " ", s)
    return re.sub(r"\s+", " ", s).strip()


@dataclass
class Row:
    isin: str
    name: str
    industry: Optional[str]
    quantity: Optional[float]
    value: Optional[float]
    pct: float                      # ALWAYS 0–100 after adapter normalisation


@dataclass
class ParsedSheet:
    amc_code: str
    scheme_name: str
    disclosure_date: Optional[date]
    rows: list[Row]
    source_file: str
    source_sheet: str
    # Populated by gates / ingest
    scheme_isins: list[str] = field(default_factory=list)
    rejected: Optional[str] = None

    @property
    def weight_sum(self) -> float:
        return sum(r.pct for r in self.rows)


class SchemeResolver:
    """
    Resolve a disclosed scheme name to the ISINs of its plan variants.

    Strict by design: an ambiguous or absent match is a gate failure, not a
    best guess. CLAUDE.md 2.3 — ISIN is the key, name matching is fallback only,
    and here it is used solely to *find* ISINs, never to identify a security.
    """

    def __init__(self, db_path: str):
        conn = sqlite3.connect(db_path)
        try:
            rows = conn.execute(
                "SELECT isin, scheme_code, scheme_name FROM amfi_instruments "
                "WHERE isin IS NOT NULL AND isin != ''"
            ).fetchall()
        finally:
            conn.close()
        self._idx: dict[str, set[tuple[str, str]]] = collections.defaultdict(set)
        for isin, code, name in rows:
            self._idx[norm_scheme(name)].add((isin, str(code)))

    def resolve(self, scheme_name: str) -> list[tuple[str, str]]:
        """
        Exact normalised match only. Returns [] when unresolvable.

        Yields (fund_isin, amfi_scheme_code) pairs — the real AMFI scheme_code,
        not a locally invented one. Two reasons this matters:
        amfi_holdings_service.get_cached_constituents() looks constituents up BY
        scheme_code, so anything else simply would not join; and the table's
        unique key is (scheme_code, underlying_isin, disclosure_date), so each
        plan variant needs its own code to coexist.
        """
        return sorted(self._idx.get(norm_scheme(scheme_name), set()))


# ── Validation gates ────────────────────────────────────────────────
# G1 band. Deliberately 80–105, not 95–105.
#
# The sum is taken over rows carrying an ISIN. Cash, TREPS, repo and net
# current assets have no ISIN, so a fund holding 8% cash legitimately sums to
# ~92. Measured on real ICICI disclosures, a 95 floor rejected 23 valid schemes
# (91.07–94.39) — the gate was wrong, not the data.
#
# The band still does its job. The failure it exists to catch is the
# fraction-vs-percentage confusion, which produces sums near 0.99 or 9869 —
# both outside this band by two orders of magnitude. Widening the floor costs
# nothing against that failure mode and stops rejecting high-cash funds.
WEIGHT_MIN, WEIGHT_MAX = 80.0, 105.0
# A fund-of-fund legitimately holds ONE instrument: HDFC Silver ETF FoF is
# 100.09% a single HDFC Silver ETF unit. Requiring 3+ rows rejected that real
# disclosure and left the fund showing fabricated equities instead — the gate
# actively preserved the bug it was meant to prevent.
#
# G1 is the real protection against a truncated parse: grabbing only the first
# row or two of a real fund yields a sum of a few percent, far below the 80
# floor. A genuine single-holding FoF sums to ~100 and passes.
ROWS_MIN, ROWS_MAX = 1, 2000
MAX_DISCLOSURE_AGE_DAYS = 400          # allow historical back-fill
MIN_DISTINCT_ISINS = 1
ISIN_VALID_FRACTION = 0.95


def run_gates(sheet: ParsedSheet, resolver: SchemeResolver,
              today: Optional[date] = None) -> Optional[str]:
    """
    Return None when every gate passes, else a short reason string.

    Gates are NOT tunable per AMC. If an AMC appears to need looser gates, the
    adapter is wrong — fix the adapter.
    """
    today = today or date.today()
    rows = sheet.rows

    # G3 — plausible row count
    if not (ROWS_MIN <= len(rows) <= ROWS_MAX):
        return f"G3_row_count:{len(rows)}"

    # G2 — ISIN format. Duplicates are NOT an error and must not be rejected:
    # a security legitimately appears on several rows, e.g. ICICI ELSS lists
    # Tega Industries twice, 175,526 locked-in shares and 63,130 free, with the
    # sheet's own footnote explaining the split. Adapters aggregate duplicates;
    # G1 remains the backstop, since double-counting a whole section would push
    # the sum past 105 and fail there.
    valid = [r for r in rows if r.isin and ISIN_RE.match(r.isin)]
    if len(valid) / max(len(rows), 1) < ISIN_VALID_FRACTION:
        return f"G2_isin_format:{len(valid)}/{len(rows)}"
    isins = [r.isin for r in valid]
    worst = max(collections.Counter(isins).values()) if isins else 0
    if worst > 6:
        return f"G2_isin_repeated_{worst}x"      # implausible — likely a parse fault

    # G6 — weight sanity per row.
    # Upper bound is WEIGHT_MAX, not 100: a single position can legitimately
    # exceed 100% when the fund carries negative net current assets. HDFC
    # Silver ETF FoF holds 100.09% of one ETF against -0.39% net current
    # assets. Capping at 100 rejected that real disclosure.
    for r in rows:
        if r.pct is None or r.pct != r.pct:          # None or NaN
            return "G6_weight_nan"
        if not (0 < r.pct <= WEIGHT_MAX):
            return f"G6_weight_range:{r.pct}"

    # G1 — weight sum, AFTER the adapter's unit convention was applied.
    # This is the backstop for the 100x error class: measured on real files,
    # Nippon/Mirae/ICICI express the pct column as a fraction (sum ≈ 0.99)
    # while SBI/HDFC use a true percentage (sum ≈ 96). Same regulator, same
    # month, no declaration anywhere.
    s = sheet.weight_sum
    if not (WEIGHT_MIN <= s <= WEIGHT_MAX):
        return f"G1_weight_sum:{s:.4f}"

    # G7 — non-degenerate
    if len(set(isins)) < MIN_DISTINCT_ISINS:
        return f"G7_degenerate:{len(set(isins))}_distinct"
    if len(set(round(r.pct, 6) for r in rows)) == 1 and len(rows) > 3:
        return "G7_all_weights_identical"

    # G4 — disclosure date present, sane, not future
    d = sheet.disclosure_date
    if d is None:
        return "G4_no_disclosure_date"
    if d > today:
        return f"G4_future_date:{d}"
    if (today - d).days > MAX_DISCLOSURE_AGE_DAYS:
        return f"G4_stale:{d}"

    # G5 — scheme identity resolves to known ISINs
    isins_resolved = resolver.resolve(sheet.scheme_name)
    if not isins_resolved:
        return "G5_scheme_unresolved"
    sheet.scheme_isins = isins_resolved

    return None
