"""Tests for edgelab.analysis.memory.PatternMemory (Phase 5a, Module 3)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from edgelab.analysis.memory import (
    MatchResult,
    MemoryRecord,
    PatternMemory,
    Result,
)


def _rec(ts=None, signal="ema_pullback_long", structure="HH_HL",
         confluence=3, anomaly=0.2, pips=20.0, result=Result.WIN):
    return MemoryRecord(
        timestamp=ts or datetime(2026, 7, 1, tzinfo=timezone.utc),
        signal_type=signal,
        structure=structure,
        confluence_score=confluence,
        anomaly_score=anomaly,
        entry_price=1.1000,
        outcome_pips=pips,
        result=result,
        metadata={},
    )


@pytest.fixture
def logger(tmp_path):
    from edgelab.monitoring.logger import TradingLogger
    return TradingLogger(name="mem.test", log_file=str(tmp_path / "mem.log"))


@pytest.fixture
def now():
    return datetime.now(timezone.utc)


class TestStore:
    def test_add_record_stores_correctly(self, logger, now):
        pm = PatternMemory({}, logger)
        pm.add_record(_rec(ts=now))
        assert pm.get_record_count() == 1

    def test_add_record_evicts_old_records(self, logger, now):
        pm = PatternMemory({"max_records": 5}, logger)
        for i in range(10):
            pm.add_record(_rec(ts=now - timedelta(days=i)))
        assert pm.get_record_count() == 5

    def test_add_record_respects_lookback_days(self, logger, now):
        pm = PatternMemory({"lookback_days": 90}, logger)
        pm.add_record(_rec(ts=now - timedelta(days=120)))
        assert pm.get_record_count() == 0

    def test_get_record_count(self, logger, now):
        pm = PatternMemory({}, logger)
        pm.add_record(_rec(ts=now))
        pm.add_record(_rec(ts=now))
        assert pm.get_record_count() == 2

    def test_clear_removes_all_records(self, logger, now):
        pm = PatternMemory({}, logger)
        pm.add_record(_rec(ts=now))
        pm.clear()
        assert pm.get_record_count() == 0

    def test_purge_old_records_removes_only_expired(self, logger, now):
        pm = PatternMemory({"lookback_days": 90}, logger)
        # seed _records directly (bypass add_record's auto-purge) to test purge isolation
        pm._records = [
            _rec(ts=now - timedelta(days=10)),
            _rec(ts=now - timedelta(days=100)),
        ]
        removed = pm.purge_old_records()
        assert removed == 1
        assert pm.get_record_count() == 1


class TestQuery:
    def test_query_exact_match_high_score(self, logger):
        pm = PatternMemory({}, logger)
        pm.add_record(_rec(signal="ema_pullback_long", structure="HH_HL", confluence=3, anomaly=0.2, result=Result.WIN))
        r = pm.query("ema_pullback_long", "HH_HL", 3, 0.2)
        assert r.similar_count >= 1
        assert r.confidence >= 0.9
        assert r.confidence <= 0.95

    def test_query_no_match_low_confidence(self, logger):
        pm = PatternMemory({}, logger)
        pm.add_record(_rec(signal="ema_pullback_long", structure="HH_HL"))
        r = pm.query("breakout_short", "LH_LL", 1, 0.9)
        assert r.similar_count == 0
        assert r.confidence == 0.0

    def test_query_partial_match(self, logger):
        # signal matches, structure differs (and confluence/anomaly differ) -> below threshold
        pm = PatternMemory({}, logger)
        pm.add_record(_rec(signal="ema_pullback_long", structure="HH_HL", confluence=3, anomaly=0.2))
        r = pm.query("ema_pullback_long", "LH_LL", 0, 0.9)
        assert r.similar_count == 0

    def test_confidence_capped_at_95(self, logger):
        pm = PatternMemory({}, logger)
        for _ in range(10):
            pm.add_record(_rec(signal="ema_pullback_long", structure="HH_HL", confluence=3, anomaly=0.2, result=Result.WIN))
        r = pm.query("ema_pullback_long", "HH_HL", 3, 0.2)
        assert r.confidence == 0.95

    def test_query_with_threshold(self, logger):
        pm = PatternMemory({}, logger)
        # only a weak partial match -> below 0.5 -> excluded
        pm.add_record(_rec(signal="ema_pullback_long", structure="HH_HL", confluence=3, anomaly=0.2))
        r = pm.query("ema_pullback_long", "LH_LL", 0, 0.9)
        assert r.similar_count == 0
        assert len(r.raw_matches) == 0

    def test_match_result_confidence_calculation(self, logger, now):
        pm = PatternMemory({}, logger)
        base = now
        results = [Result.WIN, Result.WIN, Result.WIN, Result.LOSS]
        for i, res in enumerate(results):
            pm.add_record(_rec(ts=base - timedelta(days=i), signal="ema_pullback_long",
                               structure="HH_HL", confluence=3, anomaly=0.2, result=res))
        r = pm.query("ema_pullback_long", "HH_HL", 3, 0.2)
        assert abs(r.confidence - 0.75) < 1e-9

    def test_query_with_no_matching_records(self, logger):
        pm = PatternMemory({}, logger)
        r = pm.query("nothing", "NONE", 0, 0.0)
        assert r.similar_count == 0
        assert r.confidence == 0.0
        assert r.avg_pips == 0.0
