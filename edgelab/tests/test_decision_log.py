"""Tests for edgelab.analysis.decision_log.DecisionLogger (Phase 5b, Module 2).

Every decision produces a fixed-schema DecisionLog. Priority logic:
KILL > critical SL > news block > inactivity > caution/danger > high anomaly
> no pattern -> EXECUTE. Outcomes feed PatternMemory (the audit trail).
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timedelta, timezone

import pytest

from edgelab.analysis.decision_log import DecisionLog, DecisionLogger
from edgelab.analysis.memory import PatternMemory
from edgelab.monitoring.logger import TradingLogger


@pytest.fixture
def logger():
    return TradingLogger(name="dl.test", log_file=os.path.join(tempfile.gettempdir(), "dl.log"))


@pytest.fixture
def log_dir():
    d = tempfile.mkdtemp(prefix="decisions_")
    return d


@pytest.fixture
def memory():
    return PatternMemory({"lookback_days": 90}, TradingLogger(name="m", log_file=os.path.join(tempfile.gettempdir(), "m.log")))


def _signal(direction="LONG", entry=1.1000, sl=1.0950, tp=1.1100, stype="ema_pullback_long"):
    return {"symbol": "EURUSD", "direction": direction, "entry_price": entry,
            "stop_loss": sl, "take_profit": tp, "signal_type": stype}


def _good_risk():
    return {
        "risk_status": {"protection_level": "SAFE", "action": "NONE", "reason": "within limits"},
        "inactivity_status": "normal",
        "news_status": {"trading_allowed": True, "reason": "outside all blackouts"},
        "trade_management_status": {"is_critical": False},
    }


def _analysis(anomaly_score=0.2, patterns=None, pattern_match=None, structure_strength=0.8):
    return {
        "structure": {"trend": "UP", "trend_strength": structure_strength},
        "anomaly": {"score": anomaly_score, "verdict": "normal"},
        "patterns": patterns if patterns is not None else [],
        "pattern_match": pattern_match,
    }


class TestBuildDecision:
    def test_build_decision_executes_with_good_data(self, logger, log_dir, memory):
        dl = DecisionLogger({"log_dir": log_dir}, logger, memory)
        analysis = _analysis(patterns=[{"pattern_type": "HH_HL", "confidence": 0.8}])
        d = dl.build_decision(_signal(), analysis, _good_risk())
        assert d.recommended_action == "EXECUTE"
        assert 0.0 <= d.confidence <= 0.95

    def test_build_decision_skips_on_news_blocked(self, logger, log_dir, memory):
        dl = DecisionLogger({"log_dir": log_dir}, logger, memory)
        risk = _good_risk()
        risk["news_status"] = {"trading_allowed": False, "reason": "pre-blackout NFP"}
        d = dl.build_decision(_signal(), _analysis(), risk)
        assert d.recommended_action == "SKIP"

    def test_build_decision_closes_on_risk_kill(self, logger, log_dir, memory):
        dl = DecisionLogger({"log_dir": log_dir}, logger, memory)
        risk = _good_risk()
        risk["risk_status"] = {"protection_level": "KILL", "action": "CLOSE_ALL_POSITIONS", "reason": "total DD breached"}
        d = dl.build_decision(_signal(), _analysis(), risk)
        assert d.recommended_action == "CLOSE_POSITION"

    def test_build_decision_reduces_on_anomaly(self, logger, log_dir, memory):
        dl = DecisionLogger({"log_dir": log_dir}, logger, memory)
        d = dl.build_decision(_signal(), _analysis(anomaly_score=0.75), _good_risk())
        assert d.recommended_action == "REDUCE_SIZE"

    def test_build_decision_reduces_on_risk_caution(self, logger, log_dir, memory):
        dl = DecisionLogger({"log_dir": log_dir}, logger, memory)
        risk = _good_risk()
        risk["risk_status"] = {"protection_level": "CAUTION", "action": "REDUCE_SIZE", "reason": "daily DD approaching"}
        d = dl.build_decision(_signal(), _analysis(), risk)
        assert d.recommended_action == "REDUCE_SIZE"

    def test_build_decision_skips_on_no_pattern_no_memory(self, logger, log_dir, memory):
        dl = DecisionLogger({"log_dir": log_dir}, logger, memory)
        # no patterns AND no pattern match -> SKIP (rule 7)
        d = dl.build_decision(_signal(), _analysis(patterns=[], pattern_match=None), _good_risk())
        assert d.recommended_action == "SKIP"

    def test_build_decision_executes_with_pattern_even_no_match(self, logger, log_dir, memory):
        dl = DecisionLogger({"log_dir": log_dir}, logger, memory)
        pat = {"pattern_type": "HH_HL", "confidence": 0.8}
        d = dl.build_decision(_signal(), _analysis(patterns=[pat], pattern_match=None), _good_risk())
        # rule 7 only skips when BOTH empty; pattern present -> EXECUTE
        assert d.recommended_action == "EXECUTE"

    def test_confidence_capped_at_95(self, logger, log_dir, memory):
        dl = DecisionLogger({"log_dir": log_dir}, logger, memory)
        pat = {"pattern_type": "HH_HL", "confidence": 1.0}
        match = {"confidence": 1.0}
        d = dl.build_decision(_signal(), _analysis(anomaly_score=0.0, patterns=[pat],
                                                   pattern_match=match, structure_strength=1.0), _good_risk())
        assert d.confidence == 0.95

    def test_confidence_weighted_calculation(self, logger, log_dir, memory):
        dl = DecisionLogger({"log_dir": log_dir}, logger, memory)
        # match 0.8 (40%), pattern 0.5 (30%), structure 1.0 (20%), anomaly 0.0 -> inverse 1.0 (10%)
        pat = {"pattern_type": "HH_HL", "confidence": 0.5}
        match = {"confidence": 0.8}
        d = dl.build_decision(_signal(), _analysis(anomaly_score=0.0, patterns=[pat],
                                                   pattern_match=match, structure_strength=1.0), _good_risk())
        expected = 0.8 * 0.40 + 0.5 * 0.30 + 1.0 * 0.20 + 1.0 * 0.10
        assert abs(d.confidence - expected) < 1e-9

    def test_reasoning_is_human_readable(self, logger, log_dir, memory):
        dl = DecisionLogger({"log_dir": log_dir}, logger, memory)
        d = dl.build_decision(_signal(), _analysis(), _good_risk())
        assert "EURUSD" in d.reasoning
        assert "LONG" in d.reasoning
        assert len(d.reasoning) > 20

    def test_decision_id_is_unique_uuid(self, logger, log_dir, memory):
        dl = DecisionLogger({"log_dir": log_dir}, logger, memory)
        d1 = dl.build_decision(_signal(), _analysis(), _good_risk())
        d2 = dl.build_decision(_signal(), _analysis(), _good_risk())
        assert d1.decision_id != d2.decision_id


class TestPersistence:
    def test_log_decision_creates_file(self, logger, log_dir, memory):
        dl = DecisionLogger({"log_dir": log_dir}, logger, memory)
        d = dl.build_decision(_signal(), _analysis(), _good_risk())
        dl.log_decision(d)
        path = os.path.join(log_dir, f"{d.decision_id}.json")
        assert os.path.exists(path)
        with open(path) as fh:
            saved = json.load(fh)
        assert saved["decision_id"] == d.decision_id
        assert saved["symbol"] == "EURUSD"

    def test_record_outcome_updates_file(self, logger, log_dir, memory):
        dl = DecisionLogger({"log_dir": log_dir}, logger, memory)
        d = dl.build_decision(_signal(), _analysis(), _good_risk())
        dl.log_decision(d)
        dl.record_outcome(d.decision_id, 35.0, "WIN")
        path = os.path.join(log_dir, f"{d.decision_id}.json")
        with open(path) as fh:
            saved = json.load(fh)
        assert saved["outcome_pips"] == 35.0
        assert saved["result"] == "WIN"

    def test_record_outcome_creates_memory_record(self, logger, log_dir, memory):
        dl = DecisionLogger({"log_dir": log_dir}, logger, memory)
        d = dl.build_decision(_signal(), _analysis(), _good_risk())
        dl.log_decision(d)
        before = memory.get_record_count()
        dl.record_outcome(d.decision_id, 35.0, "WIN")
        assert memory.get_record_count() == before + 1

    def test_get_decision_returns_none_for_missing_id(self, logger, log_dir, memory):
        dl = DecisionLogger({"log_dir": log_dir}, logger, memory)
        assert dl.get_decision("does-not-exist") is None

    def test_list_recent_decisions_sorted_by_time(self, logger, log_dir, memory):
        dl = DecisionLogger({"log_dir": log_dir}, logger, memory)
        for k in range(3):
            sig = _signal()
            d = dl.build_decision(sig, _analysis(), _good_risk())
            # offset timestamps so ordering is meaningful
            d.timestamp_utc = datetime(2026, 7, 1, k, 0, tzinfo=timezone.utc)
            dl.log_decision(d)
        recent = dl.list_recent_decisions(limit=20)
        assert len(recent) == 3
        ts = [d.timestamp_utc for d in recent]
        assert ts == sorted(ts, reverse=True)


class TestDefaults:
    def test_decision_log_default_outcome_none(self, logger, log_dir, memory):
        dl = DecisionLogger({"log_dir": log_dir}, logger, memory)
        d = dl.build_decision(_signal(), _analysis(), _good_risk())
        assert d.outcome_pips is None
