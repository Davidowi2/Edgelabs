"""Pattern memory store for EdgeLab (Phase 5a, Module 3).

A LOOKUP table, not ML. Stores outcomes of past setups and retrieves similar
ones by weighted similarity. Confidence capped at 0.95 (honest reporting).
Pure standard library.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import List, Optional

from edgelab.monitoring.logger import TradingLogger


class Result(str, Enum):
    WIN = "WIN"
    LOSS = "LOSS"
    BREAKEVEN = "BREAKEVEN"


@dataclass
class MemoryRecord:
    timestamp: datetime
    signal_type: str
    structure: str
    confluence_score: int
    anomaly_score: float
    entry_price: float
    outcome_pips: float
    result: Result
    metadata: dict = field(default_factory=dict)


@dataclass
class MatchResult:
    similar_count: int = 0
    avg_pips: float = 0.0
    win_rate: float = 0.0
    avg_hold_bars: int = 0
    confidence: float = 0.0
    raw_matches: List[MemoryRecord] = field(default_factory=list)


class PatternMemory:
    def __init__(self, config: dict, logger: TradingLogger) -> None:
        self._logger = logger
        cfg = config or {}
        self.max_records = int(cfg.get("max_records", 500))
        self.lookback_days = int(cfg.get("lookback_days", 90))
        self.match_weights = cfg.get(
            "match_weights",
            {"signal_type": 1.0, "structure": 2.0, "confluence": 1.0, "anomaly": 0.5},
        )
        self._records: List[MemoryRecord] = []

    # ---------- storage ----------
    def add_record(self, record: MemoryRecord) -> None:
        self._records.append(record)
        self.purge_old_records()
        while len(self._records) > self.max_records:
            self._records.pop(0)  # FIFO evict oldest

    def purge_old_records(self) -> int:
        cutoff = datetime.now(record_timestamp_tz()) - timedelta(days=self.lookback_days)
        before = len(self._records)
        self._records = [r for r in self._records if r.timestamp >= cutoff]
        removed = before - len(self._records)
        if removed:
            self._logger.info("memory purged old records", removed=removed)
        return removed

    def get_record_count(self) -> int:
        return len(self._records)

    def clear(self) -> None:
        self._records = []

    # ---------- similarity ----------
    def _similarity(self, rec: MemoryRecord, signal_type, structure, confluence_score, anomaly_score) -> float:
        w = self.match_weights
        sw = w.get("signal_type", 1.0)
        stw = w.get("structure", 1.0)
        cw = w.get("confluence", 1.0)
        aw = w.get("anomaly", 0.5)
        total_w = sw + stw + cw + aw

        s_sig = 1.0 if rec.signal_type == signal_type else 0.0
        s_str = 1.0 if rec.structure == structure else 0.0
        s_con = max(0.0, 1.0 - abs(rec.confluence_score - confluence_score) / 5.0)
        s_an = max(0.0, 1.0 - abs(rec.anomaly_score - anomaly_score) / 1.0)

        # normalized weighted average so a single categorical match cannot exceed 1.0
        return (sw * s_sig + stw * s_str + cw * s_con + aw * s_an) / total_w

    def query(self, signal_type: str, structure: str, confluence_score: int,
              anomaly_score: float, max_results: int = 5) -> MatchResult:
        scored = []
        for rec in self._records:
            sim = self._similarity(rec, signal_type, structure, confluence_score, anomaly_score)
            if sim > 0.5:
                scored.append((sim, rec))
        scored.sort(key=lambda x: x[0], reverse=True)
        top = scored[:max_results]

        result = MatchResult()
        result.raw_matches = [r for _, r in top]
        result.similar_count = len(top)
        if top:
            pips = [r.outcome_pips for _, r in top]
            wins = sum(1 for _, r in top if r.result == Result.WIN)
            result.avg_pips = sum(pips) / len(pips)
            result.win_rate = wins / len(top)
            result.confidence = min(0.95, result.win_rate)
        else:
            result.confidence = 0.0
            result.avg_pips = 0.0
        self._logger.info("memory query", matches=result.similar_count, confidence=result.confidence)
        return result


def record_timestamp_tz():
    return timezone.utc


# import timezone lazily to avoid circular concerns
from datetime import timezone  # noqa: E402
