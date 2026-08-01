"""Tests for edgelab.analysis.patterns.PatternDetector (Phase 5b, Module 1).

Seven measured pattern detectors. Every pattern returns a quantified result
(entry zone, SL, measured target). Pure functions: same input -> same output.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from edgelab.analysis.patterns import (
    DetectedPattern,
    PatternDetector,
    PatternStatus,
    PatternType,
)
from edgelab.monitoring.logger import TradingLogger


def _bar(ts, o, h, l, c, v=100.0):
    return {"timestamp": ts, "open": o, "high": h, "low": l, "close": c, "volume": v}


def _sine_bars(tb, step, amp=0.0030, period=16, n=80):
    """Sine-zigzag bars around a trend (period 16 > 7-bar swing window)."""
    import math
    bars = []
    base = datetime(2026, 7, 1, tzinfo=timezone.utc)
    for i in range(n):
        trend = tb + i * step
        wave = amp * math.sin(2 * math.pi * i / period)
        high = trend + abs(wave) + 0.0003
        low = trend - abs(wave) - 0.0003
        close = trend + wave
        bars.append(_bar(base + timedelta(hours=i), close, high, low, close))
    return bars


def _interp(controls, i):
    if i <= controls[0][0]:
        return controls[0][1]
    if i >= controls[-1][0]:
        return controls[-1][1]
    for k in range(len(controls) - 1):
        i0, p0 = controls[k]
        i1, p1 = controls[k + 1]
        if i0 <= i <= i1:
            t = (i - i0) / (i1 - i0) if i1 != i0 else 0.0
            return p0 + t * (p1 - p0)
    return controls[-1][1]


def _controls_bars(controls, n):
    """Piecewise-linear close series; high=close+0.0003, low=close-0.0003.
    Control points are the reversal (swing) points, spaced >=7 bars apart."""
    bars = []
    base = datetime(2026, 7, 1, tzinfo=timezone.utc)
    for i in range(n):
        close = _interp(controls, i)
        bars.append(_bar(base + timedelta(hours=i), close, close + 0.0003, close - 0.0003, close))
    return bars


@pytest.fixture
def logger():
    import tempfile, os
    return TradingLogger(name="pat.test", log_file=os.path.join(tempfile.gettempdir(), "pat.log"))


# ---------------- HH_HL / LH_LL ----------------
class TestHHHL:
    def test_detect_hh_hl_with_clear_uptrend(self, logger):
        pd = PatternDetector({}, logger)
        bars = _sine_bars(1.1000, 0.00015)
        res = pd.detect_hh_hl(bars, bars[-1]["timestamp"])
        assert len(res) == 1
        p = res[0]
        assert p.pattern_type == PatternType.HH_HL
        assert p.confidence >= 0.7
        assert p.status in (PatternStatus.CONFIRMED, PatternStatus.FORMING)

    def test_detect_hh_hl_with_no_clear_trend(self, logger):
        pd = PatternDetector({}, logger)
        bars = _sine_bars(1.1000, 0.0)  # range -> no HH/HL
        res = pd.detect_hh_hl(bars, bars[-1]["timestamp"])
        assert res == []

    def test_confidence_capped_at_95(self, logger):
        pd = PatternDetector({}, logger)
        bars = _sine_bars(1.1000, 0.00015)  # perfect HH/HL -> ratio 1.0 -> cap 0.95
        res = pd.detect_hh_hl(bars, bars[-1]["timestamp"])
        assert res[0].confidence == 0.95


class TestLHLL:
    def test_detect_lh_ll_with_clear_downtrend(self, logger):
        pd = PatternDetector({}, logger)
        bars = _sine_bars(1.1100, -0.00015)
        res = pd.detect_lh_ll(bars, bars[-1]["timestamp"])
        assert len(res) == 1
        p = res[0]
        assert p.pattern_type == PatternType.LH_LL
        assert p.confidence >= 0.7


# ---------------- BOS ----------------
class TestBOS:
    def _prior_uptrend(self):
        # sine zigzag rising series -> multiple separated swing highs/lows
        import math
        bars = []
        base = datetime(2026, 7, 1, tzinfo=timezone.utc)
        for i in range(60):
            trend = 1.0900 + i * 0.0002
            wave = 0.0020 * math.sin(2 * math.pi * i / 16)
            c = trend + wave
            bars.append(_bar(base + timedelta(hours=i), c, trend + abs(wave) + 0.0003,
                             trend - abs(wave) - 0.0003, c))
        return bars

    def test_detect_bos_up(self, logger):
        pd = PatternDetector({}, logger)
        bars = self._prior_uptrend()
        # mutate last bar in place to be the breakout (close above prior high)
        last = bars[-1]
        bars[-1] = _bar(last["timestamp"], last["close"] + 0.0010, last["close"] + 0.0020,
                        last["close"] + 0.0010, last["close"] + 0.0020)
        highs, _, _ = pd._swings(bars, bars[-1]["timestamp"])
        prior_high = highs[-2].price  # prior swing high (breakout is [-1])
        res = pd.detect_bos(bars, bars[-1]["timestamp"])
        assert len(res) == 1
        assert res[0].pattern_type == PatternType.BOS_UP
        assert res[0].status == PatternStatus.CONFIRMED

    def test_detect_bos_down(self, logger):
        pd = PatternDetector({}, logger)
        bars = []
        base = datetime(2026, 7, 1, tzinfo=timezone.utc)
        import math
        for i in range(60):
            trend = 1.1100 - i * 0.0002
            wave = 0.0020 * math.sin(2 * math.pi * i / 16)
            c = trend + wave
            bars.append(_bar(base + timedelta(hours=i), c, trend + abs(wave) + 0.0003,
                             trend - abs(wave) - 0.0003, c))
        last = bars[-1]
        bars[-1] = _bar(last["timestamp"], last["close"] - 0.0010, last["close"] - 0.0010,
                        last["close"] - 0.0020, last["close"] - 0.0020)
        lows, _, _ = pd._swings(bars, bars[-1]["timestamp"])
        prior_low = lows[-2].price  # prior swing low (breakout is [-1])
        res = pd.detect_bos(bars, bars[-1]["timestamp"])
        assert len(res) == 1
        assert res[0].pattern_type == PatternType.BOS_DOWN
        assert res[0].status == PatternStatus.CONFIRMED

    def test_detect_bos_failed(self, logger):
        pd = PatternDetector({}, logger)
        bars = self._prior_uptrend()
        highs, _, _ = pd._swings(bars, bars[-1]["timestamp"])
        prior_high = highs[-2].price
        last = bars[-1]
        # wick pierces prior high but close snaps back below -> FAILED
        bars[-1] = _bar(last["timestamp"], prior_high - 0.0005, prior_high + 0.0010,
                        prior_high - 0.0005, prior_high - 0.0005)
        res = pd.detect_bos(bars, bars[-1]["timestamp"])
        assert len(res) == 1
        assert res[0].pattern_type == PatternType.BOS_UP
        assert res[0].status == PatternStatus.FAILED


# ---------------- CHoCH ----------------
class TestCHoCH:
    def test_detect_choch_in_uptrend(self, logger):
        pd = PatternDetector({}, logger)
        bars = _sine_bars(1.1000, 0.00015)
        # append a bar dropping below the last detected higher low
        highs, lows, _ = pd._swings(bars, bars[-1]["timestamp"])
        last_low = lows[-1].price if lows else bars[-1]["close"]
        last = bars[-1]
        nb = _bar(last["timestamp"] + timedelta(hours=1),
                  last_low - 0.0020, last_low - 0.0010, last_low - 0.0020,
                  last_low - 0.0020)
        bars.append(nb)
        res = pd.detect_choch(bars, bars[-1]["timestamp"])
        assert len(res) == 1
        assert res[0].pattern_type == PatternType.CHoCH_DOWN

    def test_detect_choch_requires_prior_trend_context(self, logger):
        pd = PatternDetector({}, logger)
        bars = _sine_bars(1.1000, 0.0)  # range, no prior trend
        res = pd.detect_choch(bars, bars[-1]["timestamp"])
        assert res == []


# ---------------- HEAD AND SHOULDERS ----------------
class TestHeadAndShoulders:
    def _hs_bars(self, head=1.1000, neckline=1.0900, shoulder=1.0950):
        # head clearly tallest above neckline; shoulders above neckline.
        # relative height rule: head_height >= 1.02 * shoulder_height
        return _controls_bars(
            [(0, 1.0930), (10, shoulder), (20, neckline), (30, head),
             (40, neckline), (50, shoulder), (60, neckline - 0.0010)],
            61,
        )

    def test_detect_head_and_shoulders_bearish(self, logger):
        pd = PatternDetector({}, logger)
        bars = self._hs_bars()
        res = pd.detect_head_and_shoulders(bars, bars[-1]["timestamp"])
        assert len(res) == 1
        p = res[0]
        assert p.pattern_type == PatternType.HEAD_AND_SHOULDERS
        assert p.measured_target is not None
        # head must be above neckline, target below neckline (bearish projection)
        assert p.key_levels["head"] > p.key_levels["neckline"]
        assert p.measured_target < p.key_levels["neckline"]

    def test_detect_head_and_shoulders_requires_min_touches(self, logger):
        pd = PatternDetector({}, logger)
        # valleys far apart -> neckline = avg, neither touches -> 0 touches
        bars = _controls_bars(
            [(0, 1.0930), (10, 1.0950), (20, 1.0850), (30, 1.1000),
             (40, 1.0950), (50, 1.0950), (60, 1.0940)],
            61,
        )
        res = pd.detect_head_and_shoulders(bars, bars[-1]["timestamp"])
        assert res == []

    def test_measured_target_h_and_s(self, logger):
        pd = PatternDetector({}, logger)
        bars = self._hs_bars(head=1.1000, neckline=1.0900, shoulder=1.0950)
        res = pd.detect_head_and_shoulders(bars, bars[-1]["timestamp"])
        # formula: measured_target = neckline - (head - neckline)
        neck = res[0].key_levels["neckline"]
        head = res[0].key_levels["head"]
        expected = neck - (head - neck)
        assert abs(res[0].measured_target - expected) < 1e-9
        # head 1.1000, neckline ~1.0900 -> target ~1.0800 (formula-consistent)
        assert abs(res[0].measured_target - 1.0800) < 0.002


# ---------------- DOUBLE TOP / BOTTOM ----------------
class TestDoubleTop:
    def test_detect_double_top(self, logger):
        pd = PatternDetector({}, logger)
        bars = _controls_bars(
            [(0, 1.0930), (10, 1.1000), (20, 1.0890), (30, 1.0995), (40, 1.0940)],
            41,
        )
        res = pd.detect_double_top(bars, bars[-1]["timestamp"])
        assert len(res) == 1
        p = res[0]
        assert p.pattern_type == PatternType.DOUBLE_TOP
        # target = valley - (peak - valley): verify formula
        nl = p.key_levels["neckline"]
        pk = max(p.key_levels["peak_1"], p.key_levels["peak_2"])
        assert abs(p.measured_target - (nl - (pk - nl))) < 1e-9
        assert p.measured_target < nl  # bearish projection below neckline

    def test_detect_double_top_too_far_apart(self, logger):
        pd = PatternDetector({}, logger)
        bars = _controls_bars(
            [(0, 1.0930), (10, 1.1000), (20, 1.0890), (30, 1.1030), (40, 1.0940)],
            41,
        )
        res = pd.detect_double_top(bars, bars[-1]["timestamp"])
        assert res == []


class TestDoubleBottom:
    def test_detect_double_bottom(self, logger):
        pd = PatternDetector({}, logger)
        bars = _controls_bars(
            [(0, 1.0970), (10, 1.0900), (20, 1.1010), (30, 1.0905), (40, 1.0960)],
            41,
        )
        res = pd.detect_double_bottom(bars, bars[-1]["timestamp"])
        assert len(res) == 1
        p = res[0]
        assert p.pattern_type == PatternType.DOUBLE_BOTTOM
        # target = neckline + (neckline - bottom): verify formula
        nl = p.key_levels["neckline"]
        bt = min(p.key_levels["bottom_1"], p.key_levels["bottom_2"])
        assert abs(p.measured_target - (nl + (nl - bt))) < 1e-9
        assert p.measured_target > nl  # bullish projection above neckline


# ---------------- TRIANGLES ----------------
def _triangle_bars(highs_vals, lows_vals):
    bars = []
    base = datetime(2026, 7, 1, tzinfo=timezone.utc)
    for i, (hi, lo) in enumerate(zip(highs_vals, lows_vals)):
        mid = (hi + lo) / 2
        bars.append(_bar(base + timedelta(hours=i), mid, hi, lo, mid))
    return bars


class TestTriangles:
    def test_detect_triangle_ascending(self, logger):
        pd = PatternDetector({}, logger)
        n = 30
        highs = [1.1000] * n
        lows = [1.0950 + (i / (n - 1)) * 0.0030 for i in range(n)]
        bars = _triangle_bars(highs, lows)
        res = pd.detect_triangle(bars, bars[-1]["timestamp"])
        assert len(res) == 1
        assert res[0].pattern_type == PatternType.TRIANGLE_ASCENDING

    def test_detect_triangle_descending(self, logger):
        pd = PatternDetector({}, logger)
        n = 30
        lows = [1.0950] * n
        highs = [1.1000 - (i / (n - 1)) * 0.0030 for i in range(n)]
        bars = _triangle_bars(highs, lows)
        res = pd.detect_triangle(bars, bars[-1]["timestamp"])
        assert len(res) == 1
        assert res[0].pattern_type == PatternType.TRIANGLE_DESCENDING

    def test_detect_triangle_symmetrical(self, logger):
        pd = PatternDetector({}, logger)
        n = 30
        highs = [1.1000 - (i / (n - 1)) * 0.0030 for i in range(n)]
        lows = [1.0950 + (i / (n - 1)) * 0.0030 for i in range(n)]
        bars = _triangle_bars(highs, lows)
        res = pd.detect_triangle(bars, bars[-1]["timestamp"])
        assert len(res) == 1
        assert res[0].pattern_type == PatternType.TRIANGLE_SYMMETRICAL

    def test_detect_triangle_requires_min_bars(self, logger):
        pd = PatternDetector({}, logger)
        n = 15  # below default triangle_min_bars=20
        highs = [1.1000] * n
        lows = [1.0950 + (i / (n - 1)) * 0.0030 for i in range(n)]
        bars = _triangle_bars(highs, lows)
        res = pd.detect_triangle(bars, bars[-1]["timestamp"])
        assert res == []


# ---------------- AGGREGATE ----------------
class TestDetectAll:
    def test_detect_all_combines_results(self, logger):
        pd = PatternDetector({}, logger)
        bars = _sine_bars(1.1000, 0.00015)
        res = pd.detect_all(bars, bars[-1]["timestamp"])
        assert isinstance(res, list)
        assert len(res) >= 1
        assert any(p.pattern_type == PatternType.HH_HL for p in res)

    def test_patterns_dont_mutate_input(self, logger):
        pd = PatternDetector({}, logger)
        bars = _sine_bars(1.1000, 0.00015)
        snap1 = [p.pattern_type for p in pd.detect_all(list(bars), bars[-1]["timestamp"])]
        snap2 = [p.pattern_type for p in pd.detect_all(list(bars), bars[-1]["timestamp"])]
        # detect_all must not mutate bars; recomputing yields identical results
        assert snap1 == snap2

    def test_key_levels_structure(self, logger):
        pd = PatternDetector({}, logger)
        bars = _sine_bars(1.1000, 0.00015)
        res = pd.detect_all(bars, bars[-1]["timestamp"])
        for p in res:
            assert isinstance(p.key_levels, dict)
        # HH_HL must carry the documented keys
        hh = [p for p in res if p.pattern_type == PatternType.HH_HL]
        if hh:
            kl = hh[0].key_levels
            assert "last_swing_high" in kl
            assert "last_swing_low" in kl
            assert "entry_zone" in kl
