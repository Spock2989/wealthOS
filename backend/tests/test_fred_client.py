"""
Tests for the FRED client + cache + sync flow.

Strategy: HTTP is mocked with respx so we never hit real FRED in CI.
Database uses an in-memory SQLite. Determinism is asserted by running
the same upsert twice and checking the second run is a no-op.

Run with:
  cd backend && PYTHONPATH=. pytest tests/test_fred_client.py -v
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.macro_observation import MacroObservation
from app.services import macro_cache
from app.services.fred_client import FredClient, FredResult, Observation, SeriesMeta


# ── DB fixture ──────────────────────────────────────────────────────

@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    s = Session()
    try:
        yield s
    finally:
        s.close()


# ── Mocked HTTP ─────────────────────────────────────────────────────

class _MockResponse:
    def __init__(self, status_code: int, body: dict):
        self.status_code = status_code
        self._body = body
        self.text = json.dumps(body)

    def json(self):
        return self._body


class _MockClient:
    """Stand-in for httpx.Client. Returns canned responses by URL+params."""
    def __init__(self, responses):
        self._responses = responses
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def get(self, url, params):
        self.calls.append((url, dict(params)))
        for matcher, resp in self._responses:
            if matcher(url, params):
                return resp
        return _MockResponse(404, {"error": "not_in_mock"})


def _fixture_responses():
    """Two canned FRED responses: /series meta, /series/observations data."""
    meta_body = {
        "seriess": [{
            "id": "DGS10",
            "title": "10-Year Treasury Constant Maturity Rate",
            "units": "Percent",
            "frequency_short": "D",
            "last_updated": "2026-05-27 15:34:00-05",
        }],
    }
    obs_body = {
        "observations": [
            {"date": "2026-05-26", "value": "4.31"},
            {"date": "2026-05-27", "value": "4.28"},
            {"date": "2026-05-28", "value": "."},   # FRED's missing
        ],
    }
    return [
        (lambda u, p: u.endswith("/series") and p.get("series_id") == "DGS10",
         _MockResponse(200, meta_body)),
        (lambda u, p: u.endswith("/series/observations") and p.get("series_id") == "DGS10",
         _MockResponse(200, obs_body)),
    ]


# ── Tests ───────────────────────────────────────────────────────────

def test_fred_client_returns_structured_result():
    responses = _fixture_responses()
    with patch("httpx.Client", lambda timeout=None: _MockClient(responses)):
        c = FredClient(api_key="testkey")
        r = c.get_series("DGS10")

    assert r.ok is True
    assert r.series_id == "DGS10"
    assert r.meta is not None and r.meta.title.startswith("10-Year")
    assert r.meta.units == "Percent"
    assert r.meta.frequency == "D"
    assert len(r.observations) == 3
    assert r.observations[0].date == date(2026, 5, 26)
    assert r.observations[0].value == 4.31
    assert r.observations[2].value is None        # FRED '.' → None


def test_fred_client_no_key_returns_structured_error():
    c = FredClient(api_key="")
    r = c.get_series("DGS10")
    assert r.ok is False
    assert "FRED_API_KEY" in (r.error or "")
    assert r.observations == []


def test_upsert_is_idempotent(db):
    """Same rows → second upsert is a no-op (0 inserted, 0 updated)."""
    rows = [
        (date(2026, 5, 26), 4.31),
        (date(2026, 5, 27), 4.28),
    ]
    first = macro_cache.upsert_observations(db, "DGS10", "10Y", "Percent", "D", rows)
    assert first == {"inserted": 2, "updated": 0}

    second = macro_cache.upsert_observations(db, "DGS10", "10Y", "Percent", "D", rows)
    assert second == {"inserted": 0, "updated": 0}, "second run must be a no-op"


def test_upsert_updates_changed_value(db):
    macro_cache.upsert_observations(db, "DGS10", "10Y", "Percent", "D", [(date(2026, 5, 26), 4.31)])
    res = macro_cache.upsert_observations(db, "DGS10", "10Y", "Percent", "D", [(date(2026, 5, 26), 4.40)])
    assert res == {"inserted": 0, "updated": 1}
    latest = macro_cache.get_latest(db, "DGS10")
    assert latest.value == 4.40


def test_snapshot_flags_missing_series(db):
    macro_cache.upsert_observations(db, "DGS10", "10Y", "Percent", "D", [(date(2026, 5, 27), 4.28)])
    snap = macro_cache.build_snapshot(db, ["DGS10", "VIXCLS"])
    by_id = {s.series_id: s for s in snap.series}
    assert by_id["DGS10"].latest_value == 4.28
    assert by_id["VIXCLS"].latest_value is None
    assert by_id["VIXCLS"].is_stale is True


def test_registry_has_twelve_series():
    from app.services.macro_registry import SERIES_REGISTRY, registered_ids
    assert len(SERIES_REGISTRY) == 12
    # All registered IDs must be unique
    assert len(set(registered_ids())) == 12
    # India coverage check — must have at least 3 India-tagged series
    india = [s for s in SERIES_REGISTRY if s.geography == "India"]
    assert len(india) >= 3, "India macro coverage too thin"


def test_history_is_deterministic_order(db):
    """Order must be ascending by date, regardless of insert order."""
    rows_a = [(date(2026, 5, 27), 4.28), (date(2026, 5, 26), 4.31)]
    macro_cache.upsert_observations(db, "DGS10", "10Y", "Percent", "D", rows_a)
    hist = macro_cache.get_history(db, "DGS10")
    dates = [h.observation_date for h in hist]
    assert dates == sorted(dates)
