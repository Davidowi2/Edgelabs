"""Tests for edgelab.risk wiring + startup integration (Phase 3, Module 4)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from edgelab.monitoring.logger import TradingLogger
from edgelab.risk import (
    AccountState,
    DrawdownProtector,
    InactivityTracker,
    create_risk_system,
)
from edgelab.time.broker_time import BrokerTime


@pytest.fixture
def logger(tmp_path):
    return TradingLogger(name="risk.wiring", log_file=str(tmp_path / "r.log"))


@pytest.fixture
def bt():
    return BrokerTime(offset="+3", dst=False)


VALID_CONFIG = {
    "risk": {
        "initial_balance": 10000.0,
        "firm_preset": "blueberry_1step",
    }
}


class TestFactory:
    def test_create_risk_system_with_valid_config(self, logger, bt):
        rs = create_risk_system(VALID_CONFIG, logger, bt)
        assert isinstance(rs["account_state"], AccountState)
        assert isinstance(rs["drawdown_protector"], DrawdownProtector)
        assert isinstance(rs["inactivity_tracker"], InactivityTracker)

    def test_create_risk_system_with_missing_initial_balance(self, logger, bt):
        bad = {"risk": {"firm_preset": "blueberry_1step"}}
        rs = create_risk_system(bad, logger, bt)
        assert rs == {} or rs is None

    def test_create_risk_system_with_unknown_firm_preset(self, logger, bt):
        bad = {"risk": {"initial_balance": 10000.0, "firm_preset": "nope"}}
        rs = create_risk_system(bad, logger, bt)
        assert rs == {} or rs is None

    def test_create_risk_system_never_raises_with_garbage_input(self, logger, bt):
        for cfg in [{}, None, {"risk": "broken"}, {"nope": 1}]:
            rs = create_risk_system(cfg, logger, bt)
            assert rs == {} or rs is None or isinstance(rs, dict)


class TestUnifiedCheck:
    def test_check_all_risk_limits_returns_complete_dict(self, logger, bt):
        from edgelab.risk import check_all_risk_limits
        rs = create_risk_system(VALID_CONFIG, logger, bt)
        t = datetime(2026, 7, 1, 10, 0, tzinfo=timezone.utc)
        out = check_all_risk_limits(rs, 10000.0, t)
        for k in ("protection_level", "action", "reason", "daily_pnl",
                  "daily_dd_pct", "total_dd_pct", "inactivity_level", "days_until_kill"):
            assert k in out

    def test_check_all_risk_limits_updates_account_state(self, logger, bt):
        from edgelab.risk import check_all_risk_limits
        rs = create_risk_system(VALID_CONFIG, logger, bt)
        t = datetime(2026, 7, 1, 10, 0, tzinfo=timezone.utc)
        check_all_risk_limits(rs, 10250.0, t)
        assert rs["account_state"].current_equity == 10250.0

    def test_risk_status_dict_has_all_required_keys(self, logger, bt):
        from edgelab.risk import check_all_risk_limits
        rs = create_risk_system(VALID_CONFIG, logger, bt)
        t = datetime(2026, 7, 1, 10, 0, tzinfo=timezone.utc)
        out = check_all_risk_limits(rs, 10000.0, t)
        assert set(out.keys()) == {
            "protection_level", "action", "reason", "daily_pnl",
            "daily_dd_pct", "total_dd_pct", "inactivity_level", "days_until_kill",
        }


class TestStartup:
    def test_startup_check_includes_risk_validation(self, logger):
        from edgelab.monitoring.startup_check import StartupValidator
        config = dict(VALID_CONFIG)
        config["news"] = {"static_calendar_path": str(
            Path(__file__).resolve().parents[1] / "data" / "news_calendar_2026.json")}
        config["broker"] = {"timezone_offset": "+3"}
        config["internal_risk"] = {"risk_per_trade_pct": 0.01, "daily_loss_lock_pct": 0.02,
                                    "total_dd_lock_pct": 0.05}
        config["news_filter"] = {"currency_map": {"EURUSD": ["EUR", "USD"]}}
        config["account"] = {"type": "demo", "confirmed": True}
        config["inactivity"] = {"last_trade_timestamp": "2026-07-01T00:00:00Z"}
        v = StartupValidator(config, logger)
        result = v.run_all_checks()
        labels = [c[0] for c in v._checks_run()]
        assert "risk_config" in labels
        assert result.passed is True
