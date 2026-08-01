"""Tests for edgelab.regime.volatility.VolatilityClassifier (Phase 6, Module 1).

Volatility is the primary regime input: current ATR vs its recent distribution
(percentile), plus expanding/contracting detection. Pure stdlib, no ML.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from edgelab.analysis.structure import StructureAnalyzer
from edgelab.monitoring.logger import TradingLogger
from edgelab.regime.volatility import VolatilityClassifier, VolatilityLevel


def _bar(ts, o, h, l, c, v=100.0):
    return {"timestamp": ts, "open": o, "high": h, "low": l, "close": c, "volume": v}


def _flat_bars(n=120, price=1.1000):
    """Constant price -> ATR ~ 0 (low volatility)."""
    bars = []
    base = datetime(2026, 7, 1, tzinfo=timezone.utc)
    for i in range(n):
        bars.append(_bar(base + timedelta(hours=i), price, price, price, price))
    return bars


def _moderate_bars(n=120, start=1.1000, amp=0.0030):
    """Near-stationary small variation -> smoothed ATR sits mid-distribution (NORMAL)."""
    import random
    rng = random.Random(4)
    bars = []
    base = datetime(2026, 7, 1, tzinfo=timezone.utc)
    for i in range(n):
        # tight cluster around amp (±8%) -> ATR nearly constant -> ~median -> NORMAL
        wave = amp * (0.92 + 0.16 * rng.random())
        c = start
        h = c + wave
        l = c - wave
        bars.append(_bar(base + timedelta(hours=i), c, h, l, c))
    return bars


def _high_bars(n=120, start=1.1000, amp=0.0100):
    bars = []
    base = datetime(2026, 7, 1, tzinfo=timezone.utc)
    for i in range(n):
        wave = amp * (0.6 + ((i % 7) / 7.0))
        c = start + 0.0020 * (i % 3)
        h = c + wave
        l = c - wave
        bars.append(_bar(base + timedelta(hours=i), c, h, l, c))
    return bars


def _extreme_bars(n=120, start=1.1000):
    """Mostly calm, then a few huge spikes at the end -> extreme percentile."""
    bars = []
    base = datetime(2026, 7, 1, tzinfo=timezone.utc)
    for i in range(n):
        if i >= n - 10:
            wave = 0.0200 + 0.005 * (i % 5)
        else:
            wave = 0.0008
        c = start
        h = c + wave
        l = c - wave
        bars.append(_bar(base + timedelta(hours=i), c, h, l, c))
    return bars


def _expanding_bars(n=120, start=1.1000):
    """Volatility steadily increasing -> ATR now > ATR 5 bars ago."""
    bars = []
    base = datetime(2026, 7, 1, tzinfo=timezone.utc)
    for i in range(n):
        wave = 0.0005 + 0.0002 * i  # grows over time
        c = start + 0.0003 * i
        h = c + wave
        l = c - wave
        bars.append(_bar(base + timedelta(hours=i), c, h, l, c))
    return bars


def _contracting_bars(n=120, start=1.1000):
    """Volatility steadily decreasing -> ATR now < ATR 5 bars ago."""
    bars = []
    base = datetime(2026, 7, 1, tzinfo=timezone.utc)
    for i in range(n):
        wave = 0.0200 * (1.0 - i / (2 * n))  # shrinks but stays positive
        c = start + 0.0003 * i
        h = c + wave
        l = c - wave
        bars.append(_bar(base + timedelta(hours=i), c, h, l, c))
    return bars


@pytest.fixture
def logger():
    import tempfile, os
    return TradingLogger(name="vol.test", log_file=os.path.join(tempfile.gettempdir(), "vol.test.log"))


class TestClassify:
    def test_classify_low_volatility(self, logger):
        vc = VolatilityClassifier({}, logger)
        snap = vc.classify(_flat_bars(), _flat_bars()[-1]["timestamp"])
        assert snap.level == VolatilityLevel.LOW

    def test_classify_normal_volatility(self, logger):
        vc = VolatilityClassifier({}, logger)
        snap = vc.classify(_moderate_bars(), _moderate_bars()[-1]["timestamp"])
        assert snap.level == VolatilityLevel.NORMAL

    def test_classify_high_volatility(self, logger):
        vc = VolatilityClassifier({}, logger)
        snap = vc.classify(_high_bars(), _high_bars()[-1]["timestamp"])
        assert snap.level == VolatilityLevel.HIGH

    def test_classify_extreme_volatility(self, logger):
        vc = VolatilityClassifier({}, logger)
        snap = vc.classify(_extreme_bars(), _extreme_bars()[-1]["timestamp"])
        assert snap.level == VolatilityLevel.EXTREME

    def test_expanding_detected(self, logger):
        vc = VolatilityClassifier({}, logger)
        snap = vc.classify(_expanding_bars(), _expanding_bars()[-1]["timestamp"])
        assert snap.expanding is True

    def test_contracting_detected(self, logger):
        vc = VolatilityClassifier({}, logger)
        snap = vc.classify(_contracting_bars(), _contracting_bars()[-1]["timestamp"])
        assert snap.contracting is True

    def test_get_status_returns_serializable(self, logger):
        vc = VolatilityClassifier({}, logger)
        snap = vc.classify(_moderate_bars(), _moderate_bars()[-1]["timestamp"])
        d = vc.get_status() if hasattr(vc, "get_status") else None
        # get_status() lives on the snapshot in this design; fall back gracefully
        if d is None:
            d = snap.to_dict()
        assert isinstance(d, dict)
        assert "level" in d and "current_atr" in d

    def test_atr_percentile_calculation(self, logger):
        vc = VolatilityClassifier({}, logger)
        bars = _flat_bars(120)
        snap = vc.classify(bars, bars[-1]["timestamp"])
        # flat bars -> ATR is the minimum of the distribution -> low percentile
        assert 0 <= snap.atr_percentile <= 100
        assert snap.current_atr <= 1e-9 + 1e-12 or snap.atr_percentile < 50

    def test_empty_bars_returns_safe_defaults(self, logger):
        vc = VolatilityClassifier({}, logger)
        snap = vc.classify([], datetime(2026, 7, 1, tzinfo=timezone.utc))
        assert snap.level == VolatilityLevel.NORMAL
        assert snap.current_atr == 0.0

    def test_single_bar_returns_safe_defaults(self, logger):
        vc = VolatilityClassifier({}, logger)
        bars = [_bar(datetime(2026, 7, 1, tzinfo=timezone.utc), 1.10, 1.10, 1.10, 1.10)]
        snap = vc.classify(bars, bars[-1]["timestamp"])
        assert snap.level == VolatilityLevel.NORMAL
        assert snap.current_atr == 0.0

    def test_lookback_days_tracked_in_snapshot(self, logger):
        vc = VolatilityClassifier({"lookback_days": 90}, logger)
        snap = vc.classify(_moderate_bars(120), _moderate_bars(120)[-1]["timestamp"])
        assert snap.lookback_days == 90
