"""Tests for edgelab.risk.inactivity_tracker (Phase 3, Module 3)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from edgelab.risk.account_state import AccountState
from edgelab.risk.inactivity_tracker import InactivityTracker
from edgelab.time.broker_time import BrokerTime


@pytest.fixture
def bt():
    return BrokerTime(offset="+3", dst=False)


def _nl():
    from edgelab.monitoring.logger import TradingLogger
    import tempfile, os
    return TradingLogger(name="inact.test", log_file=os.path.join(tempfile.gettempdir(), "inact.log"))


def _state(bt):
    return AccountState(initial_balance=10000.0, broker_time=bt, logger=_nl())


class TestLevels:
    def test_safe_when_recent_trade(self, bt):
        as_ = _state(bt)
        t = datetime(2026, 7, 1, 10, 0, tzinfo=timezone.utc)
        as_.record_trade_closed(t)
        it = InactivityTracker(as_, {}, _nl(), bt)
        level, days, _ = it.check_inactivity(t + timedelta(days=5))
        assert level == "safe"
        assert days == 25  # 30 - 5

    def test_warning_at_warning_days(self, bt):
        as_ = _state(bt)
        t = datetime(2026, 7, 1, 10, 0, tzinfo=timezone.utc)
        as_.record_trade_closed(t)
        it = InactivityTracker(as_, {}, _nl(), bt)
        # 22 days since trade -> warning
        level, days, _ = it.check_inactivity(t + timedelta(days=22))
        assert level == "warning"
        assert days == 8

    def test_danger_at_danger_days(self, bt):
        as_ = _state(bt)
        t = datetime(2026, 7, 1, 10, 0, tzinfo=timezone.utc)
        as_.record_trade_closed(t)
        it = InactivityTracker(as_, {}, _nl(), bt)
        level, days, _ = it.check_inactivity(t + timedelta(days=28))
        assert level == "danger"
        assert days == 2

    def test_critical_at_kill_days(self, bt):
        as_ = _state(bt)
        t = datetime(2026, 7, 1, 10, 0, tzinfo=timezone.utc)
        as_.record_trade_closed(t)
        it = InactivityTracker(as_, {}, _nl(), bt)
        level, days, _ = it.check_inactivity(t + timedelta(days=30))
        assert level == "critical"
        assert days == 0

    def test_days_until_kill_calculation(self, bt):
        as_ = _state(bt)
        t = datetime(2026, 7, 1, 10, 0, tzinfo=timezone.utc)
        as_.record_trade_closed(t)
        it = InactivityTracker(as_, {}, _nl(), bt)
        _, days, _ = it.check_inactivity(t + timedelta(days=10))
        assert days == 20

    def test_record_trade_activity_delegates(self, bt):
        as_ = _state(bt)
        t = datetime(2026, 7, 1, 10, 0, tzinfo=timezone.utc)
        it = InactivityTracker(as_, {}, _nl(), bt)
        it.record_trade_activity(t)
        assert as_.last_trade_timestamp is not None

    def test_never_traded_returns_full_limit(self, bt):
        as_ = _state(bt)
        t = datetime(2026, 7, 1, 10, 0, tzinfo=timezone.utc)
        it = InactivityTracker(as_, {}, _nl(), bt)
        level, days, _ = it.check_inactivity(t)
        assert level == "critical"
        assert days == 30
