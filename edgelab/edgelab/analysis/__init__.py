"""EdgeLab analysis package (Phase 5a, Module 4).

Factory + convenience wrapper for the analytical core. quick_analyze() runs
structure + anomaly + memory in one call (the Phase 7 signal hook). Fail-open:
malformed config returns {} and logs. Pure standard library.
"""

from __future__ import annotations

import os
import tempfile
from datetime import datetime
from typing import Dict, List, Optional

from edgelab.analysis.anomaly import IsolationForest
from edgelab.analysis.memory import MatchResult, MemoryRecord, PatternMemory, Result
from edgelab.analysis.structure import (
    MarketSnapshot,
    StructureAnalyzer,
    SwingPoint,
    SwingType,
    Trend,
)
from edgelab.monitoring.logger import TradingLogger
from edgelab.time.broker_time import BrokerTime

__all__ = [
    "StructureAnalyzer",
    "IsolationForest",
    "PatternMemory",
    "PatternDetector",
    "DecisionLogger",
    "DecisionLog",
    "DetectedPattern",
    "MarketSnapshot",
    "MemoryRecord",
    "MatchResult",
    "create_analysis_system",
    "quick_analyze",
    "full_analysis",
]


def create_analysis_system(config: dict, logger: TradingLogger, broker_time: BrokerTime) -> dict:
    """Build the three analysis modules. Returns {} on any failure."""
    try:
        cfg = config or {}
        analysis = cfg.get("analysis")
        if not isinstance(analysis, dict):
            logger.error("analysis config missing or malformed; analysis disabled")
            return {}
        structure = StructureAnalyzer(analysis.get("structure", {}), logger)
        anomaly = IsolationForest(analysis.get("anomaly", {}), logger)
        memory = PatternMemory(analysis.get("memory", {}), logger)
        logger.info("analysis system initialized",
                    structure=analysis.get("structure", {}),
                    anomaly=analysis.get("anomaly", {}),
                    memory=analysis.get("memory", {}))
        return {"structure": structure, "anomaly": anomaly, "memory": memory}
    except Exception as exc:  # noqa: BLE001 - never crash startup
        logger.error("analysis system construction failed", error=repr(exc))
        return {}


def quick_analyze(bars: List[dict], latest_bar: dict, signal_type: str, structure: str,
                 confluence_score: int, config: dict, logger: TradingLogger) -> dict:
    """One-call convenience: structure + anomaly + pattern memory query."""
    bt = BrokerTime(offset="+3", dst=False)
    sys = create_analysis_system(config, logger, bt)
    snapshot = sys["structure"].analyze(bars, latest_bar["timestamp"])
    anomaly_score = sys["anomaly"].fit_and_score(bars, latest_bar)
    verdict = sys["anomaly"].get_verdict(anomaly_score)
    match = None
    if sys["memory"].get_record_count() > 0:
        match = sys["memory"].query(signal_type, structure, confluence_score, anomaly_score)
    return {
        "structure": snapshot,
        "anomaly_score": anomaly_score,
        "anomaly_verdict": verdict,
        "pattern_match": match,
    }


def full_analysis(bars: List[dict], symbol: str, current_time: datetime,
                signal_data: Optional[dict] = None, risk_data: Optional[dict] = None,
                analysis_system: Optional[dict] = None,
                decision_logger: Optional["DecisionLogger"] = None) -> dict:
    """Single entry point (Phase 7 will call this).

    Runs structure + anomaly + pattern detection + pattern memory query.
    If signal_data AND risk_data are provided AND a decision_logger is
    available, also builds a DecisionLog (writes it to disk).

    Returns a fixed-schema dict:
        {
          "structure": MarketSnapshot,
          "anomaly_score": float,
          "anomaly_verdict": str,
          "patterns": List[DetectedPattern],
          "pattern_match": MatchResult | None,
          "decision_log": DecisionLog | None,
        }
    Fail-open: on any error returns what it can and logs.
    """
    from edgelab.analysis.decision_log import DecisionLog, DecisionLogger
    from edgelab.analysis.patterns import PatternDetector

    # reuse the structure module's logger if we have a system, else make one
    base_logger = None
    if analysis_system is not None:
        base_logger = getattr(analysis_system.get("structure"), "_logger", None)
    if base_logger is None:
        base_logger = TradingLogger(
            name="analysis",
            log_file=os.path.join(tempfile.gettempdir(), "analysis_full.log"))
    logger = base_logger
    try:
        if analysis_system is None:
            bt = BrokerTime(offset="+3", dst=False)
            analysis_system = create_analysis_system(
                {"analysis": {}}, logger, bt)
        structure = analysis_system.get("structure")
        anomaly = analysis_system.get("anomaly")
        memory = analysis_system.get("memory")

        snapshot = structure.analyze(bars, current_time)
        anomaly_score = anomaly.fit_and_score(bars, {"high": _last(bars, "high"),
                                                 "low": _last(bars, "low"),
                                                 "close": _last(bars, "close"),
                                                 "open": _last(bars, "open"),
                                                 "volume": _last(bars, "volume"),
                                                 "timestamp": current_time})
        verdict = anomaly.get_verdict(anomaly_score)

        detector = PatternDetector({}, logger)
        patterns = detector.detect_all(bars, current_time)

        pattern_match = None
        if memory is not None and memory.get_record_count() > 0:
            stype = signal_data.get("signal_type") if signal_data else "UNKNOWN"
            strength = getattr(snapshot, "trend_strength", 0.0) or 0.0
            pattern_match = memory.query(
                stype, str(getattr(snapshot, "trend", "RANGE")),
                int(round(strength * 100)), anomaly_score)

        decision_log = None
        if signal_data is not None and risk_data is not None and decision_logger is not None:
            analysis_data = {
                "structure": snapshot,
                "anomaly": {"score": anomaly_score, "verdict": verdict},
                "patterns": patterns,
                "pattern_match": pattern_match,
                "timestamp_broker": current_time,
                "timestamp_utc": current_time,
            }
            decision_log = decision_logger.build_decision(
                signal_data, analysis_data, risk_data)

        return {
            "structure": snapshot,
            "anomaly_score": anomaly_score,
            "anomaly_verdict": verdict,
            "patterns": patterns,
            "pattern_match": pattern_match,
            "decision_log": decision_log,
        }
    except Exception as exc:  # noqa: BLE001 - fail open
        logger.error("full_analysis failed; returning partial", error=repr(exc))
        return {
            "structure": None,
            "anomaly_score": 0.0,
            "anomaly_verdict": "unknown",
            "patterns": [],
            "pattern_match": None,
            "decision_log": None,
        }


def _last(bars, key):
    return bars[-1].get(key, 0.0) if bars else 0.0
