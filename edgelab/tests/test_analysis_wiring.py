"""Tests for edgelab.analysis wiring (Phase 5a, Module 4)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from edgelab.analysis import create_analysis_system, quick_analyze
from edgelab.analysis.structure import StructureAnalyzer
from edgelab.analysis.anomaly import IsolationForest
from edgelab.analysis.memory import PatternMemory, MemoryRecord, Result
from edgelab.monitoring.logger import TradingLogger
from edgelab.time.broker_time import BrokerTime


@pytest.fixture
def logger(tmp_path):
    return TradingLogger(name="anw.test", log_file=str(tmp_path / "anw.log"))


@pytest.fixture
def bt():
    return BrokerTime(offset="+3", dst=False)


def _bar(ts, c=1.1000):
    return {"timestamp": ts, "open": c, "high": c + 0.0005, "low": c - 0.0005,
            "close": c, "volume": 100.0}


def _bars(n=60, c=1.1000):
    base = datetime(2026, 7, 1, tzinfo=timezone.utc)
    return [_bar(base + timedelta(hours=i), c) for i in range(n)]


VALID = {"analysis": {"structure": {}, "anomaly": {}, "memory": {}}}


class TestFactory:
    def test_create_analysis_system_with_valid_config(self, logger, bt):
        sys = create_analysis_system(VALID, logger, bt)
        assert isinstance(sys["structure"], StructureAnalyzer)
        assert isinstance(sys["anomaly"], IsolationForest)
        assert isinstance(sys["memory"], PatternMemory)

    def test_create_analysis_system_with_missing_config(self, logger, bt):
        sys = create_analysis_system({}, logger, bt)
        assert sys == {} or sys is None

    def test_create_analysis_system_never_raises(self, logger, bt):
        for cfg in [None, {}, {"analysis": "broken"}, {"nope": 1}]:
            sys = create_analysis_system(cfg, logger, bt)
            assert sys == {} or isinstance(sys, dict)


class TestQuick:
    def test_quick_analyze_returns_complete_dict(self, logger, bt):
        bars = _bars()
        latest = bars[-1]
        out = quick_analyze(bars, latest, "ema_pullback_long", "HH_HL", 3,
                            VALID, logger)
        for k in ("structure", "anomaly_score", "anomaly_verdict", "pattern_match"):
            assert k in out

    def test_quick_analyze_with_no_memory_records(self, logger, bt):
        bars = _bars()
        out = quick_analyze(bars, bars[-1], "ema_pullback_long", "HH_HL", 3,
                           VALID, logger)
        # no records added -> pattern_match is None
        assert out["pattern_match"] is None


class TestStartup:
    def test_startup_check_includes_analysis_validation(self, logger):
        from edgelab.monitoring.startup_check import StartupValidator
        config = dict(VALID)
        config["news"] = {"static_calendar_path": "data/news_calendar_2026.json"}
        config["broker"] = {"timezone_offset": "+3"}
        config["internal_risk"] = {"risk_per_trade_pct": 0.01, "daily_loss_lock_pct": 0.02,
                                    "total_dd_lock_pct": 0.05}
        config["risk"] = {"initial_balance": 10000.0, "firm_preset": "blueberry_1step"}
        config["news_filter"] = {"currency_map": {"EURUSD": ["EUR", "USD"]}}
        config["account"] = {"type": "demo", "confirmed": True}
        config["inactivity"] = {"last_trade_timestamp": "2026-07-01T00:00:00Z"}
        v = StartupValidator(config, logger)
        labels = [c[0] for c in v._checks_run()]
        assert "analysis_config" in labels
        result = v.run_all_checks()
        assert result.passed is True


class TestFullAnalysis:
    def test_full_analysis_with_signal(self, logger, bt):
        from edgelab.analysis import full_analysis, create_analysis_system
        from edgelab.analysis.decision_log import DecisionLogger
        from edgelab.analysis.memory import PatternMemory
        sys = create_analysis_system(VALID, logger, bt)
        dl = DecisionLogger({"log_dir": "edgelab/logs/decisions_test"}, logger,
                           PatternMemory({}, logger))
        bars = _bars(80, 1.1000)
        signal = {"symbol": "EURUSD", "direction": "LONG", "entry_price": 1.1000,
                  "stop_loss": 1.0950, "take_profit": 1.1100, "signal_type": "ema_pullback_long"}
        risk = {"risk_status": {"protection_level": "SAFE"}, "inactivity_status": "normal",
                "news_status": {"trading_allowed": True}, "trade_management_status": {"is_critical": False}}
        out = full_analysis(bars, "EURUSD", bars[-1]["timestamp"], signal_data=signal,
                            risk_data=risk, analysis_system=sys, decision_logger=dl)
        assert out["decision_log"] is not None

    def test_full_analysis_without_signal(self, logger, bt):
        from edgelab.analysis import full_analysis, create_analysis_system
        sys = create_analysis_system(VALID, logger, bt)
        bars = _bars(80, 1.1000)
        out = full_analysis(bars, "EURUSD", bars[-1]["timestamp"], analysis_system=sys)
        assert out["decision_log"] is None
        assert out["structure"] is not None
        assert isinstance(out["anomaly_score"], float)
        assert isinstance(out["patterns"], list)

    def test_full_analysis_returns_all_keys(self, logger, bt):
        from edgelab.analysis import full_analysis, create_analysis_system
        sys = create_analysis_system(VALID, logger, bt)
        bars = _bars(80, 1.1000)
        out = full_analysis(bars, "EURUSD", bars[-1]["timestamp"], analysis_system=sys)
        for k in ("structure", "anomaly_score", "anomaly_verdict", "patterns", "pattern_match", "decision_log"):
            assert k in out

    def test_full_analysis_creates_system_if_not_provided(self, logger, bt):
        from edgelab.analysis import full_analysis
        bars = _bars(80, 1.1000)
        out = full_analysis(bars, "EURUSD", bars[-1]["timestamp"])
        # no system given -> internally created, still returns analysis
        assert out["structure"] is not None
        assert isinstance(out["patterns"], list)

    def test_full_analysis_reuses_provided_system(self, logger, bt):
        from edgelab.analysis import full_analysis, create_analysis_system
        sys = create_analysis_system(VALID, logger, bt)
        bars = _bars(80, 1.1000)
        # building analysis twice with the SAME system should not error / recreate
        out1 = full_analysis(bars, "EURUSD", bars[-1]["timestamp"], analysis_system=sys)
        out2 = full_analysis(bars, "EURUSD", bars[-1]["timestamp"], analysis_system=sys)
        assert out1["patterns"] is not None
        assert out2["patterns"] is not None

