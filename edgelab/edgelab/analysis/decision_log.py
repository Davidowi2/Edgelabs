"""Trade Decision Explainer for EdgeLab (Phase 5b, Module 2).

Assembles all analysis inputs into a structured, fixed-schema decision log.
Every decision produces the SAME fields, enabling automated review, search,
and post-trade learning. The decision log is written to disk as JSON and,
after the trade closes, fed into the PatternMemory store.

Pure standard library. No ML. No trade execution.
"""

import json
import os
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from edgelab.analysis.memory import PatternMemory

# confidence cap: honesty contract (never report > 0.95)
CONFIDENCE_CAP = 0.95

# weighted average weights for overall decision confidence
_WEIGHTS = {
    "pattern_match": 0.40,   # PatternMemory lookup confidence
    "pattern_detection": 0.30,  # highest detected-pattern confidence
    "structure_strength": 0.20,  # trend strength from StructureAnalyzer
    "anomaly_inverse": 0.10,   # (1 - anomaly score)
}


@dataclass
class DecisionLog:
    decision_id: str
    timestamp_broker: datetime
    timestamp_utc: datetime
    symbol: str
    direction: str  # "LONG" | "SHORT"
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    signal_type: Optional[str] = None
    market_structure: Optional[dict] = None
    patterns: List[dict] = field(default_factory=list)
    pattern_match: Optional[dict] = None
    anomaly: Optional[dict] = None
    risk_status: Optional[dict] = None
    inactivity_status: Optional[dict] = None
    news_status: Optional[dict] = None
    trade_management_status: Optional[dict] = None
    recommended_action: str = "EXECUTE"
    confidence: float = 0.0
    reasoning: str = ""
    outcome_pips: Optional[float] = None

    def to_dict(self) -> dict:
        d = asdict(self)
        for k in ("timestamp_broker", "timestamp_utc"):
            if isinstance(d.get(k), datetime):
                d[k] = d[k].isoformat()  # type: ignore[assignment]
        if self.patterns:
            d["patterns"] = [p if isinstance(p, dict) else asdict(p) for p in self.patterns]
        return d

    @staticmethod
    def from_dict(d: dict) -> "DecisionLog":
        def _dt(v):
            if isinstance(v, str):
                try:
                    return datetime.fromisoformat(v)
                except Exception:  # noqa: BLE001 - tolerate bad timestamps
                    return None
            return v

        return DecisionLog(
            decision_id=d["decision_id"],
            timestamp_broker=_dt(d.get("timestamp_broker")),
            timestamp_utc=_dt(d.get("timestamp_utc")),
            symbol=d["symbol"],
            direction=d["direction"],
            entry_price=d.get("entry_price"),
            stop_loss=d.get("stop_loss"),
            take_profit=d.get("take_profit"),
            signal_type=d.get("signal_type"),
            market_structure=d.get("market_structure"),
            patterns=d.get("patterns", []),
            pattern_match=d.get("pattern_match"),
            anomaly=d.get("anomaly"),
            risk_status=d.get("risk_status"),
            inactivity_status=d.get("inactivity_status"),
            news_status=d.get("news_status"),
            trade_management_status=d.get("trade_management_status"),
            recommended_action=d.get("recommended_action", "EXECUTE"),
            confidence=float(d.get("confidence", 0.0)),
            reasoning=d.get("reasoning", ""),
            outcome_pips=d.get("outcome_pips"),
        )


class DecisionLogger:
    """Builds, persists, and retrieves structured decision logs."""

    def __init__(self, config, logger, pattern_memory: PatternMemory):
        self._cfg = config or {}
        self._logger = logger
        self._memory = pattern_memory
        self._log_dir = self._cfg.get("log_dir", "edgelab/logs/decisions")

    # ---------- construction ----------
    def build_decision(self, signal_data, analysis_data, risk_data) -> DecisionLog:
        signal_data = signal_data or {}
        analysis_data = analysis_data or {}
        risk_data = risk_data or {}

        symbol = signal_data.get("symbol", "?")
        direction = signal_data.get("direction", "LONG")
        entry = signal_data.get("entry_price")
        sl = signal_data.get("stop_loss")
        tp = signal_data.get("take_profit")
        signal_type = signal_data.get("signal_type")

        # broker time (UTC+3) is provided by the caller via analysis_data/timestamp
        ts_broker = analysis_data.get("timestamp_broker") or signal_data.get("timestamp_broker")
        if ts_broker is None:
            ts_utc = datetime.now(timezone.utc)
            ts_broker = ts_utc
        else:
            ts_utc = analysis_data.get("timestamp_utc") or ts_broker

        structure = analysis_data.get("structure")
        anomaly = analysis_data.get("anomaly")
        patterns = analysis_data.get("patterns") or []
        pattern_match = analysis_data.get("pattern_match")

        risk_status = risk_data.get("risk_status")
        inactivity_status = risk_data.get("inactivity_status")
        news_status = risk_data.get("news_status")
        trade_management_status = risk_data.get("trade_management_status")

        # ---- recommended action (priority logic) ----
        action = self._recommend(
            risk_status, trade_management_status, news_status,
            inactivity_status, anomaly, pattern_match, patterns)

        # ---- overall confidence (weighted average, capped) ----
        confidence = self._confidence(pattern_match, patterns, structure, anomaly)
        confidence = min(CONFIDENCE_CAP, confidence)

        # ---- human-readable reasoning ----
        reasoning = self._reasoning(
            symbol, direction, action, structure, anomaly, patterns,
            pattern_match, risk_status, news_status, inactivity_status,
            trade_management_status, confidence)

        decision = DecisionLog(
            decision_id=str(uuid.uuid4()),
            timestamp_broker=ts_broker,
            timestamp_utc=ts_utc,
            symbol=symbol,
            direction=direction,
            entry_price=entry,
            stop_loss=sl,
            take_profit=tp,
            signal_type=signal_type,
            market_structure=(structure.to_dict() if hasattr(structure, "to_dict") else structure),
            patterns=self._serialize_patterns(patterns),
            pattern_match=(pattern_match.to_dict() if hasattr(pattern_match, "to_dict") else pattern_match),
            anomaly=anomaly,
            risk_status=risk_status,
            inactivity_status=inactivity_status,
            news_status=news_status,
            trade_management_status=trade_management_status,
            recommended_action=action,
            confidence=confidence,
            reasoning=reasoning,
        )
        return decision

    # ---------- persistence ----------
    def log_decision(self, decision: DecisionLog) -> None:
        os.makedirs(self._log_dir, exist_ok=True)
        path = os.path.join(self._log_dir, f"{decision.decision_id}.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(decision.to_dict(), fh, indent=2, default=str)
        self._logger.info("decision logged", decision_id=decision.decision_id,
                         action=decision.recommended_action, symbol=decision.symbol)

    def record_outcome(self, decision_id: str, outcome_pips: float, result: str) -> None:
        path = os.path.join(self._log_dir, f"{decision_id}.json")
        if not os.path.exists(path):
            self._logger.warning("record_outcome: decision not found", decision_id=decision_id)
            return
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        data["outcome_pips"] = outcome_pips
        data["result"] = result
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, default=str)
        # feed the PatternMemory store so the system accumulates data points
        try:
            from edgelab.analysis.memory import MemoryRecord, Result
            pat_type = (data.get("patterns")[0].get("pattern_type")
                         if data.get("patterns") else "NONE")
            sig = data.get("signal_type") or "UNKNOWN"
            an_score = 0.0
            if isinstance(data.get("anomaly"), dict):
                an_score = float(data["anomaly"].get("score") or 0.0)
            rec = MemoryRecord(
                timestamp=(data.get("timestamp_utc") or datetime.now(timezone.utc)),
                signal_type=sig,
                structure=pat_type,
                confluence_score=int(round((data.get("confidence") or 0.0) * 100)),
                anomaly_score=an_score,
                entry_price=float(data.get("entry_price") or 0.0),
                outcome_pips=outcome_pips,
                result=Result(result) if result in ("WIN", "LOSS", "BREAKEVEN") else Result.LOSS,
                metadata={
                    "decision_id": decision_id,
                    "recommended_action": data.get("recommended_action"),
                    "pattern_match": data.get("pattern_match"),
                },
            )
            self._memory.add_record(rec)
        except Exception as exc:  # noqa: BLE001 - memory is best-effort
            self._logger.warning("record_outcome: memory add failed", error=repr(exc))
        self._logger.info("outcome recorded", decision_id=decision_id,
                         outcome_pips=outcome_pips, result=result)

    def get_decision(self, decision_id: str) -> Optional[DecisionLog]:
        path = os.path.join(self._log_dir, f"{decision_id}.json")
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return DecisionLog.from_dict(data)

    def list_recent_decisions(self, limit: int = 20) -> List[DecisionLog]:
        if not os.path.isdir(self._log_dir):
            return []
        out = []
        for fn in os.listdir(self._log_dir):
            if not fn.endswith(".json"):
                continue
            with open(os.path.join(self._log_dir, fn), "r", encoding="utf-8") as fh:
                try:
                    data = json.load(fh)
                except Exception:  # noqa: BLE001 - skip corrupt files
                    continue
            out.append(DecisionLog.from_dict(data))
        out.sort(key=lambda d: d.timestamp_broker or datetime.min.replace(tzinfo=timezone.utc),
                 reverse=True)
        return out[:limit]

    # ---------- internals ----------
    @staticmethod
    def _recommend(risk_status, tm_status, news_status, inactivity_status,
                    anomaly, pattern_match, patterns) -> str:
        # 1. risk kill -> close
        if risk_status and risk_status.get("protection_level") == "KILL":
            return "CLOSE_POSITION"
        # 2. trade-management critical -> close
        if tm_status:
            if tm_status.get("is_critical") or tm_status.get("status") == "critical":
                return "CLOSE_POSITION"
        # 3. news blocks trading -> skip
        if news_status and news_status.get("trading_allowed") is False:
            return "SKIP"
        # 4. inactivity critical -> skip
        if inactivity_status and str(inactivity_status).lower() == "critical":
            return "SKIP"
        if isinstance(inactivity_status, dict) and inactivity_status.get("level") == "critical":
            return "SKIP"
        # 5. risk caution/danger -> reduce
        if risk_status and risk_status.get("protection_level") in ("CAUTION", "DANGER"):
            return "REDUCE_SIZE"
        # 6. high anomaly -> reduce
        if anomaly and isinstance(anomaly.get("score"), (int, float)) and anomaly["score"] > 0.7:
            return "REDUCE_SIZE"
        # 7. no pattern and no memory match -> skip
        pm_conf = 0.0
        if isinstance(pattern_match, dict):
            pm_conf = float(pattern_match.get("confidence") or 0.0)
        if pm_conf < 0.4 and not patterns:
            return "SKIP"
        # else execute
        return "EXECUTE"

    @staticmethod
    def _confidence(pattern_match, patterns, structure, anomaly) -> float:
        parts = []

        def add(weight, value, ok):
            if ok:
                parts.append((weight, value))

        # pattern memory match
        pm_conf = 0.0
        if isinstance(pattern_match, dict):
            pm_conf = float(pattern_match.get("confidence") or 0.0)
        add(_WEIGHTS["pattern_match"], pm_conf, True)

        # detected-pattern confidence (highest)
        pd_conf = 0.0
        for p in patterns:
            c = 0.0
            if isinstance(p, dict):
                c = float(p.get("confidence") or 0.0)
            elif hasattr(p, "confidence"):
                c = float(getattr(p, "confidence") or 0.0)
            pd_conf = max(pd_conf, c)
        add(_WEIGHTS["pattern_detection"], pd_conf, True)

        # structure strength
        st_conf = 0.0
        if isinstance(structure, dict):
            st_conf = float(structure.get("trend_strength") or 0.0)
        elif hasattr(structure, "trend_strength"):
            st_conf = float(getattr(structure, "trend_strength") or 0.0)
        add(_WEIGHTS["structure_strength"], st_conf, True)

        # anomaly inverse
        an_conf = 1.0
        if anomaly and isinstance(anomaly.get("score"), (int, float)):
            an_conf = 1.0 - float(anomaly["score"])
        add(_WEIGHTS["anomaly_inverse"], an_conf, True)

        if not parts:
            return 0.0
        total_w = sum(w for w, _ in parts)
        if total_w <= 0:
            return 0.0
        return sum(w * v for w, v in parts) / total_w

    @staticmethod
    def _serialize_patterns(patterns) -> List[dict]:
        out = []
        for p in patterns:
            if isinstance(p, dict):
                out.append(p)
            elif hasattr(p, "to_dict"):
                out.append(p.to_dict())
            else:
                out.append(p)
        return out

    @staticmethod
    def _reasoning(symbol, direction, action, structure, anomaly, patterns,
                    pattern_match, risk_status, news_status, inactivity_status,
                    tm_status, confidence) -> str:
        bits = [f"{symbol} {direction} decision"]
        bits.append(f"recommended action: {action}")
        bits.append(f"overall confidence: {confidence:.2f}")

        trend = None
        if isinstance(structure, dict):
            trend = structure.get("trend")
        elif hasattr(structure, "trend"):
            trend = getattr(structure, "trend")
        if trend:
            bits.append(f"market structure: {trend}")

        if anomaly and isinstance(anomaly.get("score"), (int, float)):
            bits.append(f"anomaly score: {anomaly['score']:.2f} ({anomaly.get('verdict', 'n/a')})")

        if patterns:
            names = []
            for p in patterns:
                if isinstance(p, dict):
                    names.append(p.get("pattern_type", "?"))
                else:
                    names.append(str(getattr(p, "pattern_type", "?")))
            bits.append("detected patterns: " + ", ".join(names))

        if isinstance(pattern_match, dict) and pattern_match.get("confidence") is not None:
            bits.append(f"pattern memory confidence: {float(pattern_match['confidence']):.2f}")

        if risk_status and risk_status.get("protection_level"):
            bits.append(f"risk level: {risk_status['protection_level']}")
        if news_status and news_status.get("trading_allowed") is False:
            bits.append("news blackout active")
        if inactivity_status and str(inactivity_status).lower() == "critical":
            bits.append("inactivity critical")
        if tm_status and (tm_status.get("is_critical") or tm_status.get("status") == "critical"):
            bits.append("trade management critical")
        return "; ".join(bits)
