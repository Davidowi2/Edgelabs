"""Tests for edgelab.trade.sl_watchdog (Phase 4, Module 2)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from edgelab.trade.position import Position, TradeDirection, TradeStatus
from edgelab.trade.sl_watchdog import SLWatchdog
from edgelab.time.broker_time import BrokerTime


@pytest.fixture
def bt():
    return BrokerTime(offset="+3", dst=False)


def _pos(sl=1.0950, lot=0.1, entry=1.1000, tp=1.1100, current=1.1000):
    return Position(
        position_id="pos-1",
        symbol="EURUSD",
        direction=TradeDirection.LONG,
        entry_price=entry,
        current_sl=sl,
        current_tp=tp,
        lot_size=lot,
        entry_time=datetime(2026, 7, 1, 10, 0, tzinfo=timezone.utc),
        status=TradeStatus.OPEN,
        magic_number="idea-1",
        current_price=current,
    )


class TestStates:
    def test_position_with_valid_sl_returns_ok(self, bt):
        wd = SLWatchdog({}, _nl(), bt)
        p = _pos(sl=1.0950)  # 50 pips * 10 * 0.1 = 50 < 150 limit
        r = wd.check_position(p, account_balance=10000.0,
                              current_time=datetime(2026, 7, 1, 10, 0, tzinfo=timezone.utc))
        assert r["status"] == "ok"
        assert r["action"] == "none"

    def test_position_without_sl_returns_critical(self, bt):
        wd = SLWatchdog({}, _nl(), bt)
        p = _pos(sl=None)  # never had SL -> immediate critical
        r = wd.check_position(p, account_balance=10000.0,
                              current_time=datetime(2026, 7, 1, 10, 0, tzinfo=timezone.utc))
        assert r["status"] == "critical"
        assert r["action"] == "flag_critical"

    def test_position_with_too_wide_sl_returns_warning(self, bt):
        wd = SLWatchdog({}, _nl(), bt)
        p = _pos(sl=1.0500)  # 500 pips * 10 * 0.1 = 500 > 150 limit
        r = wd.check_position(p, account_balance=10000.0,
                              current_time=datetime(2026, 7, 1, 10, 0, tzinfo=timezone.utc))
        assert r["status"] == "warning"
        assert r["action"] == "tighten_sl"


class TestTimer:
    def test_sl_becomes_critical_after_timer(self, bt):
        wd = SLWatchdog({}, _nl(), bt)
        t0 = datetime(2026, 7, 1, 10, 0, tzinfo=timezone.utc)
        # first seen WITH sl -> recorded as ever-having-sl
        p = _pos(sl=1.0950)
        wd.check_position(p, 10000.0, t0)
        # SL removed
        p.current_sl = None
        t1 = t0 + timedelta(seconds=5)   # within timer -> warning
        r1 = wd.check_position(p, 10000.0, t1)
        assert r1["status"] == "warning"
        # past timer -> critical
        t2 = t0 + timedelta(seconds=30)
        r2 = wd.check_position(p, 10000.0, t2)
        assert r2["status"] == "critical"

    def test_sl_timer_resets_when_sl_restored(self, bt):
        wd = SLWatchdog({}, _nl(), bt)
        t0 = datetime(2026, 7, 1, 10, 0, tzinfo=timezone.utc)
        p = _pos(sl=1.0950)
        wd.check_position(p, 10000.0, t0)   # ever-had-sl recorded
        p.current_sl = None
        t1 = t0 + timedelta(seconds=5)
        wd.check_position(p, 10000.0, t1)    # warning, timer starts
        p.current_sl = 1.0950                # restored within timer
        t2 = t0 + timedelta(seconds=10)
        r = wd.check_position(p, 10000.0, t2)
        assert r["status"] == "ok"


class TestConfig:
    def test_max_risk_pct_calculation(self, bt):
        wd = SLWatchdog({"max_risk_pct": 0.015}, _nl(), bt)
        p = _pos(sl=1.0950)  # risk 50; limit 0.015*10000=150 -> ok
        r = wd.check_position(p, 10000.0,
                              datetime(2026, 7, 1, 10, 0, tzinfo=timezone.utc))
        assert r["status"] == "ok"

    def test_configurable_max_risk_pct(self, bt):
        # tighter limit: 0.003 * 10000 = 30; risk 50 -> warning
        wd = SLWatchdog({"max_risk_pct": 0.003}, _nl(), bt)
        p = _pos(sl=1.0950)
        r = wd.check_position(p, 10000.0,
                              datetime(2026, 7, 1, 10, 0, tzinfo=timezone.utc))
        assert r["status"] == "warning"

    def test_configurable_sl_timer(self, bt):
        wd = SLWatchdog({"sl_timer_seconds": 10}, _nl(), bt)
        t0 = datetime(2026, 7, 1, 10, 0, tzinfo=timezone.utc)
        p = _pos(sl=1.0950)
        wd.check_position(p, 10000.0, t0)
        p.current_sl = None
        t1 = t0 + timedelta(seconds=3)
        wd.check_position(p, 10000.0, t1)   # warning
        t2 = t0 + timedelta(seconds=15)        # > 10s timer
        r = wd.check_position(p, 10000.0, t2)
        assert r["status"] == "critical"


def _nl():
    from edgelab.monitoring.logger import TradingLogger
    import tempfile, os
    return TradingLogger(name="sl.test", log_file=os.path.join(tempfile.gettempdir(), "sl.log"))
