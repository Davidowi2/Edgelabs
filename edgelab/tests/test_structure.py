"""Tests for edgelab.analysis.structure.StructureAnalyzer (Phase 5a, Module 1)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from edgelab.analysis.structure import (
    MarketSnapshot,
    StructureAnalyzer,
    SwingPoint,
    SwingType,
    Trend,
)


def _bar(ts, o, h, l, c, v=100.0):
    return {"timestamp": ts, "open": o, "high": h, "low": l, "close": c, "volume": v}


def _osc(trend_base, i, step, amp=0.0030, period=16):
    """One bar: sine zigzag around a rising/falling/flat trend.

    Period (16) is longer than the swing detection window (2*order+1 = 7) so
    genuine, separated local extrema form. The trend term biases consecutive
    swings to rise (uptrend), fall (downtrend), or stay flat (range).
    """
    import math
    trend = trend_base + i * step
    wave = amp * math.sin(2 * math.pi * i / period)
    high = trend + abs(wave) + 0.0003
    low = trend - abs(wave) - 0.0003
    close = trend + wave
    return high, low, close


def _uptrend_bars():
    bars = []
    base = datetime(2026, 7, 1, 0, 0, tzinfo=timezone.utc)
    for i in range(80):
        h, l, c = _osc(1.1000, i, 0.00015)
        bars.append(_bar(base + timedelta(hours=i), c, h, l, c))
    return bars


def _downtrend_bars():
    bars = []
    base = datetime(2026, 7, 1, 0, 0, tzinfo=timezone.utc)
    for i in range(80):
        h, l, c = _osc(1.1100, i, -0.00015)
        bars.append(_bar(base + timedelta(hours=i), c, h, l, c))
    return bars


def _series():
    bars = []
    base = datetime(2026, 7, 1, 0, 0, tzinfo=timezone.utc)
    for i in range(80):
        h, l, c = _osc(1.1000, i, 0.0)
        bars.append(_bar(base + timedelta(hours=i), c, h, l, c))
    return bars


@pytest.fixture
def logger():
    from edgelab.monitoring.logger import TradingLogger
    import tempfile, os
    return TradingLogger(name="st.test", log_file=os.path.join(tempfile.gettempdir(), "st.log"))


class TestTrend:
    def test_detect_uptrend(self, logger):
        sa = StructureAnalyzer({}, logger)
        bars = _uptrend_bars()
        snap = sa.analyze(bars, bars[-1]["timestamp"])
        assert snap.trend == Trend.UP

    def test_detect_downtrend(self, logger):
        sa = StructureAnalyzer({}, logger)
        bars = _downtrend_bars()
        snap = sa.analyze(bars, bars[-1]["timestamp"])
        assert snap.trend == Trend.DOWN

    def test_detect_range(self, logger):
        sa = StructureAnalyzer({}, logger)
        bars = _series()
        snap = sa.analyze(bars, bars[-1]["timestamp"])
        assert snap.trend == Trend.RANGE


class TestStrength:
    def test_trend_strength_scales_with_consistency(self, logger):
        sa = StructureAnalyzer({}, logger)
        up = sa.analyze(_uptrend_bars(), _uptrend_bars()[-1]["timestamp"])
        rng = sa.analyze(_series(), _series()[-1]["timestamp"])
        assert up.trend_strength >= rng.trend_strength
        assert 0.0 <= up.trend_strength <= 1.0


class TestSwings:
    def test_swing_high_detection(self, logger):
        sa = StructureAnalyzer({}, logger)
        bars = _series()
        t = bars[10]["timestamp"]
        bars[10] = _bar(t, 1.1000, 1.1300, 1.0990, 1.1000)
        snap = sa.analyze(bars, bars[-1]["timestamp"])
        assert any(s.type == SwingType.SWING_HIGH for s in snap.swing_highs)

    def test_swing_low_detection(self, logger):
        sa = StructureAnalyzer({}, logger)
        bars = _series()
        t = bars[10]["timestamp"]
        bars[10] = _bar(t, 1.1000, 1.1010, 1.0700, 1.1000)
        snap = sa.analyze(bars, bars[-1]["timestamp"])
        assert any(s.type == SwingType.SWING_LOW for s in snap.swing_lows)


class TestLevels:
    def test_key_resistance_nearest_above(self, logger):
        sa = StructureAnalyzer({}, logger)
        bars = _series()
        bars[10] = _bar(bars[10]["timestamp"], 1.1000, 1.1300, 1.0990, 1.1000)
        bars[20] = _bar(bars[20]["timestamp"], 1.1000, 1.1250, 1.0990, 1.1000)
        snap = sa.analyze(bars, bars[-1]["timestamp"])
        assert snap.key_resistance is not None
        assert snap.key_resistance > bars[-1]["close"]

    def test_key_support_nearest_below(self, logger):
        sa = StructureAnalyzer({}, logger)
        bars = _series()
        bars[10] = _bar(bars[10]["timestamp"], 1.1000, 1.1010, 1.0700, 1.1000)
        bars[20] = _bar(bars[20]["timestamp"], 1.1000, 1.1010, 1.0750, 1.1000)
        snap = sa.analyze(bars, bars[-1]["timestamp"])
        assert snap.key_support is not None
        assert snap.key_support < bars[-1]["close"]

    def test_no_key_resistance_when_all_swings_below_price(self, logger):
        sa = StructureAnalyzer({}, logger)
        # last bar prints a new high above all swings -> no resistance above it
        bars = _series()
        bars[-1] = _bar(bars[-1]["timestamp"], 1.1500, 1.1510, 1.1490, 1.1500)
        snap = sa.analyze(bars, bars[-1]["timestamp"])
        assert snap.key_resistance is None

    def test_no_key_support_when_all_swings_above_price(self, logger):
        sa = StructureAnalyzer({}, logger)
        # last bar prints a new low below all swings -> no support below it
        bars = _series()
        bars[-1] = _bar(bars[-1]["timestamp"], 1.0500, 1.0510, 1.0490, 1.0500)
        snap = sa.analyze(bars, bars[-1]["timestamp"])
        assert snap.key_support is None


class TestStatus:
    def test_get_status_returns_serializable_dict(self, logger):
        sa = StructureAnalyzer({}, logger)
        snap = sa.analyze(_series(), _series()[-1]["timestamp"])
        d = sa.get_status()
        assert isinstance(d, dict)
        assert "trend" in d and "trend_strength" in d


class TestEdge:
    def test_analyze_with_insufficient_bars(self, logger):
        sa = StructureAnalyzer({"lookback_bars": 200}, logger)
        bars = _series()[:10]
        snap = sa.analyze(bars, bars[-1]["timestamp"])
        assert snap.trend == Trend.RANGE

    def test_analyze_with_empty_bars(self, logger):
        sa = StructureAnalyzer({}, logger)
        snap = sa.analyze([], datetime(2026, 7, 1, tzinfo=timezone.utc))
        assert snap.trend == Trend.RANGE


class TestIndexErrorFix:
    """Regression tests for the len(highs) != len(lows) IndexError (Phase 6, Module 0)."""

    def _mismatched_bars(self):
        highs = [1.099908, 1.101461, 1.099042, 1.10122, 1.100195, 1.098056,
                 1.100879, 1.099595, 1.101299, 1.100673, 1.098005, 1.099974,
                 1.10147, 1.098976, 1.099301, 1.101482]
        lows = [1.098526, 1.099326, 1.097565, 1.098285, 1.097588, 1.09616,
                1.099718, 1.097955, 1.099283, 1.097807, 1.096786, 1.097872,
                1.099057, 1.096881, 1.096672, 1.099401]
        base = datetime(2026, 7, 1, tzinfo=timezone.utc)
        bars = []
        for i, (h, l) in enumerate(zip(highs, lows)):
            c = (h + l) / 2
            bars.append({"timestamp": base + timedelta(hours=i),
                         "open": c, "high": h, "low": l, "close": c})
        return bars

    def test_analyze_with_different_swing_counts_does_not_raise(self, logger):
        """10+ bars produce 3 swing highs but only 2 swing lows; before the
        fix analyze() raised IndexError (lows[k] out of range). After the fix
        it must return a valid MarketSnapshot without raising."""
        sa = StructureAnalyzer({"swing_order": 3}, logger)
        bars = self._mismatched_bars()
        # must not raise
        snap = sa.analyze(bars, bars[-1]["timestamp"])
        # valid enum trend + bounded strength
        from edgelab.analysis.structure import Trend
        assert snap.trend in (Trend.UP, Trend.DOWN, Trend.RANGE)
        assert 0.0 <= snap.trend_strength <= 1.0

    def test_analyze_with_extra_high_count_returns_snapshot(self, logger):
        sa = StructureAnalyzer({"swing_order": 3}, logger)
        bars = self._mismatched_bars()
        snap = sa.analyze(bars, bars[-1]["timestamp"])
        assert isinstance(snap.trend_strength, float)
        assert 0.0 <= snap.trend_strength <= 1.0
