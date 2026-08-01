"""EdgeLab regime package (Phase 6, Module 3).

Factory + convenience wrapper for regime detection. quick_regime_check() runs
volatility + regime classification in one call (the Phase 7 signal hook).
Fail-open: malformed config returns {} and logs. Pure standard library.
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from edgelab.monitoring.logger import TradingLogger
from edgelab.regime.regime import MarketRegime, RegimeClassifier, RegimeSnapshot
from edgelab.regime.volatility import (
    VolatilityClassifier,
    VolatilitySnapshot,
)

__all__ = [
    "VolatilityClassifier",
    "VolatilitySnapshot",
    "RegimeClassifier",
    "RegimeSnapshot",
    "MarketRegime",
    "create_regime_system",
    "quick_regime_check",
]


def create_regime_system(config: dict, logger: TradingLogger,
                         volatility_classifier: Optional[VolatilityClassifier] = None) -> dict:
    """Build the regime modules. Returns {} on any failure (fail-open)."""
    try:
        cfg = config or {}
        rcfg = cfg.get("regime")
        if not isinstance(rcfg, dict):
            # regime detection disabled (no config section) -> fail-open empty
            logger.warning("regime config missing; regime detection disabled")
            return {}
        vol = volatility_classifier or VolatilityClassifier(rcfg, logger)
        regime = RegimeClassifier(rcfg, logger, vol)
        logger.info("regime system initialized",
                    adx_period=regime.adx_period,
                    trending_adx=regime.trending_adx,
                    strong_trend_adx=regime.strong_trend_adx,
                    ranging_adx=regime.ranging_adx,
                    atr_period=vol.atr_period,
                    low_thr=vol.low_thr, high_thr=vol.high_thr,
                    extreme_thr=vol.extreme_thr,
                    lookback_days=vol.lookback_days)
        return {"volatility": vol, "regime": regime}
    except Exception as exc:  # noqa: BLE001 - never crash startup
        logger.error("regime system construction failed", error=repr(exc))
        return {}


def quick_regime_check(bars: List[dict], current_time: datetime,
                       regime_system: Optional[dict] = None,
                       structure_trend: Optional[str] = None) -> dict:
    """Single entry point (Phase 7 will call this).

    Runs volatility + regime classification. Returns a fixed-schema dict:
        {"regime", "confidence", "volatility_level", "adx", "reasoning"}
    Fail-open: on any error returns a safe RANGING dict.
    """
    try:
        if not regime_system:
            regime_system = create_regime_system({}, TradingLogger(
                name="regime", log_file=__import__("tempfile").gettempdir() + "/regime_q.log"))
        regime: RegimeClassifier = regime_system.get("regime")
        if regime is None:
            return {
                "regime": MarketRegime.RANGING.value,
                "confidence": 0.5,
                "volatility_level": "NORMAL",
                "adx": 0.0,
                "reasoning": "regime system unavailable; defaulting to RANGING",
            }
        snap = regime.classify(bars, current_time, structure_trend=structure_trend)
        return {
            "regime": snap.regime.value,
            "confidence": snap.confidence,
            "volatility_level": snap.components["volatility"]["level"],
            "adx": snap.components["adx"],
            "reasoning": snap.reasoning,
        }
    except Exception as exc:  # noqa: BLE001 - fail open
        logger = TradingLogger(name="regime",
                               log_file=__import__("tempfile").gettempdir() + "/regime_q.log")
        logger.error("quick_regime_check failed; safe default", error=repr(exc))
        return {
            "regime": MarketRegime.RANGING.value,
            "confidence": 0.5,
            "volatility_level": "NORMAL",
            "adx": 0.0,
            "reasoning": "regime check error; defaulting to RANGING",
        }
