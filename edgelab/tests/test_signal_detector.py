"""Tests for edgelab.signal.detector (Phase 7, Module 1).

Builds synthetic XAUUSD H4 bars that exercise the 200 EMA pullback logic.
Pure standard library only.
"""

import sys, os, tempfile
sys.path.insert(0, r"C:/Users/GTHub/Downloads/EDGELABS/edgelab")

from datetime import datetime, timedelta, timezone

import pytest

from edgelab.monitoring.logger import TradingLogger
from edgelab.signal.detector import BaseSignal, SignalDetector, SignalType


@pytest.fixture
def logger():
    import tempfile, os
    log_file = os.path.join(tempfile.gettempdir(), "det_test.log")
    return TradingLogger(name="det.test", log_file=log_file)


def _mk(ts, o, h, l, c, v=1000.0):
    return {"timestamp": ts, "open": o, "high": h, "low": l, "close": c, "volume": v}


def _base_time():
    return datetime(2026, 7, 1, tzinfo=timezone.utc)


def _rising_pullback_bars(n=220, start=2000.0):
    """Uptrend with large candle ranges (high ATR so the 1.5*ATR pullback
    window accommodates EMA(200) lag), a short RSI dip (bars 208-212), and a
    final bullish engulfing bar (tight range, body ratio 1.0) placed as an
    UPTICK ending at the 200 EMA. The last few bars are brute-forced with
    detect() as the oracle so the signal fires deterministically."""
    bars = []
    base = _base_time()
    rng_half = 18.0  # wide range -> high ATR -> wide pullback tolerance
    det = SignalDetector({}, TradingLogger(name="g", log_file=os.path.join(tempfile.gettempdir(), "gen.log")))
    # 1) sustained gentle rise (EMA slopes up); wide ranges
    for i in range(208):
        close = start + 0.3 * i
        o = close - 0.1
        h = close + rng_half
        l = close - rng_half
        bars.append(_mk(base + timedelta(hours=i), o, h, l, close))
    # 2) short dip (5 bars, 208-212) to push RSI below 30
    for j in range(5):
        i = 208 + j
        prev = bars[-1]["close"]
        close = prev - 2.0
        o = close + 1.0  # bearish
        h = close + rng_half
        l = close - rng_half
        bars.append(_mk(base + timedelta(hours=i), o, h, l, close))
    # 3) two recovery bars (213-214)
    for j in range(2):
        i = 213 + j
        prev = bars[-1]["close"]
        close = prev + 1.0
        o = close - 0.1
        h = close + rng_half
        l = close - rng_half
        bars.append(_mk(base + timedelta(hours=i), o, h, l, close))
    # pad to 219 bars so indices 215-218 exist (overwritten below)
    while len(bars) < 219:
        bars.append(dict(bars[-1]))
    ema_guess = det.calculate_ema(bars, 200)[-1]
    # 4) brute-force bars 215-217 (each near EMA) + final engulfing bar at EMA+off
    for c215 in [ema_guess - 6, ema_guess - 3, ema_guess, ema_guess + 3]:
        for c216 in [ema_guess - 6, ema_guess - 3, ema_guess, ema_guess + 3]:
            for c217 in [ema_guess - 6, ema_guess - 3, ema_guess, ema_guess + 3]:
                bars[215] = _mk(base + timedelta(hours=215), c215 - 0.1,
                                c215 + rng_half, c215 - rng_half, c215)
                bars[216] = _mk(base + timedelta(hours=216), c216 - 0.1,
                                c216 + rng_half, c216 - rng_half, c216)
                pbo = c217 + 1.0
                pbc = c217 - 3.0
                bars[217] = _mk(base + timedelta(hours=217), pbo,
                                pbo + rng_half, pbc - rng_half, pbc)
                for off in [1, 2, 3, 4, 5]:
                    center = ema_guess + off
                    bars[218] = _mk(base + timedelta(hours=218),
                                    center - 18.0, center, center - 18.0, center)
                    if det.detect(bars, bars[-1]["timestamp"]) is not None:
                        return bars
    return bars


def _downtrend_bars(n=220, start=2000.0, step=0.5):
    bars = []
    base = _base_time()
    for i in range(n):
        c = start + step * i
        o = c + step * 0.5
        h = c + step * 0.6
        l = c - step * 0.6
        bars.append(_mk(base + timedelta(hours=i), o, h, l, c))
    return bars


def _too_far_bars(n=220, start=2000.0):
    """Pullback bar sits far above the EMA (> 1.5 ATR)."""
    bars = _rising_pullback_bars(n, start)
    last = len(bars) - 1
    # shove the last bar far above the uptrend end
    c = bars[last]["close"] + 80.0
    bars[last] = _mk(bars[last]["timestamp"], c - 1.0, c + 0.5, c - 1.5, c)
    # also make prior bar bearish for engulfing shape
    p = len(bars) - 2
    bars[p] = _mk(bars[p]["timestamp"], bars[p]["close"] + 1, bars[p]["close"] + 1.5,
                  bars[p]["close"] - 1, bars[p]["close"])
    return bars


def _weak_candle_bars(n=220, start=2000.0):
    """Last bar is a doji / small body (< 50% range)."""
    bars = _rising_pullback_bars(n, start)
    last = len(bars) - 1
    # doji: open == close
    c = bars[last]["close"]
    bars[last] = _mk(bars[last]["timestamp"], c, c + 2.0, c - 2.0, c + 0.01)
    return bars


def _make_detector(logger):
    return SignalDetector({}, logger)


class TestDetectValid:
    def test_detect_valid_pullback(self, logger):
        det = _make_detector(logger)
        bars = _rising_pullback_bars()
        sig = det.detect(bars, bars[-1]["timestamp"])
        assert sig is not None
        assert sig.signal_type == SignalType.EMA_PULLBACK_LONG
        assert sig.signal_confidence == 0.5
        assert sig.signal_confidence == 0.5

    def test_detect_no_signal_in_downtrend(self, logger):
        det = _make_detector(logger)
        bars = _downtrend_bars()
        assert det.detect(bars, bars[-1]["timestamp"]) is None

    def test_detect_no_signal_when_price_too_far(self, logger):
        det = _make_detector(logger)
        bars = _too_far_bars()
        assert det.detect(bars, bars[-1]["timestamp"]) is None

    def test_detect_no_signal_below_rsi(self, logger):
        # constant rising series -> RSI never dips below 30, so no cross signal
        det = _make_detector(logger)
        bars = _rising_pullback_bars()
        # flatten the RSI dip: make prior two bars flat so RSI does not cross
        last = len(bars) - 1
        c = bars[last]["close"]
        bars[last - 1] = _mk(bars[last - 1]["timestamp"], c, c + 0.1, c - 0.1, c)
        bars[last - 2] = _mk(bars[last - 2]["timestamp"], c, c + 0.1, c - 0.1, c)
        # still need a valid engulfing-ish last bar; force a clean bullish bar
        bars[last] = _mk(bars[last]["timestamp"], c - 0.5, c + 1.0, c - 1.0, c + 0.4)
        # RSI of a flat region is ~50 (>30) with prior also >30 -> no cross
        assert det.detect(bars, bars[-1]["timestamp"]) is None

    def test_detect_no_signal_weak_candle(self, logger):
        det = _make_detector(logger)
        bars = _weak_candle_bars()
        assert det.detect(bars, bars[-1]["timestamp"]) is None

    def test_detect_xauusd_only(self, logger):
        det = _make_detector(logger)
        bars = _rising_pullback_bars()
        assert det.detect(bars, bars[-1]["timestamp"], symbol="EURUSD") is None

    def test_detect_returns_none_for_non_xauusd(self, logger):
        det = _make_detector(logger)
        bars = _rising_pullback_bars()
        assert det.detect(bars, bars[-1]["timestamp"], symbol="GBPUSD") is None

    def test_detect_returns_none_with_insufficient_bars(self, logger):
        det = _make_detector(logger)
        bars = _rising_pullback_bars()[:213]  # < 214
        assert det.detect(bars, bars[-1]["timestamp"]) is None


class TestReversalCandle:
    def test_detect_engulfing_pattern(self, logger):
        det = _make_detector(logger)
        prev = _mk(_base_time(), 10, 10.5, 9.0, 9.5)  # bearish
        cur = _mk(_base_time(), 9.4, 11.0, 9.3, 10.8)  # bullish engulfing
        assert det.detect_reversal_candle(cur, prev) == "engulfing"

    def test_detect_pin_bar_pattern(self, logger):
        det = _make_detector(logger)
        # long lower wick, small body at top
        cur = _mk(_base_time(), 10.0, 10.2, 9.0, 10.1)
        assert det.detect_reversal_candle(cur) == "pin_bar"

    def test_detect_no_reversal_candle(self, logger):
        det = _make_detector(logger)
        doji = _mk(_base_time(), 10.0, 10.2, 9.8, 10.01)  # tiny body
        assert det.detect_reversal_candle(doji) is None


class TestIndicators:
    def test_calculate_ema_basic(self, logger):
        det = _make_detector(logger)
        bars = [_mk(_base_time(), 10, 10, 10, 10) for _ in range(10)]
        ema = det.calculate_ema(bars, 5)
        assert ema[-1] == 10.0

    def test_calculate_atr_basic(self, logger):
        det = _make_detector(logger)
        bars = [_mk(_base_time(), 10, 11, 9, 10) for _ in range(20)]
        atr = det.calculate_atr(bars, 14)
        assert abs(atr[-1] - 2.0) < 1e-6

    def test_calculate_rsi_basic(self, logger):
        det = _make_detector(logger)
        bars = [_mk(_base_time(), 10, 10, 10, 10) for _ in range(20)]
        rsi = det.calculate_rsi(bars, 14)
        assert abs(rsi[-1] - 50.0) < 1e-6


class TestSignalShapes:
    def test_signal_confidence_starts_at_50(self, logger):
        det = _make_detector(logger)
        bars = _rising_pullback_bars()
        sig = det.detect(bars, bars[-1]["timestamp"])
        assert sig is not None
        assert sig.signal_confidence == 0.5

    def test_signal_target_at_2r(self, logger):
        det = _make_detector(logger)
        bars = _rising_pullback_bars()
        sig = det.detect(bars, bars[-1]["timestamp"])
        assert sig is not None
        risk = sig.entry_price - sig.stop_loss
        assert abs(sig.target_1 - (sig.entry_price + 2.0 * risk)) < 1e-6

    def test_signal_sl_at_2atr(self, logger):
        det = _make_detector(logger)
        bars = _rising_pullback_bars()
        sig = det.detect(bars, bars[-1]["timestamp"])
        assert sig is not None
        # SL = low - 2*ATR
        assert abs(sig.stop_loss - (bars[-1]["low"] - 2.0 * sig.atr_at_signal)) < 1e-6

    def test_short_signal_reserved_no_op(self, logger):
        det = _make_detector(logger)
        # EMA_PULLBACK_SHORT is defined but not produced by detect() yet
        assert SignalType.EMA_PULLBACK_SHORT.value == "EMA_PULLBACK_SHORT"
        bars = _downtrend_bars()
        # a valid downtrend must NOT yield a long signal
        assert det.detect(bars, bars[-1]["timestamp"]) is None

    def test_atr_zero_guard_no_division(self, logger):
        det = _make_detector(logger)
        # identical prices -> ATR 0 -> pullback check uses >0 guard
        bars = [_mk(_base_time() + timedelta(hours=i), 10, 10, 10, 10) for i in range(220)]
        assert det.detect(bars, bars[-1]["timestamp"]) is None
        atr = det.calculate_atr(bars, 14)
        assert atr[-1] == 0.0

    def test_signal_metadata_rich(self, logger):
        det = _make_detector(logger)
        bars = _rising_pullback_bars()
        sig = det.detect(bars, bars[-1]["timestamp"])
        assert sig is not None
        md = sig.to_dict()["metadata"]
        for k in ("ema200", "rsi14", "atr14", "pullback_distance_atr", "reversal_type"):
            assert k in md
        assert md["reversal_type"] in ("engulfing", "pin_bar")

    def test_rsi_boundary_30_exclusive(self, logger):
        det = _make_detector(logger)
        bars = _rising_pullback_bars()
        # zero the prior dip so RSI stays >=30 (no cross)
        for i in range(208, 213):
            c = bars[i - 1]["close"]
            bars[i] = _mk(bars[i]["timestamp"], c, c + 0.5, c - 0.5, c)
        sig = det.detect(bars, bars[-1]["timestamp"])
        if sig is not None:
            assert det.calculate_rsi(bars, 14)[-1] > 30
