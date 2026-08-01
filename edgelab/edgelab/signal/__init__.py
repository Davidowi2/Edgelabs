"""EdgeLab signal system factory (Phase 7, Module 3).

Wires the 3-way confluence pipeline: base SignalDetector + ConfluenceChecker,
fed by the analysis / regime / risk / news systems. Pure standard library.

Public API:
  * create_signal_system(config, logger, analysis_system, regime_system,
        risk_system, news_filter, pattern_memory) -> dict
  * quick_signal_check(bars, config, logger, analysis_system, regime_system,
        risk_system, news_filter, pattern_memory, current_time, symbol,
        account_balance, current_price, open_position) -> ConfluenceResult
  * SignalDetector, ConfluenceChecker, ConfluenceResult, SignalCheck,
    SignalSource (re-exported)
"""

from __future__ import annotations

from typing import Optional

from edgelab.signal.detector import BaseSignal, SignalDetector, SignalType
from edgelab.signal.confluence import (
    ConfluenceChecker,
    ConfluenceResult,
    SignalCheck,
    SignalSource,
)


def create_signal_system(config: dict, logger, analysis_system: dict,
                        regime_system: dict, risk_system: dict,
                        news_filter, pattern_memory,
                        pattern_detector=None) -> dict:
    """Build the signal system. Returns a dict with 'detector' and 'checker'.

    If 'signal' is absent from config OR not a dict, signal generation is
    DISABLED (fail-open): returns {} so callers skip signal checks.
    """
    cfg = config or {}
    sig_cfg = cfg.get("signal")
    if not isinstance(sig_cfg, dict):
        logger.warning("signal system disabled (no 'signal' config)")
        return {}

    detector = SignalDetector(sig_cfg, logger)
    checker = ConfluenceChecker(
        sig_cfg, logger, detector, analysis_system, regime_system,
        risk_system, news_filter, pattern_memory,
        pattern_detector=pattern_detector)
    logger.info("signal system created",
                base=sig_cfg.get("base_weight"),
                structure=sig_cfg.get("structure_weight"),
                regime=sig_cfg.get("regime_weight"))
    return {"detector": detector, "checker": checker}


def quick_signal_check(bars, config: dict, logger, analysis_system: dict,
                      regime_system: dict, risk_system: dict, news_filter,
                      pattern_memory, current_time=None, symbol: str = "XAUUSD",
                      account_balance: float = 0.0, current_price: float = 0.0,
                      open_position=None, pattern_detector=None) -> ConfluenceResult:
    """One-shot confluence check. Builds the system on the fly if not supplied.

    Fail-open: any unexpected error -> a SKIP result (all_passed False) with
    the reason recorded, never a silent pass.
    """
    from datetime import datetime
    if current_time is None:
        current_time = bars[-1]["timestamp"] if bars else datetime(2026, 1, 1)

    system = create_signal_system(
        config, logger, analysis_system, regime_system, risk_system,
        news_filter, pattern_memory, pattern_detector=pattern_detector)
    if not system:
        res = ConfluenceResult(all_passed=False)
        res.reasons = ["signal_system_disabled"]
        return res

    checker = system["checker"]
    try:
        return checker.check(
            bars, current_time, symbol, account_balance, current_price,
            open_position=open_position)
    except Exception as exc:  # noqa: BLE001 - fail open
        logger.error("signal check crashed", error=repr(exc))
        res = ConfluenceResult(all_passed=False)
        res.reasons = [f"signal_check_error:{repr(exc)}"]
        return res


__all__ = [
    "create_signal_system",
    "quick_signal_check",
    "SignalDetector",
    "ConfluenceChecker",
    "ConfluenceResult",
    "SignalCheck",
    "SignalSource",
    "BaseSignal",
    "SignalType",
]
