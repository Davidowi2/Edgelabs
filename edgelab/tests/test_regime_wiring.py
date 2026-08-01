"""Tests for edgelab.regime (Phase 6, Module 3): factory + quick_regime_check + startup integration.

The factory builds the volatility + regime classifiers once. quick_regime_check()
is the single call Phase 7 will use. Startup validation includes a regime check.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from edgelab.monitoring.logger import TradingLogger
from edgelab.regime import (
    MarketRegime,
    RegimeClassifier,
    RegimeSnapshot,
    VolatilityClassifier,
    VolatilitySnapshot,
    create_regime_system,
    quick_regime_check,
)
from edgelab.regime.regime import RegimeClassifier as _RC
from edgelab.regime.volatility import VolatilityClassifier as _VC


def _bar(ts, o, h, l, c, v=100.0):
    return {"timestamp": ts, "open": o, "high": h, "low": l, "close": c, "volume": v}


def _uptrend_bars(n=200, start=1.1000, step=0.0008):
    bars = []
    base = datetime(2026, 7, 1, tzinfo=timezone.utc)
    c = start
    for i in range(n):
        c = c + step
        wave = 0.0010
        bars.append(_bar(base + timedelta(hours=i), c, c + wave, c - wave, c))
    return bars


@pytest.fixture
def logger():
    import tempfile, os
    return TradingLogger(name="rw.test", log_file=os.path.join(tempfile.gettempdir(), "rw.test.log"))


class TestFactory:
    def test_create_regime_system_with_valid_config(self, logger):
        sys = create_regime_system({"regime": {}}, logger)
        assert isinstance(sys.get("volatility"), VolatilityClassifier)
        assert isinstance(sys.get("regime"), RegimeClassifier)

    def test_create_regime_system_auto_creates_volatility(self, logger):
        vc = VolatilityClassifier({}, logger)
        sys = create_regime_system({"regime": {}}, logger, volatility_classifier=vc)
        # provided classifier is reused
        assert sys["volatility"] is vc
        assert isinstance(sys["regime"], RegimeClassifier)

    def test_create_regime_system_with_missing_config(self, logger):
        sys = create_regime_system({}, logger)
        # never raises; malformed config -> empty dict
        assert sys == {}

    def test_create_regime_system_never_raises(self, logger):
        for cfg in [None, {}, {"regime": None}, {"regime": "bad"}]:
            try:
                create_regime_system(cfg, logger)
            except Exception as exc:  # noqa: BLE001
                pytest.fail(f"create_regime_system raised on {cfg!r}: {exc}")


class TestQuickCheck:
    def test_quick_regime_check_returns_complete_dict(self, logger):
        bars = _uptrend_bars()
        out = quick_regime_check(bars, bars[-1]["timestamp"], structure_trend="UP")
        for k in ("regime", "confidence", "volatility_level", "adx", "reasoning"):
            assert k in out
        assert isinstance(out["confidence"], float)

    def test_quick_regime_check_auto_creates_system(self, logger):
        bars = _uptrend_bars()
        out = quick_regime_check(bars, bars[-1]["timestamp"], structure_trend="UP")
        assert out["regime"] in [r.value for r in MarketRegime]


class TestStartupIntegration:
    def test_startup_check_includes_regime_validation(self, logger):
        from edgelab.monitoring.startup_check import StartupValidator

        config = {
            "broker": {"timezone_offset": "+3"},
            "internal_risk": {"risk_per_trade_pct": 0.01, "daily_loss_lock_pct": 0.02,
                              "total_dd_lock_pct": 0.05},
            "risk": {"initial_balance": 10000.0, "firm_preset": "blueberry_1step"},
            "news_filter": {"currency_map": {"EURUSD": ["EUR", "USD"]}},
            "analysis": {},
            "regime": {},
            "account": {"type": "demo", "confirmed": True},
            "inactivity": {"last_trade_timestamp": "2026-07-01T00:00:00Z"},
        }
        v = StartupValidator(config, logger)
        labels = [c[0] for c in v._checks_run()]
        assert "regime_config" in labels
        result = v.run_all_checks()
        assert result.passed is True

    def test_regime_integration_with_analysis(self, logger):
        """Regime output complements (does not replace) the analysis output."""
        from edgelab.analysis import full_analysis, create_analysis_system
        from edgelab.time.broker_time import BrokerTime

        bt = BrokerTime(offset="+3", dst=False)
        sys = create_analysis_system({"analysis": {}}, logger, bt)
        bars = _uptrend_bars()
        analysis = full_analysis(bars, "EURUSD", bars[-1]["timestamp"],
                                 analysis_system=sys)
        regime_out = quick_regime_check(bars, bars[-1]["timestamp"], structure_trend="UP")
        # both present and structurally compatible
        assert "structure" in analysis
        assert regime_out["regime"] in [r.value for r in MarketRegime]
