"""
WealthOS — Scenario × FRED macro context tests.

Covers:
  1. build_macro_context: correct mapping from MacroSnapshot dict
  2. build_macro_context: empty / None snapshot → graceful degradation
  3. enrich_with_macro_context: adds macro_driver_context to all results
  4. enrich_with_macro_context: correct implied level for multiplier scenarios
  5. enrich_with_macro_context: correct implied level for additive scenarios
  6. enrich_with_macro_context: None macro_context → null driver fields, no crash
  7. enrich_with_macro_context: unknown scenario_id → macro_driver_context is None
  8. Determinism: same snapshot → byte-identical enriched output (5 runs)
  9. Golden pin: oil_spike_40pct with known WTI baseline
 10. enrich_with_macro_context: empty results list → returns empty list
"""
from __future__ import annotations

import copy
import hashlib
import json
from typing import Any, Dict, List

import pytest

from engines.scenario_engine import (
    BASELINE_SERIES,
    SCENARIO_MACRO_DRIVERS,
    build_macro_context,
    enrich_with_macro_context,
    run_scenarios,
)

# ── Fixtures ──────────────────────────────────────────────────


def _make_fred_snapshot(overrides: Dict[str, Any] = None) -> Dict:
    """
    Minimal MacroSnapshot.to_dict() structure with realistic values.
    """
    default_values = {
        "DCOILWTICO":       78.50,
        "DCOILBRENTEU":     82.10,
        "DEXINUS":          83.40,
        "VIXCLS":           18.20,
        "INTDSRINM193N":     6.50,
        "DGS10":             4.30,
        "T10Y2Y":           -0.20,
        "INDCPIALLMINMEI":   5.10,
        "GOLDAMGBD228NLBM": 2320.00,
        "BAMLH0A0HYM2":      3.50,
        "CPIAUCSL":          3.20,
        "BAMLH0A0HYM2":      3.50,
    }
    if overrides:
        default_values.update(overrides)

    series = []
    for sid, val in default_values.items():
        series.append({
            "series_id":     sid,
            "latest_value":  val,
            "latest_date":   "2026-05-30",
            "units":         "Test Units",
            "frequency":     "D",
            "is_stale":      False,
            "fetched_at":    "2026-05-31T04:00:00+00:00",
        })
    return {
        "series":     series,
        "computed_at": "2026-05-31T04:00:00+00:00",
        "methodology_version": "1.0.0",
    }


def _make_sector_exp() -> Dict[str, float]:
    return {
        "Banking & Financial Services": 30.0,
        "IT":                           25.0,
        "FMCG":                         15.0,
        "Energy":                       10.0,
        "Pharma":                       10.0,
        "Auto":                         10.0,
    }


# ── 1. build_macro_context: correct mapping ───────────────────


def test_build_macro_context_all_baseline_series_present():
    snap = _make_fred_snapshot()
    ctx = build_macro_context(snap)

    assert ctx["has_live_data"] is True
    assert ctx["methodology_version"] == "macro_context@1.0.0"
    assert ctx["sourced_at"] == "2026-05-31T04:00:00+00:00"

    bv = ctx["baseline_values"]
    # All BASELINE_SERIES entries must appear as keys
    for entry in BASELINE_SERIES:
        assert entry["series_id"] in bv, f"Missing: {entry['series_id']}"
        assert bv[entry["series_id"]]["label"] == entry["label"]


def test_build_macro_context_values_match_snapshot():
    snap = _make_fred_snapshot()
    ctx = build_macro_context(snap)
    bv = ctx["baseline_values"]

    assert bv["DCOILWTICO"]["value"] == 78.50
    assert bv["DEXINUS"]["value"] == 83.40
    assert bv["VIXCLS"]["value"] == 18.20
    assert bv["DGS10"]["value"] == 4.30
    assert bv["INTDSRINM193N"]["value"] == 6.50
    assert bv["T10Y2Y"]["value"] == -0.20


# ── 2. build_macro_context: empty / None snapshot ─────────────


def test_build_macro_context_none_input():
    ctx = build_macro_context(None)
    assert ctx["has_live_data"] is False
    bv = ctx["baseline_values"]
    for entry in BASELINE_SERIES:
        assert bv[entry["series_id"]]["value"] is None
        assert bv[entry["series_id"]]["is_stale"] is True
    assert len(ctx["stale_series"]) == len(BASELINE_SERIES)


def test_build_macro_context_empty_series_list():
    ctx = build_macro_context({"series": [], "computed_at": "2026-05-31T00:00:00+00:00"})
    assert ctx["has_live_data"] is False


# ── 3. enrich_with_macro_context: adds field to all results ───


def test_enrich_adds_macro_driver_context_key():
    sector_exp = _make_sector_exp()
    results = run_scenarios(sector_exp, {"large": 80.0, "mid": 15.0, "small": 5.0}, 1_000_000.0)
    snap = _make_fred_snapshot()
    ctx = build_macro_context(snap)

    enriched = enrich_with_macro_context(results, ctx)
    assert len(enriched) == len(results)
    for r in enriched:
        assert "macro_driver_context" in r, f"Missing macro_driver_context on scenario {r.get('id')}"


# ── 4. Implied level: multiplier scenario ─────────────────────


def test_enrich_oil_spike_implied_level():
    """oil_spike_40pct: WTI baseline=78.50 → implied = 78.50 * 1.40 = 109.90"""
    sector_exp = _make_sector_exp()
    results = run_scenarios(sector_exp, {}, 1_000_000.0, scenario_ids=["oil_spike_40pct"])
    snap = _make_fred_snapshot({"DCOILWTICO": 78.50})
    ctx = build_macro_context(snap)

    enriched = enrich_with_macro_context(results, ctx)
    assert len(enriched) == 1

    dc = enriched[0]["macro_driver_context"]
    assert dc is not None
    assert dc["series_id"] == "DCOILWTICO"
    assert dc["baseline_value"] == 78.50
    assert abs(dc["implied_shocked_level"] - 109.90) < 0.01


def test_enrich_oil_collapse_implied_level():
    """oil_collapse_40pct: WTI=78.50 → implied = 78.50 * 0.60 = 47.10"""
    sector_exp = _make_sector_exp()
    results = run_scenarios(sector_exp, {}, 1_000_000.0, scenario_ids=["oil_collapse_40pct"])
    snap = _make_fred_snapshot({"DCOILWTICO": 78.50})
    ctx = build_macro_context(snap)

    enriched = enrich_with_macro_context(results, ctx)
    dc = enriched[0]["macro_driver_context"]
    assert dc is not None
    assert abs(dc["implied_shocked_level"] - 47.10) < 0.01


# ── 5. Implied level: additive scenario ───────────────────────


def test_enrich_rbi_hike_implied_level():
    """rbi_rate_hike_100bps: RBI rate=6.50 → implied = 6.50 + 1.00 = 7.50"""
    sector_exp = _make_sector_exp()
    results = run_scenarios(sector_exp, {}, 1_000_000.0, scenario_ids=["rbi_rate_hike_100bps"])
    snap = _make_fred_snapshot({"INTDSRINM193N": 6.50})
    ctx = build_macro_context(snap)

    enriched = enrich_with_macro_context(results, ctx)
    dc = enriched[0]["macro_driver_context"]
    assert dc is not None
    assert dc["baseline_value"] == 6.50
    assert abs(dc["implied_shocked_level"] - 7.50) < 0.001


def test_enrich_rbi_cut_implied_level():
    """rbi_rate_cut_75bps: RBI rate=6.50 → implied = 6.50 - 0.75 = 5.75"""
    sector_exp = _make_sector_exp()
    results = run_scenarios(sector_exp, {}, 1_000_000.0, scenario_ids=["rbi_rate_cut_75bps"])
    snap = _make_fred_snapshot({"INTDSRINM193N": 6.50})
    ctx = build_macro_context(snap)

    enriched = enrich_with_macro_context(results, ctx)
    dc = enriched[0]["macro_driver_context"]
    assert dc is not None
    assert abs(dc["implied_shocked_level"] - 5.75) < 0.001


# ── 6. None macro_context → null driver fields, no crash ──────


def test_enrich_none_macro_context_no_crash():
    sector_exp = _make_sector_exp()
    results = run_scenarios(sector_exp, {}, 1_000_000.0, scenario_ids=["oil_spike_40pct"])
    enriched = enrich_with_macro_context(results, None)

    assert len(enriched) == 1
    dc = enriched[0]["macro_driver_context"]
    assert dc is not None                        # driver spec exists
    assert dc["series_id"] == "DCOILWTICO"
    assert dc["baseline_value"] is None          # no data available
    assert dc["implied_shocked_level"] is None


# ── 7. Unknown scenario_id → macro_driver_context is None ─────


def test_enrich_unknown_scenario_id():
    fake_result = {
        "id": "totally_unknown_scenario_xyz",
        "name": "Fake",
        "estimated_impact_pct": -5.0,
    }
    enriched = enrich_with_macro_context([fake_result], None)
    assert enriched[0]["macro_driver_context"] is None


# ── 8. Determinism: same snapshot → identical output ──────────


def test_enrich_determinism():
    sector_exp = _make_sector_exp()
    cap_split = {"large": 70.0, "mid": 20.0, "small": 10.0}
    snap = _make_fred_snapshot()
    ctx = build_macro_context(snap)

    def _hash(results: list) -> str:
        blob = json.dumps(
            [{"id": r["id"], "dc": r.get("macro_driver_context")} for r in results],
            sort_keys=True,
            default=str,
        ).encode()
        return hashlib.sha256(blob).hexdigest()

    base_results = run_scenarios(sector_exp, cap_split, 1_000_000.0)
    hashes = {_hash(enrich_with_macro_context(copy.deepcopy(base_results), ctx)) for _ in range(5)}
    assert len(hashes) == 1, "enrich_with_macro_context is not deterministic"


# ── 9. Golden pin: oil_spike_40pct with fixed WTI ─────────────


def test_golden_oil_spike_40pct():
    """
    Pin the exact macro_driver_context for oil_spike_40pct at WTI=78.50.
    If this test fails, it means scenario_engine.py math changed unexpectedly.
    """
    snap = _make_fred_snapshot({"DCOILWTICO": 78.50})
    ctx = build_macro_context(snap)

    sector_exp = {"Energy": 10.0, "FMCG": 90.0}
    results = run_scenarios(sector_exp, {}, 1_000_000.0, scenario_ids=["oil_spike_40pct"])
    enriched = enrich_with_macro_context(results, ctx)

    dc = enriched[0]["macro_driver_context"]
    assert dc["series_id"] == "DCOILWTICO"
    assert dc["label"] == "WTI Crude (USD/bbl)"
    assert dc["baseline_value"] == 78.50
    assert dc["implied_shocked_level"] == round(78.50 * 1.40, 4)   # 109.9
    assert dc["is_stale"] is False


# ── 10. Empty results → empty list ────────────────────────────


def test_enrich_empty_results():
    ctx = build_macro_context(_make_fred_snapshot())
    assert enrich_with_macro_context([], ctx) == []
