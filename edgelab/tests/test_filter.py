"""Tests for edgelab.news.filter.NewsFilter (Phase 2, Module 3)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from edgelab.monitoring.logger import TradingLogger
from edgelab.news.filter import NewsFilter
from edgelab.news.static_config import NewsEvent
from edgelab.time.broker_time import BrokerTime


def _event(days_offset: int, currency="USD", impact="high", name="Event", eid="e1"):
    return NewsEvent(
        id=eid,
        name=name,
        currency=currency,
        datetime_utc=datetime.now(timezone.utc) + timedelta(days=days_offset),
        impact=impact,
        source="test",
    )


@pytest.fixture
def logger(tmp_path):
    return TradingLogger(name="news.filter", log_file=str(tmp_path / "f.log"))


@pytest.fixture
def bt():
    return BrokerTime(offset="+3", dst=False)


class TestAllowance:
    def test_trading_allowed_outside_any_window(self, logger, bt):
        # event far away -> allowed
        ev = [_event(days_offset=5)]
        nf = NewsFilter({}, ev, logger, bt)
        allowed, reason = nf.is_trading_allowed("EURUSD")
        assert allowed is True

    def test_trading_blocked_in_pre_window(self, logger, bt):
        # event 20 min away, high impact (30 min pre) -> blocked
        ev = [NewsEvent(
            id="h1", name="NFP", currency="USD",
            datetime_utc=datetime.now(timezone.utc) + timedelta(minutes=20),
            impact="high", source="t")]
        nf = NewsFilter({}, ev, logger, bt)
        allowed, reason = nf.is_trading_allowed("EURUSD")
        assert allowed is False
        assert "pre" in reason.lower()

    def test_trading_blocked_in_post_window(self, logger, bt):
        ev = [NewsEvent(
            id="h1", name="NFP", currency="USD",
            datetime_utc=datetime.now(timezone.utc) - timedelta(minutes=20),
            impact="high", source="t")]
        nf = NewsFilter({}, ev, logger, bt)
        allowed, reason = nf.is_trading_allowed("EURUSD")
        assert allowed is False
        assert "post" in reason.lower()

    def test_trading_allowed_outside_post_window(self, logger, bt):
        # 35 min after a non-extended HIGH impact (30 min post) -> allowed
        ev = [NewsEvent(
            id="h1", name="ISM Manufacturing", currency="USD",
            datetime_utc=datetime.now(timezone.utc) - timedelta(minutes=35),
            impact="high", source="t")]
        nf = NewsFilter({}, ev, logger, bt)
        allowed, reason = nf.is_trading_allowed("EURUSD")
        assert allowed is True

    def test_medium_impact_window(self, logger, bt):
        ev = [NewsEvent(
            id="m1", name="CPI", currency="USD",
            datetime_utc=datetime.now(timezone.utc) + timedelta(minutes=10),
            impact="medium", source="t")]
        nf = NewsFilter({}, ev, logger, bt)
        allowed, reason = nf.is_trading_allowed("EURUSD")
        assert allowed is False

    def test_irrelevant_currency_event_does_not_block(self, logger, bt):
        # EUR event should not block GBPUSD
        ev = [NewsEvent(
            id="e1", name="ECB", currency="EUR",
            datetime_utc=datetime.now(timezone.utc) + timedelta(minutes=5),
            impact="high", source="t")]
        nf = NewsFilter({}, ev, logger, bt)
        allowed, reason = nf.is_trading_allowed("GBPUSD")
        assert allowed is True

    def test_xauusd_affected_by_usd_events(self, logger, bt):
        ev = [NewsEvent(
            id="u1", name="NFP", currency="USD",
            datetime_utc=datetime.now(timezone.utc) + timedelta(minutes=10),
            impact="high", source="t")]
        nf = NewsFilter({}, ev, logger, bt)
        allowed, reason = nf.is_trading_allowed("XAUUSD")
        assert allowed is False


class TestSizeMultiplier:
    def test_size_multiplier_normal_day(self, logger, bt):
        nf = NewsFilter({}, [_event(days_offset=5)], logger, bt)
        assert nf.get_size_multiplier("EURUSD") == 1.0

    def test_size_multiplier_high_impact_day(self, logger, bt):
        # event today (within ~0 days) for USD -> reduction applies
        ev = NewsEvent(
            id="t1", name="NFP", currency="USD",
            datetime_utc=datetime.now(timezone.utc) + timedelta(minutes=30),
            impact="high", source="t")
        nf = NewsFilter({}, [ev], logger, bt)
        assert nf.get_size_multiplier("EURUSD") == 0.5


class TestNextAndToday:
    def test_next_event_returns_upcoming(self, logger, bt):
        evs = [
            _event(days_offset=5, eid="far"),
            _event(days_offset=1, eid="near"),
        ]
        nf = NewsFilter({}, evs, logger, bt)
        nxt = nf.get_next_event("EURUSD")
        assert nxt is not None
        assert nxt.id == "near"

    def test_next_event_returns_none_when_no_upcoming(self, logger, bt):
        evs = [_event(days_offset=-5, eid="past")]
        nf = NewsFilter({}, evs, logger, bt)
        assert nf.get_next_event("EURUSD") is None

    def test_events_today_returns_only_todays(self, logger, bt):
        evs = [
            NewsEvent(id="t", name="NFP", currency="USD",
                      datetime_utc=datetime.now(timezone.utc) + timedelta(minutes=30),
                      impact="high", source="t"),
            NewsEvent(id="f", name="Later", currency="USD",
                      datetime_utc=datetime.now(timezone.utc) + timedelta(days=10),
                      impact="high", source="t"),
        ]
        nf = NewsFilter({}, evs, logger, bt)
        todays = nf.get_events_today("EURUSD")
        ids = {e.id for e in todays}
        assert "t" in ids
        assert "f" not in ids


class TestRefresh:
    def test_refresh_reloads_events_successfully(self, logger, bt, tmp_path):
        from edgelab.news.static_config import load_events_from_json
        import json
        p = tmp_path / "cal.json"
        p.write_text(json.dumps([{
            "id": "r1", "name": "R", "currency": "USD",
            "datetime_utc": "2026-07-03T12:30:00+00:00", "impact": "high", "source": "t"}]))
        evs = load_events_from_json(str(p))
        nf = NewsFilter({}, evs, logger, bt)
        assert nf.refresh(str(p)) is True

    def test_refresh_handles_missing_file_gracefully(self, logger, bt):
        nf = NewsFilter({}, [], logger, bt)
        # must not raise
        assert nf.refresh("/no/such/file.json") is False


class TestTimezone:
    def test_timezone_aware_comparison(self, logger, bt):
        # event 20 min away in UTC; broker +3 -> still within window
        ev = [NewsEvent(
            id="h1", name="NFP", currency="USD",
            datetime_utc=datetime.now(timezone.utc) + timedelta(minutes=20),
            impact="high", source="t")]
        nf = NewsFilter({}, ev, logger, bt)
        allowed, _ = nf.is_trading_allowed("EURUSD")
        assert allowed is False
