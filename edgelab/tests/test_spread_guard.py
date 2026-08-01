"""Tests for edgelab.execution.spread_guard (Phase 8, Module 1).

Pure standard library only. Uses a real TradingLogger and synthetic spreads.
"""

import sys, os, tempfile
sys.path.insert(0, r"C:/Users/GTHub/Downloads/EDGELABS/edgelab")

from datetime import datetime, timezone

import pytest

from edgelab.monitoring.logger import TradingLogger
from edgelab.execution.spread_guard import (
    SpreadGuard, SpreadSnapshot, SpreadVerdict,
)


@pytest.fixture
def logger():
    return TradingLogger(name="spread.test",
                         log_file=os.path.join(tempfile.gettempdir(), "spread_test.log"))


def _cfg(**kw):
    base = {
        "max_spread_points": 35.0,
        "shock_multiplier": 2.0,
        "elevated_multiplier": 1.5,
        "baseline_window": 60,
        "cooldown_after_shock_seconds": 900,
    }
    base.update(kw)
    return base


def _utc(hour, minute=0):
    return datetime(2026, 7, 20, hour, minute, tzinfo=timezone.utc)


class TestUpdateBaseline:
    def test_update_baseline_stores_spreads(self, logger):
        g = SpreadGuard(_cfg(), logger)
        for v in [10, 12, 11, 13, 12]:
            g.update_baseline(v)
        snap = g.check_spread(12, _utc(10))
        assert snap.baseline_samples == 5

    def test_baseline_median_correct_with_known_values(self, logger):
        g = SpreadGuard(_cfg(), logger)
        for v in [10, 20, 30, 40, 50]:
            g.update_baseline(v)
        # median of [10,20,30,40,50] = 30
        med = g._baseline_median()
        assert abs(med - 30.0) < 1e-9

    def test_baseline_window_respected(self, logger):
        g = SpreadGuard(_cfg(baseline_window=5), logger)
        for v in [1, 2, 3, 4, 5, 6, 7]:
            g.update_baseline(v)
        # only last 5 kept
        assert g._samples == [3, 4, 5, 6, 7]
        assert len(g._samples) == 5


class TestCheckSpread:
    def test_check_spread_with_insufficient_baseline(self, logger):
        g = SpreadGuard(_cfg(), logger)
        for v in [10, 12, 11]:  # < 10 samples
            g.update_baseline(v)
        snap = g.check_spread(1000, _utc(10))
        # not enough data -> OK, not BLOCKED even though huge spread
        assert snap.verdict == SpreadVerdict.OK
        assert "insufficient" in snap.reason.lower() or snap.reason != ""

    def test_check_spread_under_all_thresholds(self, logger):
        g = SpreadGuard(_cfg(), logger)
        for v in [10, 11, 10, 12, 11, 10, 11, 10, 12, 11, 10, 11]:
            g.update_baseline(v)
        snap = g.check_spread(12, _utc(10))
        assert snap.verdict == SpreadVerdict.OK
        assert snap.baseline_median == 11.0

    def test_check_spread_elevated(self, logger):
        g = SpreadGuard(_cfg(), logger)
        for v in [10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10]:
            g.update_baseline(v)
        # baseline median = 10; 1.5x = 15; 2.0x = 20
        snap = g.check_spread(18, _utc(10))
        assert snap.verdict == SpreadVerdict.ELEVATED

    def test_check_spread_shock(self, logger):
        g = SpreadGuard(_cfg(), logger)
        for v in [10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10]:
            g.update_baseline(v)
        snap = g.check_spread(25, _utc(10))  # > 2.0x*10 = 20
        assert snap.verdict == SpreadVerdict.SHOCK
        assert snap.cooldown_until is not None

    def test_check_spread_above_absolute_ceiling(self, logger):
        g = SpreadGuard(_cfg(max_spread_points=35.0), logger)
        for v in [10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10]:
            g.update_baseline(v)
        snap = g.check_spread(50, _utc(10))  # > 35 ceiling
        assert snap.verdict == SpreadVerdict.BLOCKED
        assert "ceiling" in snap.reason.lower()

    def test_check_spread_session_override(self, logger):
        # london session max override = 25
        g = SpreadGuard(_cfg(session_max_overrides={"london": 25}), logger)
        for v in [10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10]:
            g.update_baseline(v)
        # 09:00 UTC is london session
        snap = g.check_spread(30, _utc(9))  # > 25 override
        assert snap.verdict == SpreadVerdict.BLOCKED
        # other sessions still use default ceiling
        snap2 = g.check_spread(30, _utc(2))  # asian, default 35 -> OK
        assert snap2.verdict != SpreadVerdict.BLOCKED

    def test_check_spread_returns_baseline_median(self, logger):
        g = SpreadGuard(_cfg(), logger)
        for v in [8, 9, 10, 11, 12, 8, 9, 10, 11, 12, 8, 9]:
            g.update_baseline(v)
        snap = g.check_spread(10, _utc(10))
        assert abs(snap.baseline_median - 9.5) < 1e-9

    def test_check_spread_percentile_correct(self, logger):
        g = SpreadGuard(_cfg(), logger)
        for v in [10, 20, 30, 40, 50, 60, 70, 80, 90, 100,
                  10, 20, 30, 40, 50, 60, 70, 80, 90, 100]:
            g.update_baseline(v)
        # current = 100 -> max in baseline -> 100th percentile
        snap = g.check_spread(100, _utc(10))
        assert snap.percentile >= 99.0
        # current = 10 -> min -> ~10th percentile (count of values <= 10 = 2/20)
        snap2 = g.check_spread(10, _utc(10))
        assert snap2.percentile <= 15.0


class TestCooldown:
    def test_cooldown_after_shock(self, logger):
        g = SpreadGuard(_cfg(), logger)
        for v in [10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10]:
            g.update_baseline(v)
        snap = g.check_spread(25, _utc(10))
        assert snap.verdict == SpreadVerdict.SHOCK
        rem = g.get_cooldown_remaining(_utc(10))
        assert rem > 0
        assert rem <= 900.0

    def test_cooldown_expires(self, logger):
        g = SpreadGuard(_cfg(cooldown_after_shock_seconds=900), logger)
        for v in [10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10]:
            g.update_baseline(v)
        g.check_spread(25, _utc(10))  # shock -> cooldown
        # 901 seconds later
        later = _utc(10, 0).timestamp() + 901
        import datetime as dt
        later_dt = datetime.fromtimestamp(later, tz=timezone.utc)
        rem = g.get_cooldown_remaining(later_dt)
        assert rem == 0.0


class TestIsBlocked:
    def test_is_blocked_true_for_shock(self, logger):
        snap = SpreadSnapshot(20, 10, 12, 50, SpreadVerdict.SHOCK, "x")
        g = SpreadGuard(_cfg(), logger)
        assert g.is_blocked(snap) is True

    def test_is_blocked_true_for_blocked_ceiling(self, logger):
        snap = SpreadSnapshot(50, 10, 12, 50, SpreadVerdict.BLOCKED, "x")
        g = SpreadGuard(_cfg(), logger)
        assert g.is_blocked(snap) is True

    def test_is_blocked_false_for_ok(self, logger):
        snap = SpreadSnapshot(11, 10, 12, 50, SpreadVerdict.OK, "x")
        g = SpreadGuard(_cfg(), logger)
        assert g.is_blocked(snap) is False


class TestSession:
    def test_get_session_asian(self, logger):
        g = SpreadGuard(_cfg(), logger)
        assert g._get_session(_utc(23)) == "asian"
        assert g._get_session(_utc(3)) == "asian"

    def test_get_session_london(self, logger):
        g = SpreadGuard(_cfg(), logger)
        assert g._get_session(_utc(9)) == "london"

    def test_get_session_overlap(self, logger):
        g = SpreadGuard(_cfg(), logger)
        assert g._get_session(_utc(14)) == "overlap"

    def test_get_session_ny(self, logger):
        g = SpreadGuard(_cfg(), logger)
        assert g._get_session(_utc(19)) == "ny"
