"""Tests for edgelab.news wiring (Phase 2, Module 5)."""

from __future__ import annotations

from pathlib import Path

import pytest

from edgelab.monitoring.logger import TradingLogger
from edgelab.news import create_news_filter
from edgelab.time.broker_time import BrokerTime


@pytest.fixture
def logger(tmp_path):
    return TradingLogger(name="news.wiring", log_file=str(tmp_path / "w.log"))


@pytest.fixture
def bt():
    return BrokerTime(offset="+3", dst=False)


@pytest.fixture
def calendar_path():
    return str(Path(__file__).resolve().parents[1] / "data" / "news_calendar_2026.json")


class TestFactory:
    def test_create_news_filter_loads_static_config(self, logger, bt, calendar_path):
        config = {"news": {"static_calendar_path": calendar_path}}
        nf = create_news_filter(config, logger, bt)
        assert nf is not None
        assert len(nf._events) >= 80

    def test_create_news_filter_handles_missing_config_gracefully(self, logger, bt):
        # missing path -> pass-through filter, no raise, critical logged
        config = {"news": {"static_calendar_path": "/no/such/calendar.json"}}
        nf = create_news_filter(config, logger, bt)
        assert nf is not None
        allowed, reason = nf.is_trading_allowed("EURUSD")
        assert allowed is True

    def test_create_news_filter_never_raises(self, logger, bt):
        for cfg in [{}, None, {"news": {}}, {"news": "not a dict"}]:
            nf = create_news_filter(cfg, logger, bt)
            assert nf is not None


class TestStatus:
    def test_get_news_filter_status_returns_correct_structure(self, logger, bt, calendar_path):
        from edgelab.news import get_news_filter_status
        config = {"news": {"static_calendar_path": calendar_path}}
        nf = create_news_filter(config, logger, bt)
        status = get_news_filter_status(nf, "EURUSD")
        assert set(status.keys()) == {"trading_allowed", "reason", "size_multiplier", "next_event"}
        assert isinstance(status["trading_allowed"], bool)
        assert isinstance(status["size_multiplier"], float)


class TestStartup:
    def test_startup_check_includes_news_filter_validation(self, logger, calendar_path):
        from edgelab.monitoring.startup_check import StartupValidator
        config = {
            "news": {"static_calendar_path": calendar_path},
            "broker": {"timezone_offset": "+3"},
            "internal_risk": {"risk_per_trade_pct": 0.01, "daily_loss_lock_pct": 0.02, "total_dd_lock_pct": 0.05},
            "news_filter": {"currency_map": {"EURUSD": ["EUR", "USD"]}},
            "account": {"type": "demo", "confirmed": True},
            "inactivity": {"last_trade_timestamp": "2026-07-01T00:00:00Z"},
        }
        v = StartupValidator(config, logger)
        result = v.run_all_checks()
        assert result.passed is True
        labels = [c[0] for c in v._checks_run()]
        assert "news_calendar" in labels
