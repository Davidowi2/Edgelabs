"""Tests for edgelab.monitoring.startup_check.StartupValidator (Phase 1, Module 5)."""

from __future__ import annotations

from pathlib import Path

import pytest

from edgelab.monitoring.logger import TradingLogger
from edgelab.monitoring.startup_check import StartupValidator


def _validator(config, tmp_path):
    logger = TradingLogger(name="edgelab.startup", log_file=str(tmp_path / "s.log"))
    return StartupValidator(config=config, logger=logger)


VALID = {
    "broker": {"timezone_offset": "+3"},
    "risk": {
        "risk_per_trade_pct": 0.01,
        "daily_loss_lock_pct": 0.02,
        "total_dd_lock_pct": 0.05,
    },
    "news_filter": {"currency_map": {"EURUSD": ["USD", "EUR"]}},
    "account": {"type": "demo", "confirmed": True},
    "inactivity": {"last_trade_timestamp": "2026-07-01T00:00:00Z"},
}


class TestAllPass:
    def test_all_checks_pass_with_valid_config(self, tmp_path):
        v = _validator(VALID, tmp_path)
        result = v.run_all_checks()
        assert result.passed is True
        assert result.errors == []


class TestBrokerTime:
    def test_warns_on_zero_offset(self, tmp_path):
        cfg = dict(VALID)
        cfg["broker"] = {"timezone_offset": "+0"}
        v = _validator(cfg, tmp_path)
        # check should warn but not error
        passed, msg = v.check_broker_time_configured()
        assert passed is True
        # run all -> warnings present, still passes
        result = v.run_all_checks()
        assert any("offset" in w.lower() for w in result.warnings)
        assert result.passed is True


class TestRiskLimits:
    def test_error_on_too_high(self, tmp_path):
        cfg = dict(VALID)
        cfg["risk"] = dict(VALID["risk"])
        cfg["risk"]["risk_per_trade_pct"] = 0.05
        v = _validator(cfg, tmp_path)
        result = v.run_all_checks()
        assert result.passed is False
        assert any("risk" in e.lower() for e in result.errors)

    def test_warn_on_moderate(self, tmp_path):
        cfg = dict(VALID)
        cfg["risk"] = dict(VALID["risk"])
        cfg["risk"]["risk_per_trade_pct"] = 0.015
        v = _validator(cfg, tmp_path)
        passed, msg = v.check_risk_limits_configured()
        assert passed is True
        result = v.run_all_checks()
        assert any("risk" in w.lower() for w in result.warnings)


class TestNewsFilter:
    def test_errors_on_missing_symbol(self, tmp_path):
        cfg = dict(VALID)
        cfg["news_filter"] = {"currency_map": {}}
        v = _validator(cfg, tmp_path)
        result = v.run_all_checks()
        assert result.passed is False
        assert any("news" in e.lower() for e in result.errors)


class TestAccountType:
    def test_warns_on_live(self, tmp_path):
        cfg = dict(VALID)
        cfg["account"] = {"type": "live", "confirmed": False}
        v = _validator(cfg, tmp_path)
        passed, msg = v.check_account_type()
        assert passed is True
        result = v.run_all_checks()
        assert any("live" in w.lower() for w in result.warnings)


class TestInactivity:
    def test_errors_on_missing(self, tmp_path):
        cfg = dict(VALID)
        cfg["inactivity"] = {}
        v = _validator(cfg, tmp_path)
        result = v.run_all_checks()
        assert result.passed is False
        assert any("inactiv" in e.lower() for e in result.errors)


class TestLogDir:
    def test_log_directory_writable(self, tmp_path):
        cfg = dict(VALID)
        v = _validator(cfg, tmp_path)
        passed, msg = v.check_log_directory_writable(log_dir=str(tmp_path / "logs"))
        assert passed is True


class TestResultStructure:
    def test_run_all_checks_returns_structured_result(self, tmp_path):
        v = _validator(VALID, tmp_path)
        result = v.run_all_checks()
        assert hasattr(result, "passed")
        assert isinstance(result.errors, list)
        assert isinstance(result.warnings, list)


class TestExecutionConfig:
    def test_missing_execution_is_warning(self, tmp_path):
        v = _validator(VALID, tmp_path)
        passed, msg = v.check_execution_config()
        assert passed is True
        assert "warn" in msg.lower()

    def test_valid_execution_config_passes(self, tmp_path):
        cfg = dict(VALID)
        cfg["execution"] = {
            "spread": {"max_spread_points": 35.0},
            "circuit_breaker": {"failure_threshold": 5},
        }
        v = _validator(cfg, tmp_path)
        passed, msg = v.check_execution_config()
        assert passed is True

    def test_invalid_threshold_fails(self, tmp_path):
        cfg = dict(VALID)
        cfg["execution"] = {
            "spread": {},
            "circuit_breaker": {"failure_threshold": 0},
        }
        v = _validator(cfg, tmp_path)
        passed, msg = v.check_execution_config()
        assert passed is False

    def test_execution_check_wired_into_run_all(self, tmp_path):
        v = _validator(VALID, tmp_path)
        labels = [label for label, _ in v._checks_run()]
        assert "execution_config" in labels
