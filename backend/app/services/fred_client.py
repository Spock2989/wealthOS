"""
WealthOS — FRED API client.

Thin, deterministic wrapper around the St. Louis Fed FRED API.
- Reads FRED_API_KEY from env (never accepted as a constructor argument
  from caller-supplied input; secrets stay in env).
- Internal token-bucket rate limiter (FRED's free tier = 120 req/min).
- Exponential backoff on 5xx/429.
- Returns structured dataclass results — never raw JSON to callers.
- Never raises into the caller for routine FRED failures; instead returns
  a result with `ok=False` and a structured `error` so the upstream
  pipeline can surface a `STALE_MACRO` flag instead of crashing.

methodology_version: fred_client@1.0.0
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

CLIENT_VERSION = "1.0.0"

_FRED_BASE = "https://api.stlouisfed.org/fred"
_DEFAULT_TIMEOUT_S = 15.0
_MAX_RETRIES = 4
_RATE_LIMIT_PER_MIN = 110          # leave headroom below FRED's 120/min ceiling
_TOKEN_REFRESH_S = 60 / _RATE_LIMIT_PER_MIN


@dataclass
class Observation:
    date: date
    value: Optional[float]          # FRED's '.' for missing → None


@dataclass
class SeriesMeta:
    series_id: str
    title: Optional[str] = None
    units: Optional[str] = None
    frequency: Optional[str] = None
    last_updated: Optional[str] = None


@dataclass
class FredResult:
    ok: bool
    series_id: str
    meta: Optional[SeriesMeta] = None
    observations: List[Observation] = field(default_factory=list)
    error: Optional[str] = None
    client_version: str = CLIENT_VERSION
    fetched_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class _TokenBucket:
    """Simple thread-unsafe token bucket. Sufficient for the sync script's
    single-threaded use; the API route layer is read-only against the DB
    cache and does not call FRED inline."""
    def __init__(self, refresh_s: float) -> None:
        self._refresh_s = refresh_s
        self._next_ok = 0.0

    def acquire(self) -> None:
        now = time.monotonic()
        wait = self._next_ok - now
        if wait > 0:
            time.sleep(wait)
        self._next_ok = max(now, self._next_ok) + self._refresh_s


class FredClient:
    """
    Stateless against process restart (no in-memory cache). DB caching is
    the responsibility of `app.services.macro_cache`; this class is a pure
    HTTP adapter.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        timeout_s: float = _DEFAULT_TIMEOUT_S,
        max_retries: int = _MAX_RETRIES,
    ) -> None:
        # Prefer env. Allow override only for tests (mocked HTTP).
        self._api_key = api_key or os.getenv("FRED_API_KEY", "").strip()
        self._timeout_s = timeout_s
        self._max_retries = max_retries
        self._bucket = _TokenBucket(_TOKEN_REFRESH_S)

    def has_key(self) -> bool:
        return bool(self._api_key)

    # ---------- public ---------- #

    def get_series(
        self,
        series_id: str,
        start: Optional[date] = None,
        end: Optional[date] = None,
    ) -> FredResult:
        """Fetch metadata + observations for a series. Always returns a result."""
        if not self._api_key:
            return FredResult(ok=False, series_id=series_id,
                              error="FRED_API_KEY not set in environment")

        meta = self._series_meta(series_id)
        if meta is None:
            return FredResult(ok=False, series_id=series_id,
                              error=f"series_meta_failed:{series_id}")

        obs = self._series_observations(series_id, start, end)
        if obs is None:
            return FredResult(ok=False, series_id=series_id, meta=meta,
                              error=f"series_observations_failed:{series_id}")

        return FredResult(ok=True, series_id=series_id, meta=meta, observations=obs)

    # ---------- internals ---------- #

    def _series_meta(self, series_id: str) -> Optional[SeriesMeta]:
        data = self._get("/series", {"series_id": series_id})
        if not data or "seriess" not in data or not data["seriess"]:
            return None
        s = data["seriess"][0]
        return SeriesMeta(
            series_id=series_id,
            title=s.get("title"),
            units=s.get("units"),
            frequency=s.get("frequency_short") or s.get("frequency"),
            last_updated=s.get("last_updated"),
        )

    def _series_observations(
        self,
        series_id: str,
        start: Optional[date],
        end: Optional[date],
    ) -> Optional[List[Observation]]:
        params: Dict[str, Any] = {"series_id": series_id, "sort_order": "asc"}
        if start:
            params["observation_start"] = start.isoformat()
        if end:
            params["observation_end"] = end.isoformat()

        data = self._get("/series/observations", params)
        if not data or "observations" not in data:
            return None

        out: List[Observation] = []
        for o in data["observations"]:
            try:
                d = date.fromisoformat(o["date"])
            except (ValueError, KeyError):
                continue
            raw = o.get("value", ".")
            value = None if raw in (".", "", None) else float(raw)
            out.append(Observation(date=d, value=value))
        return out

    def _get(self, path: str, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """HTTP GET with rate limit, retry, and structured failure return."""
        params = dict(params)
        params["api_key"] = self._api_key
        params["file_type"] = "json"

        for attempt in range(self._max_retries + 1):
            self._bucket.acquire()
            try:
                with httpx.Client(timeout=self._timeout_s) as client:
                    r = client.get(_FRED_BASE + path, params=params)
            except httpx.HTTPError as e:
                logger.warning("FRED network error path=%s attempt=%d err=%s", path, attempt, e)
                self._backoff(attempt)
                continue

            if r.status_code == 200:
                try:
                    return r.json()
                except ValueError:
                    logger.warning("FRED non-JSON response path=%s", path)
                    return None

            if r.status_code in (429, 500, 502, 503, 504):
                logger.warning("FRED transient %s path=%s attempt=%d", r.status_code, path, attempt)
                self._backoff(attempt)
                continue

            # 4xx other than 429 — caller mistake or auth issue; do not retry
            logger.error("FRED non-retryable %s path=%s body=%s", r.status_code, path, r.text[:200])
            return None
        return None

    @staticmethod
    def _backoff(attempt: int) -> None:
        # 0.5, 1, 2, 4 — capped
        time.sleep(min(2 ** attempt * 0.5, 4.0))
