"""Tests for edgelab.signal factory (Phase 7, Module 3).

Covers create_signal_system / quick_signal_check: factory wiring, disabled
config (fail-open {}), and crash fail-open. Pure standard library only.
"""

import sys, os, tempfile
sys.path.insert(0, r"C:/Users/GTHub/Downloads/EDGELABS/edgelab")

from datetime import datetime, timedelta, timezone

import pytest

from edgelab.monitoring.logger import TradingLogger
from edgelab.signal import (
    create_signal_system, quick_signal_check, ConfluenceResult,
)
from edgelab.analysis.patterns import PatternType
from edgelab.regime.regime import MarketRegime, RegimeSnapshot
from edgelab.analysis.structure import MarketSnapshot, Trend
from edgelab.analysis.memory import PatternMemory
from edgelab.time.broker_time import BrokerTime
from edgelab.risk.account_state import AccountState
from edgelab.risk.drawdown_protector import DrawdownProtector


def _green_components(logger):
    """Return (analysis, regime, risk, news, memory) green components."""
    class _FakePattern:
        pattern_type = PatternType.HH_HL
        confidence = 1.0
        def to_dict(self):
            return {"pattern_type": self.pattern_type.value, "confidence": self.confidence}

    class _Struct:
        def analyze(self, b, now):
            return MarketSnapshot(trend=Trend.UP, trend_strength=0.9)

    class _PatternDet:
        def detect_all(self, b, now):
            return [_FakePattern()]

    class _Regime:
        def classify(self, b, now):
            s = RegimeSnapshot()
            s.regime = MarketRegime.TRENDING_UP
            s.confidence = 0.8
            s.components = {"volatility": {"level": "LOW"}}
            return s

    class _Anomaly:
        def fit_and_score(self, b, last):
            return 0.1

    class _News:
        def is_trading_allowed(self, sym, now):
            return True, "no events"

    analysis = {"structure": _Struct(), "anomaly": _Anomaly(),
                "memory": PatternMemory({}, logger)}
    regime = {"regime": _Regime()}
    bt = BrokerTime(offset="+3", dst=False)
    acct = AccountState(initial_balance=10000.0, broker_time=bt, logger=logger)
    risk = {"account_state": acct, "drawdown_protector": DrawdownProtector({}, acct, logger)}
    news = _News()
    return analysis, regime, risk, news, analysis["memory"], _PatternDet()


@pytest.fixture
def logger():
    return TradingLogger(name="sig.sys.test",
                         log_file=os.path.join(tempfile.gettempdir(), "sig_sys.log"))


def _base_time():
    return datetime(2026, 7, 1, tzinfo=timezone.utc)


def _mk(ts, o, h, l, c, v=1000.0):
    return {"timestamp": ts, "open": o, "high": h, "low": l, "close": c, "volume": v}


def _build_green_env(logger):
    import tests.test_confluence as tc
    return tc._build_green_env(logger)


class TestFactory:
    def test_create_signal_system_returns_detector_and_checker(self, logger):
        analysis, regime, risk, news, memory, patdet = _green_components(logger)
        cfg = {"signal": {"base_weight": 0.3, "structure_weight": 0.35,
                          "regime_weight": 0.35}}
        sys = create_signal_system(cfg, logger, analysis, regime, risk, news, memory,
                                    pattern_detector=patdet)
        assert "detector" in sys
        assert "checker" in sys
        sys["checker"]._pattern_detector = patdet

    def test_create_signal_system_disabled_returns_empty(self, logger):
        sys = create_signal_system({}, logger, {}, {}, {}, None, None)
        assert sys == {}

    def test_create_signal_system_disabled_when_signal_not_dict(self, logger):
        sys = create_signal_system({"signal": "on"}, logger, {}, {}, {}, None, None)
        assert sys == {}


class TestQuickCheck:
    def test_quick_check_runs_end_to_end(self, logger):
        checker, bars, now, sym = _build_green_env(logger)
        analysis, regime, risk, news, memory, patdet = _green_components(logger)
        cfg = {"signal": {"base_weight": 0.3, "structure_weight": 0.35, "regime_weight": 0.35}}
        res = quick_signal_check(bars, cfg, logger, analysis, regime, risk, news,
                                memory, current_time=now, symbol=sym,
                                account_balance=10000.0, current_price=bars[-1]["close"],
                                pattern_detector=patdet)
        assert isinstance(res, ConfluenceResult)
        assert res.all_passed is True

    def test_quick_check_disabled_is_skip(self, logger):
        analysis = {"structure": None, "anomaly": None, "memory": None}
        res = quick_signal_check([_mk(_base_time(), 1, 1, 1, 1)], {}, logger,
                                analysis, {}, {}, None, None, symbol="XAUUSD")
        assert res.all_passed is False
        assert "signal_system_disabled" in res.reasons

    def test_quick_check_crash_is_fail_open(self, logger):
        # analysis_system missing 'structure' -> checker.check raises inside;
        # quick_signal_check catches and returns a SKIP (fail-open)
        bars = [_mk(_base_time() + timedelta(hours=i), 2000 + i, 2001 + i, 1999 + i, 2000 + i)
                 for i in range(210)]
        res = quick_signal_check(bars, {"signal": {}}, logger, {}, {}, {}, None, None,
                                symbol="XAUUSD", current_time=bars[-1]["timestamp"])
        # must not raise; must report failure (never silent pass)
        assert res.all_passed is False
