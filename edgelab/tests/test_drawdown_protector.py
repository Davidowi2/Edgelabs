"""Tests for edgelab.risk.drawdown_protector + firm_presets (Phase 3, Module 2)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from edgelab.risk.account_state import AccountState
from edgelab.risk.drawdown_protector import (
    DrawdownProtector,
    ProtectionAction,
    ProtectionLevel,
)
from edgelab.risk.firm_presets import get_firm_preset, list_firm_presets
from edgelab.time.broker_time import BrokerTime


@pytest.fixture
def bt():
    return BrokerTime(offset="+3", dst=False)


def _make_state(equity, peak, daily_start, daily_high, bt):
    """Build an AccountState pre-seeded via update().

    daily_start is pinned to initial_balance (10000) by design; to test TOTAL
    drawdown in isolation we seed a higher peak and use daily_high as the first
    tick so the daily drawdown stays small while total drawdown is meaningful.
    """
    as_ = AccountState(initial_balance=10000.0, broker_time=bt, logger=_nl())
    t = datetime(2026, 7, 1, 10, 0, tzinfo=timezone.utc)
    as_.peak_equity = peak
    as_.update(daily_high, t)            # sets daily window; daily_high becomes first tick
    as_.update(equity, t + __import__("datetime").timedelta(hours=1))
    return as_


def _nl():
    from edgelab.monitoring.logger import TradingLogger
    import tempfile, os
    return TradingLogger(name="dd.test", log_file=os.path.join(tempfile.gettempdir(), "dd.log"))


class TestLevels:
    def test_safe_when_no_drawdown(self, bt):
        as_ = _make_state(equity=10000, peak=10000, daily_start=10000, daily_high=10000, bt=bt)
        dp = DrawdownProtector({}, as_, _nl())
        level, action, reason = dp.check_protection()
        assert level == ProtectionLevel.SAFE
        assert action == ProtectionAction.NONE

    def test_caution_on_daily_warn(self, bt):
        # daily DD 1.5% -> caution
        as_ = _make_state(equity=9850, peak=10000, daily_start=10000, daily_high=10000, bt=bt)
        dp = DrawdownProtector({}, as_, _nl())
        level, action, _ = dp.check_protection()
        assert level == ProtectionLevel.CAUTION
        assert action == ProtectionAction.REDUCE_SIZE

    def test_danger_on_daily_danger(self, bt):
        # daily DD 1.8% -> danger
        as_ = _make_state(equity=9820, peak=10000, daily_start=10000, daily_high=10000, bt=bt)
        dp = DrawdownProtector({}, as_, _nl())
        level, action, _ = dp.check_protection()
        assert level == ProtectionLevel.DANGER
        assert action == ProtectionAction.BLOCK_NEW_TRADES

    def test_kill_on_daily_kill(self, bt):
        # daily DD 2.0% -> kill
        as_ = _make_state(equity=9800, peak=10000, daily_start=10000, daily_high=10000, bt=bt)
        dp = DrawdownProtector({}, as_, _nl())
        level, action, _ = dp.check_protection()
        assert level == ProtectionLevel.KILL
        assert action == ProtectionAction.CLOSE_ALL_POSITIONS

    def test_caution_on_total_warn(self, bt):
        # total DD 2.5% -> caution (peak 10300, day high 10000, equity 10042.5)
        as_ = _make_state(equity=10042.5, peak=10300, daily_start=10000, daily_high=10000, bt=bt)
        dp = DrawdownProtector({}, as_, _nl())
        level, _, _ = dp.check_protection()
        assert level == ProtectionLevel.CAUTION

    def test_kill_on_total_kill(self, bt):
        # total DD 3.0% -> kill
        as_ = _make_state(equity=9700, peak=10000, daily_start=10000, daily_high=10000, bt=bt)
        dp = DrawdownProtector({}, as_, _nl())
        level, action, _ = dp.check_protection()
        assert level == ProtectionLevel.KILL
        assert action == ProtectionAction.CLOSE_ALL_POSITIONS

    def test_kill_takes_precedence_over_caution(self, bt):
        # both limits hit, kill wins
        as_ = _make_state(equity=9700, peak=10000, daily_start=9750, daily_high=9750, bt=bt)
        dp = DrawdownProtector({}, as_, _nl())
        level, _, _ = dp.check_protection()
        assert level == ProtectionLevel.KILL


class TestRecoveryBuffer:
    def test_recovery_buffer_reduces_thresholds(self, bt):
        # 10% recovery buffer: daily kill becomes 1.8% instead of 2.0%
        # equity 9820 on daily_start 10000 -> daily DD 1.8% -> would be DANGER normally,
        # with buffer kill at 1.8% -> KILL.
        as_ = _make_state(equity=9820, peak=10000, daily_start=10000, daily_high=10000, bt=bt)
        dp = DrawdownProtector({"recovery_buffer_pct": 0.1}, as_, _nl())
        level, _, reason = dp.check_protection()
        assert level == ProtectionLevel.KILL
        assert "1.8" in reason


class TestStatus:
    def test_get_status_returns_full_dict(self, bt):
        as_ = _make_state(equity=9850, peak=10000, daily_start=10000, daily_high=10000, bt=bt)
        dp = DrawdownProtector({}, as_, _nl())
        st = dp.get_status()
        for k in ("level", "action", "reason", "daily_dd_pct", "total_dd_pct"):
            assert k in st


class TestFirmPresets:
    def test_get_firm_preset_returns_blueberry_config(self):
        p = get_firm_preset("blueberry_1step")
        assert p["daily_dd_kill_pct"] == 0.02
        assert p["total_dd_kill_pct"] == 0.03

    def test_get_firm_preset_raises_on_unknown_name(self):
        with pytest.raises(ValueError):
            get_firm_preset("does_not_exist")

    def test_list_firm_presets_returns_at_least_blueberry(self):
        names = list_firm_presets()
        assert "blueberry_1step" in names
