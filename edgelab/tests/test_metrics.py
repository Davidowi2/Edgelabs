"""Tests for edgelab.monitoring.metrics.SystemMetrics (Phase 1, Module 4)."""

from __future__ import annotations

from pathlib import Path

import pytest

from edgelab.monitoring.logger import TradingLogger
from edgelab.monitoring.metrics import SystemMetrics


@pytest.fixture
def metrics(tmp_path):
    logger = TradingLogger(name="edgelab.metrics", log_file=str(tmp_path / "m.log"))
    return SystemMetrics(logger=logger)


class TestTicks:
    def test_record_tick_increments_counter(self, metrics):
        metrics.record_tick()
        metrics.record_tick()
        assert metrics.get_summary()["total_ticks"] == 2

    def test_uptime_increases(self, metrics, monkeypatch):
        # patch time.time used by SystemMetrics
        t0 = 1000.0
        seq = {"v": t0}
        import edgelab.monitoring.metrics as mmod

        monkeypatch.setattr(mmod.time, "time", lambda: seq["v"])
        m = metrics
        m._start_time = t0
        seq["v"] = t0 + 5
        assert m.get_uptime_seconds() == 5


class TestApi:
    def test_record_api_call_tracks_success_rate(self, metrics):
        metrics.record_api_call("/quotes", 12.0, True)
        metrics.record_api_call("/quotes", 14.0, False)
        s = metrics.get_summary()
        assert s["api_calls_total"] == 2
        assert s["api_success_rate"] == 0.5
        assert s["api_avg_latency_ms"] == 13.0


class TestErrors:
    def test_record_error_increments(self, metrics):
        metrics.record_error("feed", "timeout")
        metrics.record_error("feed", "timeout")
        metrics.record_error("risk", "reject")
        s = metrics.get_summary()
        assert s["errors_total"] == 3
        assert s["errors_by_component"]["feed"] == 2
        assert s["errors_by_type"]["timeout"] == 2


class TestNews:
    def test_record_news_block(self, metrics):
        metrics.record_news_block("EURUSD", "CPI", 30)
        metrics.record_news_block("EURUSD", "FOMC", 45)
        s = metrics.get_summary()
        assert s["news_blocks_total"] == 2
        assert s["news_blocked_minutes_total"] == 75


class TestTrades:
    def test_record_trade_execution(self, metrics):
        metrics.record_trade_execution()
        metrics.record_trade_execution()
        assert metrics.get_summary()["trades_executed"] == 2


class TestSummary:
    def test_get_summary_returns_all_fields(self, metrics):
        s = metrics.get_summary()
        for key in (
            "total_ticks",
            "ticks_per_second",
            "api_calls_total",
            "api_success_rate",
            "api_avg_latency_ms",
            "errors_total",
            "errors_by_component",
            "errors_by_type",
            "news_blocks_total",
            "news_blocked_minutes_total",
            "trades_executed",
            "uptime_seconds",
            "last_tick_ts",
            "last_error_ts",
        ):
            assert key in s
