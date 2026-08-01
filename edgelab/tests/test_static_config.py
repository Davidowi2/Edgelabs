"""Tests for edgelab.news.static_config (Phase 2, Module 1)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from edgelab.news.static_config import (
    NewsEvent,
    filter_events_by_currency,
    load_events_from_json,
    validate_events,
)


def _ev(**kw):
    base = dict(
        id="x1",
        name="Test Event",
        currency="USD",
        datetime_utc=datetime(2026, 7, 3, 12, 30, tzinfo=timezone.utc),
        impact="high",
        source="test",
    )
    base.update(kw)
    return NewsEvent(**base)


class TestLoad:
    def test_load_events_from_valid_json(self, tmp_path):
        data = [
            {
                "id": "us_nfp_2026_07",
                "name": "Non-Farm Payrolls",
                "currency": "USD",
                "datetime_utc": "2026-07-03T12:30:00+00:00",
                "impact": "high",
                "source": "bls.gov",
            }
        ]
        p = tmp_path / "cal.json"
        p.write_text(json.dumps(data))
        events = load_events_from_json(str(p))
        assert len(events) == 1
        e = events[0]
        assert e.id == "us_nfp_2026_07"
        assert e.currency == "USD"
        assert e.datetime_utc.tzinfo is not None

    def test_load_events_from_missing_file(self, tmp_path):
        events = load_events_from_json(str(tmp_path / "does_not_exist.json"))
        assert events == []

    def test_load_events_from_malformed_json(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text("{ this is not json ")
        # Must fail gracefully: empty list, no exception.
        events = load_events_from_json(str(p))
        assert events == []


class TestValidate:
    def test_validate_events_detects_duplicate_ids(self):
        e1 = _ev(id="dup")
        e2 = _ev(id="dup")
        errs = validate_events([e1, e2])
        assert any("duplicate" in m.lower() for m in errs)

    def test_validate_events_detects_naive_datetime(self):
        e = _ev(datetime_utc=datetime(2026, 7, 3, 12, 30))  # naive
        errs = validate_events([e])
        assert any("timezone" in m.lower() or "tz" in m.lower() for m in errs)

    def test_validate_events_detects_invalid_impact(self):
        e = _ev(impact="critical")
        errs = validate_events([e])
        assert any("impact" in m.lower() for m in errs)

    def test_validate_events_detects_invalid_currency_code(self):
        e = _ev(currency="US")  # not 3 letters
        errs = validate_events([e])
        assert any("currency" in m.lower() for m in errs)

    def test_validate_events_passes_clean_list(self):
        assert validate_events([_ev()]) == []


class TestFilter:
    def test_filter_events_by_currency_returns_only_matching(self):
        us = _ev(id="a", currency="USD")
        eu = _ev(id="b", currency="EUR")
        out = filter_events_by_currency([us, eu], ["USD"])
        assert [e.id for e in out] == ["a"]

    def test_filter_events_by_currency_handles_empty_list(self):
        assert filter_events_by_currency([], ["USD"]) == []


class Test2026File:
    def test_load_events_from_2026_file_contains_minimum_count(self):
        p = Path(__file__).resolve().parents[1] / "data" / "news_calendar_2026.json"
        assert p.exists(), f"calendar file missing: {p}"
        events = load_events_from_json(str(p))
        assert len(events) >= 80, f"only {len(events)} events, need >=80"
        # must also validate cleanly
        assert validate_events(events) == []
