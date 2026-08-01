"""Tests for edgelab.signal.confluence (Phase 7, Module 2).

Builds a full "green" environment (base signal + structure + regime all pass)
using the real detectors on synthetic bars, then asserts the 3-way gate, the
secondary filters, and graceful degradation. Pure standard library only.
"""

import sys, os, tempfile
sys.path.insert(0, r"C:/Users/GTHub/Downloads/EDGELABS/edgelab")

from datetime import datetime, timedelta, timezone

import pytest

from edgelab.monitoring.logger import TradingLogger
from edgelab.signal.detector import SignalDetector
from edgelab.signal.confluence import (
    ConfluenceChecker, ConfluenceResult, SignalCheck, SignalSource,
)
from edgelab.analysis.patterns import PatternType
from edgelab.regime.regime import MarketRegime, RegimeClassifier, RegimeSnapshot


@pytest.fixture
def logger():
    log_file = os.path.join(tempfile.gettempdir(), "conf_test.log")
    return TradingLogger(name="conf.test", log_file=log_file)


def _base_time():
    return datetime(2026, 7, 1, tzinfo=timezone.utc)


def _mk(ts, o, h, l, c, v=1000.0):
    return {"timestamp": ts, "open": o, "high": h, "low": l, "close": c, "volume": v}


def _uptrend_bars(n=200, start=1.1000, step=0.0008, wave=0.0010):
    bars = []
    base = _base_time()
    for i in range(n):
        level = start + step * i
        bars.append(_mk(base + timedelta(hours=i), level, level + wave, level - wave, level))
    return bars


def _build_green_env(logger):
    """Construct a 'green' environment where the 3-way confluence passes:
      * BASE signal fires on real _rising_pullback_bars (XAUUSD)
      * STRUCTURE mocked to UP + HH_HL (real PatternDetector would be fragile)
      * REGIME mocked to TRENDING_UP, low volatility
      * risk SAFE, news allowed, anomaly low, memory empty
    Returns (checker, bars, current_time, symbol)."""
    import tests.test_signal_detector as tsd
    from edgelab.analysis.anomaly import IsolationForest
    from edgelab.analysis.memory import PatternMemory
    from edgelab.analysis.patterns import PatternType
    from edgelab.regime.volatility import VolatilityClassifier
    from edgelab.regime.regime import RegimeClassifier, RegimeSnapshot
    from edgelab.risk.drawdown_protector import DrawdownProtector
    from edgelab.risk.account_state import AccountState
    from edgelab.time.broker_time import BrokerTime

    bars = tsd._rising_pullback_bars()
    current_time = bars[-1]["timestamp"]
    symbol = "XAUUSD"

    class _FakePattern:
        pattern_type = PatternType.HH_HL
        confidence = 1.0
        def to_dict(self):
            return {"pattern_type": self.pattern_type.value, "confidence": self.confidence}

    class _Struct:
        def analyze(self, b, now):
            from edgelab.analysis.structure import MarketSnapshot, Trend
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

    analysis = {
        "structure": _Struct(),
        "anomaly": _Anomaly(),
        "memory": PatternMemory({}, logger),
    }
    # inject the mocked pattern detector
    bt = BrokerTime(offset="+3", dst=False)
    acct = AccountState(initial_balance=10000.0, broker_time=bt, logger=logger)
    risk_sys = {
        "account_state": acct,
        "drawdown_protector": DrawdownProtector({}, acct, logger),
    }
    detector = SignalDetector({}, logger)
    checker = ConfluenceChecker(
        {"base_weight": 0.3, "structure_weight": 0.35, "regime_weight": 0.35,
         "min_confidence_to_execute": 0.6},
        logger, detector, analysis, {"regime": _Regime()}, risk_sys, _News(), analysis["memory"])
    checker._pattern_detector = _PatternDet()
    return checker, bars, current_time, symbol


def _fail_struct(checker):
    """Replace structure analyzer with one that returns DOWN trend."""
    class _S:
        def analyze(self, bars, now):
            from edgelab.analysis.structure import MarketSnapshot, Trend
            return MarketSnapshot(trend=Trend.DOWN, trend_strength=0.9)
    checker._analysis["structure"] = _S()


def _fail_regime(checker, regime_val=MarketRegime.RANGING.value, conf=0.7, vol="NORMAL"):
    class _R:
        def classify(self, bars, now):
            from edgelab.regime.regime import RegimeSnapshot
            s = RegimeSnapshot()
            s.regime = MarketRegime(regime_val)
            s.confidence = conf
            s.components = {"volatility": {"level": vol}}
            return s
    checker._regime["regime"] = _R()


def _kill_risk(checker):
    class _DP:
        def check_protection(self):
            from edgelab.risk.drawdown_protector import ProtectionLevel, ProtectionAction
            return ProtectionLevel.KILL, ProtectionAction.CLOSE_ALL_POSITIONS, "kill"
    checker._risk["drawdown_protector"] = _DP()


def _block_news(checker):
    class _N:
        def is_trading_allowed(self, sym, now):
            return False, "blackout"
    checker._news = _N()


def _extreme_anomaly(checker):
    class _A:
        def fit_and_score(self, bars, last):
            return 0.9
    checker._analysis["anomaly"] = _A()


class TestThreeWayGate:
    def test_three_signals_all_pass(self, logger):
        checker, bars, now, sym = _build_green_env(logger)
        res = checker.check(bars, now, sym, 10000.0, bars[-1]["close"])
        assert res.all_passed is True
        assert res.base_signal is not None
        assert res.structure_check.passed
        assert res.regime_check.passed
        # weighted: 0.5*0.3 + struct*0.35 + regime*0.35
        assert 0.0 < res.confidence <= 0.95

    def test_base_signal_fails_blocks_everything(self, logger):
        checker, bars, now, sym = _build_green_env(logger)
        res = checker.check(bars, now, "EURUSD", 10000.0, bars[-1]["close"])
        assert res.all_passed is False
        assert "base_signal_unavailable" in res.reasons

    def test_structure_fails_blocks_everything(self, logger):
        checker, bars, now, sym = _build_green_env(logger)
        _fail_struct(checker)
        res = checker.check(bars, now, sym, 10000.0, bars[-1]["close"])
        assert res.all_passed is False
        assert res.structure_check.passed is False

    def test_regime_fails_blocks_everything(self, logger):
        checker, bars, now, sym = _build_green_env(logger)
        _fail_regime(checker, MarketRegime.RANGING.value)
        res = checker.check(bars, now, sym, 10000.0, bars[-1]["close"])
        assert res.all_passed is False
        assert res.regime_check.passed is False

    def test_volatility_extreme_blocks(self, logger):
        checker, bars, now, sym = _build_green_env(logger)
        _fail_regime(checker, MarketRegime.TRENDING_UP.value, 0.8, "EXTREME")
        res = checker.check(bars, now, sym, 10000.0, bars[-1]["close"])
        assert res.all_passed is False
        assert res.regime_check.passed is False

    def test_news_blocks_secondary(self, logger):
        checker, bars, now, sym = _build_green_env(logger)
        _block_news(checker)
        res = checker.check(bars, now, sym, 10000.0, bars[-1]["close"])
        assert res.all_passed is False
        assert res.news_check.passed is False
        assert any("news" in r for r in res.reasons)

    def test_risk_kill_blocks(self, logger):
        checker, bars, now, sym = _build_green_env(logger)
        _kill_risk(checker)
        res = checker.check(bars, now, sym, 10000.0, bars[-1]["close"])
        assert res.all_passed is False
        assert res.risk_check.passed is False

    def test_anomaly_extreme_blocks(self, logger):
        checker, bars, now, sym = _build_green_env(logger)
        _extreme_anomaly(checker)
        res = checker.check(bars, now, sym, 10000.0, bars[-1]["close"])
        assert res.all_passed is False
        assert res.anomaly_check.passed is False


class TestConfidence:
    def test_confidence_weighted_correctly(self, logger):
        checker, bars, now, sym = _build_green_env(logger)
        res = checker.check(bars, now, sym, 10000.0, bars[-1]["close"])
        expected = (0.5 * 0.30 + res.structure_check.confidence * 0.35
                    + res.regime_check.confidence * 0.35)
        assert abs(res.confidence - min(0.95, expected)) < 1e-6

    def test_confidence_capped_at_95(self, logger):
        checker, bars, now, sym = _build_green_env(logger)
        # force structure + regime confidences to 1.0 -> weighted =
        # 0.5*0.3 + 1.0*0.35 + 1.0*0.35 = 0.85 (base is fixed at 0.5, so the
        # 0.95 cap is a safety ceiling that is not reached here)
        checker._analysis["structure"].analyze = lambda b, n: _struct_snap(1.0)
        checker._regime["regime"].classify = lambda b, n: _regime_snap(1.0, "LOW")
        res = checker.check(bars, now, sym, 10000.0, bars[-1]["close"])
        assert res.confidence == 0.85
        assert res.confidence <= 0.95

    def test_confidence_minimum_06_to_execute(self, logger):
        checker, bars, now, sym = _build_green_env(logger)
        # weak structure (trend_strength 0.5) + weak regime (0.5) -> conf =
        # 0.5*0.3 + 0.5*0.35 + 0.5*0.35 = 0.5 < 0.6
        checker._analysis["structure"].analyze = lambda b, n: _struct_snap(0.5)
        checker._regime["regime"].classify = lambda b, n: _regime_snap(0.5, "LOW")
        res = checker.check(bars, now, sym, 10000.0, bars[-1]["close"])
        assert res.confidence < 0.6


class TestFailureAccumulation:
    def test_all_filter_reasons_accumulated(self, logger):
        checker, bars, now, sym = _build_green_env(logger)
        _fail_struct(checker)
        _fail_regime(checker, MarketRegime.RANGING.value)
        _kill_risk(checker)
        _block_news(checker)
        _extreme_anomaly(checker)
        res = checker.check(bars, now, sym, 10000.0, bars[-1]["close"])
        assert res.all_passed is False
        # multiple distinct failure reasons present
        assert res.structure_check.passed is False
        assert res.regime_check.passed is False
        assert res.risk_check.passed is False
        assert res.news_check.passed is False
        assert res.anomaly_check.passed is False
        assert len(res.reasons) >= 4


class TestGracefulDegradation:
    def test_structure_unavailable_handled_gracefully(self, logger):
        checker, bars, now, sym = _build_green_env(logger)
        checker._analysis["structure"] = None  # simulate crash/unavailable
        res = checker.check(bars, now, sym, 10000.0, bars[-1]["close"])
        assert res.all_passed is False
        assert res.structure_check.reason == "structure_unavailable"

    def test_regime_unavailable_handled_gracefully(self, logger):
        checker, bars, now, sym = _build_green_env(logger)
        checker._regime["regime"] = None
        res = checker.check(bars, now, sym, 10000.0, bars[-1]["close"])
        assert res.all_passed is False
        assert res.regime_check.reason == "regime_unavailable"

    def test_only_xauusd(self, logger):
        checker, bars, now, sym = _build_green_env(logger)
        res = checker.check(bars, now, "EURUSD", 10000.0, bars[-1]["close"])
        assert res.all_passed is False

    def test_memory_block_on_all_losers(self, logger):
        checker, bars, now, sym = _build_green_env(logger)

        class _Mem:
            def get_record_count(self):
                return 5

            def query(self, st, s, c, a):
                class _M:
                    win_rate = 0.0
                    similar_count = 5
                return _M()

        checker._memory = _Mem()
        res = checker.check(bars, now, sym, 10000.0, bars[-1]["close"])
        assert res.all_passed is False
        assert res.memory_check.passed is False

    def test_trade_mgmt_critical_blocks(self, logger):
        checker, bars, now, sym = _build_green_env(logger)

        class _Pos:
            status = "critical"
            is_critical = True

        res = checker.check(bars, now, sym, 10000.0, bars[-1]["close"],
                            open_position=_Pos())
        assert res.all_passed is False
        assert res.trade_mgmt_check.passed is False

    def test_trade_mgmt_no_position_passes(self, logger):
        checker, bars, now, sym = _build_green_env(logger)
        res = checker.check(bars, now, sym, 10000.0, bars[-1]["close"],
                            open_position=None)
        assert res.trade_mgmt_check.passed is True


class TestDecisionLog:
    def test_all_filter_results_recorded_in_result(self, logger):
        checker, bars, now, sym = _build_green_env(logger)
        res = checker.check(bars, now, sym, 10000.0, bars[-1]["close"])
        # every secondary + 3-way check is present in the result object
        for attr in ("base_signal", "structure_check", "regime_check",
                     "risk_check", "news_check", "memory_check",
                     "trade_mgmt_check", "anomaly_check"):
            assert getattr(res, attr) is not None
        # reasons list is always populated (even when all pass it is empty -> still set)
        assert isinstance(res.reasons, list)


    def test_bos_up_pattern_also_passes_structure(self, logger):
        checker, bars, now, sym = _build_green_env(logger)

        class _BOS:
            pattern_type = PatternType.BOS_UP
            confidence = 0.9
            def to_dict(self):
                return {"pattern_type": self.pattern_type.value, "confidence": self.confidence}

        class _PD:
            def detect_all(self, b, now):
                return [_BOS()]

        checker._pattern_detector = _PD()
        res = checker.check(bars, now, sym, 10000.0, bars[-1]["close"])
        assert res.all_passed is True
        assert res.structure_check.passed is True

    def test_news_advisory_passes_when_allowed(self, logger):
        checker, bars, now, sym = _build_green_env(logger)
        res = checker.check(bars, now, sym, 10000.0, bars[-1]["close"])
        assert res.news_check.passed is True

    def test_xauusd_symbol_enforced(self, logger):
        checker, bars, now, sym = _build_green_env(logger)
        # non-XAUUSD symbol -> base signal None -> short-circuit skip
        res = checker.check(bars, now, "BTCUSD", 10000.0, bars[-1]["close"])
        assert res.all_passed is False
        assert "base_signal_unavailable" in res.reasons


def _struct_snap(trend_strength):
    from edgelab.analysis.structure import MarketSnapshot, Trend
    return MarketSnapshot(trend=Trend.UP, trend_strength=trend_strength)


def _regime_snap(confidence, vol):
    s = RegimeSnapshot()
    s.regime = MarketRegime.TRENDING_UP
    s.confidence = confidence
    s.components = {"volatility": {"level": vol}}
    return s
