"""Tests for edgelab.regime.regime.RegimeClassifier (Phase 6, Module 2).

Combines volatility + ADX + structure into a market-regime label. Rule-based,
not adaptive. EXTREME volatility overrides to VOLATILE regardless of ADX.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from edgelab.monitoring.logger import TradingLogger
from edgelab.regime.regime import MarketRegime, RegimeClassifier
from edgelab.regime.volatility import VolatilityClassifier


def _bar(ts, o, h, l, c, v=100.0):
    return {"timestamp": ts, "open": o, "high": h, "low": l, "close": c, "volume": v}


def _uptrend_bars(n=200, start=1.1000, step=0.0008, wave=0.0010):
    bars = []
    base = datetime(2026, 7, 1, tzinfo=timezone.utc)
    for i in range(n):
        level = start + step * i  # whole level rises -> real uptrend
        bars.append(_bar(base + timedelta(hours=i), level, level + wave, level - wave, level))
    return bars


def _downtrend_bars(n=200, start=1.1200, step=0.0008, wave=0.0010):
    bars = []
    base = datetime(2026, 7, 1, tzinfo=timezone.utc)
    for i in range(n):
        level = start - step * i
        bars.append(_bar(base + timedelta(hours=i), level, level + wave, level - wave, level))
    return bars


def _range_bars(n=200, mid=1.1000, wave=0.0006):
    bars = []
    base = datetime(2026, 7, 1, tzinfo=timezone.utc)
    for i in range(n):
        # stationary, no directional drift, small constant width -> low ADX, low vol
        bars.append(_bar(base + timedelta(hours=i), mid, mid + wave, mid - wave, mid))
    return bars


def _extreme_bars(n=200, mid=1.1000):
    bars = []
    base = datetime(2026, 7, 1, tzinfo=timezone.utc)
    for i in range(n):
        if i >= n - 20:
            wave = 0.0250 + 0.004 * (i % 6)
        else:
            wave = 0.0008
        c = mid
        bars.append(_bar(base + timedelta(hours=i), c, c + wave, c - wave, c))
    return bars


def _make_classifier(logger, vol_cfg=None):
    vc = VolatilityClassifier(vol_cfg or {}, logger)
    return RegimeClassifier({}, logger, vc)


@pytest.fixture
def logger():
    import tempfile, os
    return TradingLogger(name="reg.test", log_file=os.path.join(tempfile.gettempdir(), "reg.test.log"))


class TestClassify:
    def test_classify_trending_up_with_structure(self, logger):
        rc = _make_classifier(logger)
        bars = _uptrend_bars()
        snap = rc.classify(bars, bars[-1]["timestamp"], structure_trend="UP")
        assert snap.regime == MarketRegime.TRENDING_UP

    def test_classify_trending_down_with_structure(self, logger):
        rc = _make_classifier(logger)
        bars = _downtrend_bars()
        snap = rc.classify(bars, bars[-1]["timestamp"], structure_trend="DOWN")
        assert snap.regime == MarketRegime.TRENDING_DOWN

    def test_classify_ranging(self, logger):
        rc = _make_classifier(logger)
        bars = _range_bars()
        snap = rc.classify(bars, bars[-1]["timestamp"], structure_trend="RANGE")
        assert snap.regime == MarketRegime.RANGING

    def test_classify_volatile_extreme(self, logger):
        rc = _make_classifier(logger)
        bars = _extreme_bars()
        # even with UP structure, extreme volatility forces VOLATILE
        snap = rc.classify(bars, bars[-1]["timestamp"], structure_trend="UP")
        assert snap.regime == MarketRegime.VOLATILE

    def test_classify_volatile_high_no_trend(self, logger):
        rc = _make_classifier(logger)
        bars = _high_for_volatile()
        # HIGH volatility + ADX < 20 -> VOLATILE
        snap = rc.classify(bars, bars[-1]["timestamp"], structure_trend="RANGE")
        assert snap.regime == MarketRegime.VOLATILE

    def test_classify_default_safe(self, logger):
        rc = _make_classifier(logger)
        bars = _range_bars()
        # ambiguous: no structure provided, low ADX + low volatility -> RANGING.
        # Per spec rule: adx < ranging_adx AND LOW/NORMAL vol -> RANGING conf 0.7
        snap = rc.classify(bars, bars[-1]["timestamp"])
        assert snap.regime == MarketRegime.RANGING
        assert snap.confidence <= 0.95

    def test_strong_trend_higher_confidence(self, logger):
        rc = _make_classifier(logger)
        bars = _uptrend_bars(220)
        snap = rc.classify(bars, bars[-1]["timestamp"], structure_trend="UP")
        # strong trend -> confidence 0.8 (capped at 0.95)
        assert snap.confidence >= 0.8
        assert snap.confidence <= 0.95

    def test_calculate_adx_trending(self, logger):
        rc = _make_classifier(logger)
        bars = _uptrend_bars()
        adx = rc._calculate_adx(bars, 14)
        assert adx >= 25

    def test_calculate_adx_ranging(self, logger):
        rc = _make_classifier(logger)
        bars = _range_bars()
        adx = rc._calculate_adx(bars, 14)
        assert adx < 20

    def test_adx_insufficient_data(self, logger):
        rc = _make_classifier(logger)
        bars = _uptrend_bars(10)  # too few for ADX(14)
        adx = rc._calculate_adx(bars, 14)
        assert adx == 0.0
        snap = rc.classify(bars, bars[-1]["timestamp"], structure_trend="RANGE")
        assert snap.regime == MarketRegime.RANGING

    def test_confidence_capped_at_95(self, logger):
        rc = _make_classifier(logger)
        bars = _uptrend_bars(220)
        snap = rc.classify(bars, bars[-1]["timestamp"], structure_trend="UP")
        assert snap.confidence <= 0.95
        assert snap.confidence == 0.95 or snap.confidence < 0.95

    def test_get_status_returns_serializable(self, logger):
        rc = _make_classifier(logger)
        bars = _uptrend_bars()
        snap = rc.classify(bars, bars[-1]["timestamp"], structure_trend="UP")
        d = snap.to_dict() if hasattr(snap, "to_dict") else rc.get_status()
        assert isinstance(d, dict)
        assert "regime" in d and "confidence" in d

    def test_reasoning_includes_components(self, logger):
        rc = _make_classifier(logger)
        bars = _uptrend_bars()
        snap = rc.classify(bars, bars[-1]["timestamp"], structure_trend="UP")
        assert "ADX" in snap.reasoning
        assert "volatility" in snap.reasoning.lower()
        assert "structure" in snap.reasoning.lower()


def _high_for_volatile(n=200, mid=1.1000):
    """Moderately wide, non-directional swings -> HIGH volatility, low ADX."""
    bars = []
    base = datetime(2026, 7, 1, tzinfo=timezone.utc)
    for i in range(n):
        wave = 0.0060 + 0.001 * (i % 5)
        c = mid + 0.0030 * ((-1) ** i)
        bars.append(_bar(base + timedelta(hours=i), c, c + wave, c - wave, c))
    return bars
