"""Tests for edgelab.risk.account_state.AccountState (Phase 3, Module 1)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from edgelab.risk.account_state import AccountState
from edgelab.time.broker_time import BrokerTime


@pytest.fixture
def bt():
    return BrokerTime(offset="+3", dst=False)


class TestInitial:
    def test_initial_state(self, bt):
        as_ = AccountState(initial_balance=10000.0, broker_time=bt, logger=_noop_logger())
        assert as_.initial_balance == 10000.0
        assert as_.current_equity == 10000.0
        assert as_.peak_equity == 10000.0
        assert as_.daily_starting_balance == 10000.0
        assert as_.daily_starting_equity == 10000.0
        assert as_.daily_high_equity == 10000.0


class TestUpdate:
    def test_update_sets_current_equity(self, bt):
        as_ = AccountState(10000.0, bt, _noop_logger())
        t = datetime(2026, 7, 1, 10, 0, tzinfo=timezone.utc)
        as_.update(10500.0, t)
        assert as_.current_equity == 10500.0
        assert as_.last_update_timestamp is not None

    def test_peak_equity_only_moves_up(self, bt):
        as_ = AccountState(10000.0, bt, _noop_logger())
        base = datetime(2026, 7, 1, 10, 0, tzinfo=timezone.utc)
        as_.update(10500.0, base)
        as_.update(9800.0, base + timedelta(hours=1))  # dip
        as_.update(10200.0, base + timedelta(hours=2))
        assert as_.peak_equity == 10500.0

    def test_daily_reset_at_new_day(self, bt):
        as_ = AccountState(10000.0, bt, _noop_logger())
        d1 = datetime(2026, 7, 1, 10, 0, tzinfo=timezone.utc)
        as_.update(10600.0, d1)
        d2 = datetime(2026, 7, 2, 10, 0, tzinfo=timezone.utc)  # new broker day
        as_.update(9000.0, d2)
        # daily window resets; daily_starting_equity uses higher of initial_balance or equity
        assert as_.daily_starting_balance == 9000.0
        assert as_.daily_starting_equity == 10000.0  # initial_balance > 9000
        assert as_.daily_high_equity == 9000.0
        # peak must NOT reset
        assert as_.peak_equity == 10600.0


class TestMetrics:
    def test_daily_pnl_calculation(self, bt):
        as_ = AccountState(10000.0, bt, _noop_logger())
        t = datetime(2026, 7, 1, 10, 0, tzinfo=timezone.utc)
        as_.update(10000.0, t)  # opening tick
        as_.update(10300.0, t + timedelta(hours=1))
        assert as_.get_daily_pnl() == 300.0

    def test_daily_pnl_pct_calculation(self, bt):
        as_ = AccountState(10000.0, bt, _noop_logger())
        t = datetime(2026, 7, 1, 10, 0, tzinfo=timezone.utc)
        as_.update(10000.0, t)
        as_.update(10200.0, t + timedelta(hours=1))
        assert abs(as_.get_daily_pnl_pct() - 0.02) < 1e-9

    def test_daily_drawdown_is_non_negative(self, bt):
        as_ = AccountState(10000.0, bt, _noop_logger())
        t = datetime(2026, 7, 1, 10, 0, tzinfo=timezone.utc)
        as_.update(10600.0, t)
        as_.update(10300.0, t + timedelta(hours=1))
        assert as_.get_daily_drawdown() >= 0
        assert as_.get_daily_drawdown() == 300.0

    def test_daily_drawdown_pct_calculation(self, bt):
        as_ = AccountState(10000.0, bt, _noop_logger())
        t = datetime(2026, 7, 1, 10, 0, tzinfo=timezone.utc)
        as_.update(10600.0, t)
        as_.update(10300.0, t + timedelta(hours=1))
        # dd = 300 / daily_starting_equity (10600)
        assert abs(as_.get_daily_drawdown_pct() - (300.0 / 10600.0)) < 1e-9

    def test_total_drawdown_calculation(self, bt):
        as_ = AccountState(10000.0, bt, _noop_logger())
        t = datetime(2026, 7, 1, 10, 0, tzinfo=timezone.utc)
        as_.update(11000.0, t)
        as_.update(9500.0, t + timedelta(hours=1))
        assert as_.get_total_drawdown() == 1500.0
        assert as_.get_total_drawdown() >= 0

    def test_total_drawdown_pct_calculation(self, bt):
        as_ = AccountState(10000.0, bt, _noop_logger())
        t = datetime(2026, 7, 1, 10, 0, tzinfo=timezone.utc)
        as_.update(11000.0, t)
        as_.update(9900.0, t + timedelta(hours=1))
        assert abs(as_.get_total_drawdown_pct() - (1100.0 / 11000.0)) < 1e-9


class TestInactivity:
    def test_get_days_since_last_trade_never_traded(self, bt):
        as_ = AccountState(10000.0, bt, _noop_logger())
        t = datetime(2026, 7, 1, 10, 0, tzinfo=timezone.utc)
        # no trade ever -> large number
        assert as_.get_days_since_last_trade(t) > 1000

    def test_get_days_since_last_trade_returns_zero_after_record(self, bt):
        as_ = AccountState(10000.0, bt, _noop_logger())
        t = datetime(2026, 7, 1, 10, 0, tzinfo=timezone.utc)
        as_.record_trade_closed(t)
        assert as_.get_days_since_last_trade(t) == 0

    def test_get_days_since_last_trade_delta(self, bt):
        as_ = AccountState(10000.0, bt, _noop_logger())
        t0 = datetime(2026, 7, 1, 10, 0, tzinfo=timezone.utc)
        as_.record_trade_closed(t0)
        t5 = t0 + timedelta(days=5)
        assert as_.get_days_since_last_trade(t5) == 5

    def test_record_trade_closed_updates_timestamp(self, bt):
        as_ = AccountState(10000.0, bt, _noop_logger())
        t = datetime(2026, 7, 1, 10, 0, tzinfo=timezone.utc)
        as_.record_trade_closed(t)
        assert as_.last_trade_timestamp is not None


class TestDailyStarting:
    def test_daily_starting_uses_higher_equity(self, bt):
        as_ = AccountState(10000.0, bt, _noop_logger())
        t = datetime(2026, 7, 1, 10, 0, tzinfo=timezone.utc)
        as_.update(10800.0, t)  # equity > balance
        assert as_.daily_starting_equity == 10800.0

    def test_daily_starting_uses_higher_balance(self, bt):
        as_ = AccountState(10000.0, bt, _noop_logger())
        t = datetime(2026, 7, 1, 10, 0, tzinfo=timezone.utc)
        as_.update(9700.0, t)  # equity < balance
        assert as_.daily_starting_equity == 10000.0


def _noop_logger():
    from edgelab.monitoring.logger import TradingLogger
    import tempfile, os
    p = os.path.join(tempfile.gettempdir(), "acct_test.log")
    return TradingLogger(name="acct.test", log_file=p)
