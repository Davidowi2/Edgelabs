"""3-way confluence checker for EdgeLab (Phase 7, Module 2).

Coordinates the three independent signals:
  * Signal 1 (BASE): 200 EMA pullback  -> SignalDetector
  * Signal 2 (STRUCTURE): HH_HL / BOS_UP + trend UP -> StructureAnalyzer + PatternDetector
  * Signal 3 (REGIME): TRENDING_UP, non-extreme vol -> RegimeClassifier

ALL THREE must pass. Then the 5 secondary filters (risk, news, anomaly,
memory, trade-mgmt) can each independently block. Failure is loud: every
reason is accumulated in ConfluenceResult.reasons. If a signal source is
unavailable (raises), it fails safe with reason "structure_unavailable" /
"regime_unavailable". Pure standard library.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional

from edgelab.analysis.patterns import PatternDetector, PatternType
from edgelab.analysis.structure import StructureAnalyzer, Trend
from edgelab.regime.regime import MarketRegime, RegimeClassifier
from edgelab.signal.detector import BaseSignal, SignalDetector


class SignalSource(str, Enum):
    BASE_SIGNAL = "BASE_SIGNAL"
    STRUCTURE = "STRUCTURE"
    REGIME = "REGIME"


@dataclass
class SignalCheck:
    source: SignalSource
    passed: bool
    confidence: float = 0.5
    reason: str = ""
    data: dict = field(default_factory=dict)


@dataclass
class ConfluenceResult:
    all_passed: bool = False
    base_signal: Optional[BaseSignal] = None
    structure_check: Optional[SignalCheck] = None
    regime_check: Optional[SignalCheck] = None
    risk_check: Optional[SignalCheck] = None
    news_check: Optional[SignalCheck] = None
    memory_check: Optional[SignalCheck] = None
    trade_mgmt_check: Optional[SignalCheck] = None
    anomaly_check: Optional[SignalCheck] = None
    confidence: float = 0.0
    reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        def _sc(x):
            return x.__dict__ if isinstance(x, SignalCheck) else x
        return {
            "all_passed": self.all_passed,
            "base_signal": self.base_signal.to_dict() if self.base_signal else None,
            "structure_check": _sc(self.structure_check),
            "regime_check": _sc(self.regime_check),
            "risk_check": _sc(self.risk_check),
            "news_check": _sc(self.news_check),
            "memory_check": _sc(self.memory_check),
            "trade_mgmt_check": _sc(self.trade_mgmt_check),
            "anomaly_check": _sc(self.anomaly_check),
            "confidence": self.confidence,
            "reasons": self.reasons,
        }


class ConfluenceChecker:
    def __init__(self, config: dict, logger, signal_detector: SignalDetector,
                 analysis_system: dict, regime_system: dict, risk_system: dict,
                 news_filter, pattern_memory,
                 pattern_detector=None) -> None:
        self._logger = logger
        cfg = config or {}
        self._signal_detector = signal_detector
        self._analysis = analysis_system or {}
        self._regime = regime_system or {}
        self._risk = risk_system or {}
        self._news = news_filter
        self._memory = pattern_memory
        # pattern detector is pure/stateless; build from config unless injected
        self._pattern_detector = pattern_detector or PatternDetector(
            cfg.get("pattern", {}), logger)
        self.base_weight = float(cfg.get("base_weight", 0.30))
        self.structure_weight = float(cfg.get("structure_weight", 0.35))
        self.regime_weight = float(cfg.get("regime_weight", 0.35))
        self.min_confidence_to_execute = float(cfg.get("min_confidence_to_execute", 0.60))
        # hard anomaly block threshold
        self.anomaly_block = float(cfg.get("anomaly_block", 0.80))

    # ---------- helpers ----------
    def _check_structure(self, bars, current_time) -> SignalCheck:
        try:
            structure = self._analysis.get("structure")
            if structure is None:
                return SignalCheck(SignalSource.STRUCTURE, False, 0.0,
                                   "structure_unavailable", {})
            snap = structure.analyze(bars, current_time)
            trend_val = snap.trend.value if hasattr(snap.trend, "value") else str(snap.trend)
            trend_strength = float(getattr(snap, "trend_strength", 0.0) or 0.0)
            # patterns (HH_HL or BOS_UP with confidence >= 0.5)
            patterns = self._pattern_detector.detect_all(bars, current_time)
            ok_patterns = [p for p in patterns
                           if p.pattern_type in (PatternType.HH_HL, PatternType.BOS_UP)
                           and getattr(p, "confidence", 0.0) >= 0.5]
            max_pat_conf = max((getattr(p, "confidence", 0.0) for p in ok_patterns), default=0.0)
            passed = (trend_val == "UP" and trend_strength >= 0.5 and len(ok_patterns) > 0)
            conf = min(trend_strength, max_pat_conf) if passed else 0.0
            reason = "" if passed else "structure not aligned (trend/strength/pattern)"
            return SignalCheck(SignalSource.STRUCTURE, passed, conf, reason,
                               {"trend": trend_val, "trend_strength": trend_strength,
                                "patterns": [p.to_dict() if hasattr(p, "to_dict") else p
                                             for p in ok_patterns]})
        except Exception as exc:  # noqa: BLE001 - fail safe
            self._logger.error("structure check failed", error=repr(exc))
            return SignalCheck(SignalSource.STRUCTURE, False, 0.0,
                               "structure_unavailable", {})

    def _check_regime(self, bars, current_time) -> SignalCheck:
        try:
            regime = self._regime.get("regime")
            if regime is None:
                return SignalCheck(SignalSource.REGIME, False, 0.0,
                                   "regime_unavailable", {})
            snap = regime.classify(bars, current_time)
            reg_val = snap.regime.value if hasattr(snap.regime, "value") else str(snap.regime)
            reg_conf = float(getattr(snap, "confidence", 0.0) or 0.0)
            vol = (snap.components.get("volatility", {}) or {}).get("level", "NORMAL")
            passed = (reg_val == MarketRegime.TRENDING_UP.value
                      and reg_conf >= 0.5 and vol != "EXTREME")
            reason = "" if passed else "regime not TRENDING_UP / extreme volatility"
            return SignalCheck(SignalSource.REGIME, passed, reg_conf if passed else 0.0,
                               reason, {"regime": reg_val, "confidence": reg_conf,
                                        "volatility": vol})
        except Exception as exc:  # noqa: BLE001 - fail safe
            self._logger.error("regime check failed", error=repr(exc))
            return SignalCheck(SignalSource.REGIME, False, 0.0,
                               "regime_unavailable", {})

    def _check_risk(self, account_balance, current_time) -> SignalCheck:
        try:
            dp = self._risk.get("drawdown_protector")
            if dp is None:
                return SignalCheck(SignalSource.BASE_SIGNAL, True, 1.0,
                                   "risk system unavailable (permissive)", {})
            level, action, reason = dp.check_protection()
            level_val = level.value if hasattr(level, "value") else str(level)
            passed = level_val != "KILL"
            return SignalCheck(SignalSource.BASE_SIGNAL, passed, 1.0 if passed else 0.0,
                               f"risk:{level_val}:{reason}",
                               {"protection_level": level_val, "action": getattr(action, "value", str(action))})
        except Exception as exc:  # noqa: BLE001
            self._logger.error("risk check failed", error=repr(exc))
            return SignalCheck(SignalSource.BASE_SIGNAL, False, 0.0, "risk_unavailable", {})

    def _check_news(self, symbol, current_time) -> SignalCheck:
        try:
            if self._news is None:
                return SignalCheck(SignalSource.BASE_SIGNAL, True, 1.0, "news unavailable", {})
            allowed, reason = self._news.is_trading_allowed(symbol, current_time)
            return SignalCheck(SignalSource.BASE_SIGNAL, bool(allowed), 1.0 if allowed else 0.0,
                               f"news:{reason}", {"trading_allowed": bool(allowed), "reason": reason})
        except Exception as exc:  # noqa: BLE001
            self._logger.error("news check failed", error=repr(exc))
            return SignalCheck(SignalSource.BASE_SIGNAL, False, 0.0, "news_unavailable", {})

    def _check_anomaly(self, bars) -> SignalCheck:
        try:
            anomaly = self._analysis.get("anomaly")
            if anomaly is None:
                return SignalCheck(SignalSource.BASE_SIGNAL, True, 1.0, "anomaly unavailable", {})
            score = anomaly.fit_and_score(bars, bars[-1])
            passed = score <= self.anomaly_block
            return SignalCheck(SignalSource.BASE_SIGNAL, passed, 1.0 if passed else 0.0,
                               f"anomaly:{score:.3f}", {"score": score})
        except Exception as exc:  # noqa: BLE001
            self._logger.error("anomaly check failed", error=repr(exc))
            return SignalCheck(SignalSource.BASE_SIGNAL, True, 1.0, "anomaly_unavailable", {})

    def _check_memory(self, base_signal, structure_check, regime_check) -> SignalCheck:
        try:
            if self._memory is None:
                return SignalCheck(SignalSource.BASE_SIGNAL, True, 1.0, "memory unavailable", {})
            if self._memory.get_record_count() == 0:
                return SignalCheck(SignalSource.BASE_SIGNAL, True, 1.0, "no memory records", {})
            stype = "EMA_PULLBACK_LONG" if base_signal else "UNKNOWN"
            structure = "UP" if (structure_check and structure_check.passed) else "UNKNOWN"
            confluence = int(round((regime_check.confidence if regime_check else 0.0) * 100))
            an_score = 0.0
            match = self._memory.query(stype, structure, confluence, an_score)
            # advisory: block only on a strong losing history
            win_rate = float(getattr(match, "win_rate", 0.0) or 0.0)
            similar = int(getattr(match, "similar_count", 0) or 0)
            passed = not (similar > 0 and win_rate == 0.0)
            return SignalCheck(SignalSource.BASE_SIGNAL, passed, 1.0 if passed else 0.0,
                               "memory advisory", {"similar_count": similar, "win_rate": win_rate})
        except Exception as exc:  # noqa: BLE001
            self._logger.error("memory check failed", error=repr(exc))
            return SignalCheck(SignalSource.BASE_SIGNAL, True, 1.0, "memory_unavailable", {})

    def _check_trade_mgmt(self, open_position) -> SignalCheck:
        # requires an open Position object; if none, skip with passed=True
        if open_position is None:
            return SignalCheck(SignalSource.BASE_SIGNAL, True, 1.0,
                               "no open position (skipped)", {})
        try:
            status = getattr(open_position, "status", None)
            is_critical = getattr(open_position, "is_critical", False)
            critical = bool(is_critical) or (status == "critical")
            return SignalCheck(SignalSource.BASE_SIGNAL, not critical, 1.0 if not critical else 0.0,
                               "trade management ok" if not critical else "trade management critical",
                               {"status": status, "is_critical": critical})
        except Exception as exc:  # noqa: BLE001
            self._logger.error("trade mgmt check failed", error=repr(exc))
            return SignalCheck(SignalSource.BASE_SIGNAL, True, 1.0, "trade_mgmt_unavailable", {})

    # ---------- main ----------
    def check(self, bars, current_time, symbol, account_balance, current_price,
              open_position=None) -> ConfluenceResult:
        reasons: List[str] = []
        base_signal = self._signal_detector.detect(bars, current_time, symbol)

        if base_signal is None:
            # short-circuit structure + regime (they are meaningless without base)
            structure_check = SignalCheck(SignalSource.STRUCTURE, False, 0.0,
                                          "base_signal_unavailable", {})
            regime_check = SignalCheck(SignalSource.REGIME, False, 0.0,
                                       "base_signal_unavailable", {})
            result = ConfluenceResult(all_passed=False, base_signal=None,
                                      structure_check=structure_check,
                                      regime_check=regime_check)
            reasons.append("base_signal_unavailable")
            result.reasons = reasons
            return result

        structure_check = self._check_structure(bars, current_time)
        regime_check = self._check_regime(bars, current_time)

        risk_check = self._check_risk(account_balance, current_time)
        news_check = self._check_news(symbol, current_time)
        anomaly_check = self._check_anomaly(bars)
        memory_check = self._check_memory(base_signal, structure_check, regime_check)
        trade_mgmt_check = self._check_trade_mgmt(open_position)

        # weighted confidence from the 3 signals
        base_conf = 0.5
        struct_conf = structure_check.confidence
        regime_conf = regime_check.confidence
        weighted = (base_conf * self.base_weight
                    + struct_conf * self.structure_weight
                    + regime_conf * self.regime_weight)
        confidence = min(0.95, weighted)

        # accumulate failures
        if not structure_check.passed:
            reasons.append(f"structure:{structure_check.reason}")
        if not regime_check.passed:
            reasons.append(f"regime:{regime_check.reason}")
        if not risk_check.passed:
            reasons.append(risk_check.reason)
        if not news_check.passed:
            reasons.append(news_check.reason)
        if not anomaly_check.passed:
            reasons.append(anomaly_check.reason)
        if not memory_check.passed:
            reasons.append(memory_check.reason)
        if not trade_mgmt_check.passed:
            reasons.append(trade_mgmt_check.reason)

        three_ok = structure_check.passed and regime_check.passed
        secondary_ok = (risk_check.passed and news_check.passed and anomaly_check.passed
                        and memory_check.passed and trade_mgmt_check.passed)
        all_passed = three_ok and secondary_ok

        result = ConfluenceResult(
            all_passed=all_passed,
            base_signal=base_signal,
            structure_check=structure_check,
            regime_check=regime_check,
            risk_check=risk_check,
            news_check=news_check,
            memory_check=memory_check,
            trade_mgmt_check=trade_mgmt_check,
            anomaly_check=anomaly_check,
            confidence=confidence,
            reasons=reasons,
        )
        self._logger.info("confluence check", all_passed=all_passed,
                         confidence=round(confidence, 2), n_reasons=len(reasons))
        return result
