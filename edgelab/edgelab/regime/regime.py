"""Regime classification for EdgeLab (Phase 6, Module 2).

Combines volatility + ADX + structure into a market-regime label that the
signal layer (Phase 7) will use for context. Rule-based, not adaptive:

  - EXTREME volatility          -> VOLATILE (safety override, regardless of ADX)
  - HIGH volatility + low ADX   -> VOLATILE
  - ADX >= 25 + structure       -> TRENDING_UP / TRENDING_DOWN
  - ADX >= 40 (strong trend)    -> confidence 0.8
  - ADX < 20 + normal/low vol   -> RANGING
  - default                     -> RANGING (safe), confidence 0.5

Confidence is always capped at 0.95 (honest reporting). Pure stdlib, no ML.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional

from edgelab.analysis.structure import StructureAnalyzer, Trend
from edgelab.monitoring.logger import TradingLogger
from edgelab.regime.volatility import VolatilityClassifier, VolatilitySnapshot


class MarketRegime(str, Enum):
    TRENDING_UP = "TRENDING_UP"
    TRENDING_DOWN = "TRENDING_DOWN"
    RANGING = "RANGING"
    VOLATILE = "VOLATILE"
    UNKNOWN = "UNKNOWN"


@dataclass
class RegimeSnapshot:
    regime: MarketRegime = MarketRegime.UNKNOWN
    confidence: float = 0.0
    components: dict = field(default_factory=dict)
    reasoning: str = ""
    timestamp: Optional[datetime] = None
    lookback_bars: int = 0

    def to_dict(self) -> dict:
        return {
            "regime": self.regime.value,
            "confidence": self.confidence,
            "components": self.components,
            "reasoning": self.reasoning,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "lookback_bars": self.lookback_bars,
        }


def _true_range(bar, prev_close):
    high = bar["high"]
    low = bar["low"]
    return max(high - low, abs(high - prev_close), abs(low - prev_close))


class RegimeClassifier:
    def __init__(self, config: dict, logger: TradingLogger,
                 volatility_classifier: VolatilityClassifier) -> None:
        self._logger = logger
        self._vol = volatility_classifier
        cfg = config or {}
        self.adx_period = int(cfg.get("adx_period", 14))
        self.trending_adx = float(cfg.get("trending_adx_threshold", 25))
        self.strong_trend_adx = float(cfg.get("strong_trend_adx_threshold", 40))
        self.ranging_adx = float(cfg.get("ranging_adx_threshold", 20))
        self.lookback_bars = int(cfg.get("lookback_bars", 200))

    # ---------- ADX (Wilder smoothing) ----------
    def _calculate_adx(self, bars: List[dict], period: int) -> float:
        if len(bars) < period * 2:
            return 0.0
        # True Range series (aligned with +DM/-DM: start at bar 1, N-1 values)
        tr = []
        for i in range(1, len(bars)):
            tr.append(_true_range(bars[i], bars[i - 1]["close"]))
        # +DM / -DM
        pdm = []
        mdm = []
        for i in range(1, len(bars)):
            up = bars[i]["high"] - bars[i - 1]["high"]
            dn = bars[i - 1]["low"] - bars[i]["low"]
            pdm.append(max(up, 0.0) if up > dn else 0.0)
            mdm.append(max(dn, 0.0) if dn > up else 0.0)
        # Wilder smoothing (all three series now have the same length)
        def smooth(series, p):
            if len(series) < p:
                return [0.0] * len(series)
            s = sum(series[:p]) / p
            out = [s]
            for v in series[p:]:
                s = (s * (p - 1) + v) / p
                out.append(s)
            return out
        atr_s = smooth(tr, period)
        pdm_s = smooth(pdm, period)
        mdm_s = smooth(mdm, period)
        # +DI / -DI
        plus_di = []
        minus_di = []
        for i in range(len(atr_s)):
            atr_v = atr_s[i]
            if atr_v == 0:
                plus_di.append(0.0)
                minus_di.append(0.0)
            else:
                plus_di.append(100.0 * pdm_s[i] / atr_v)
                minus_di.append(100.0 * mdm_s[i] / atr_v)
        # DX
        dx = []
        for i in range(len(plus_di)):
            denom = plus_di[i] + minus_di[i]
            dx.append(0.0 if denom == 0 else 100.0 * abs(plus_di[i] - minus_di[i]) / denom)
        # ADX = smoothed DX
        if len(dx) < period:
            return 0.0
        adx_s = smooth(dx, period)
        return adx_s[-1]

    # ---------- classification ----------
    def classify(self, bars: List[dict], current_time: datetime,
                 structure_trend: Optional[str] = None) -> RegimeSnapshot:
        vol: VolatilitySnapshot = self._vol.classify(bars, current_time)
        adx = self._calculate_adx(bars, self.adx_period)
        trend = structure_trend
        if trend is None:
            try:
                snap = StructureAnalyzer({}, self._logger).analyze(bars, current_time)
                trend = snap.trend.value
            except Exception:  # noqa: BLE001 - structure is best-effort context
                trend = "RANGE"

        regime = MarketRegime.RANGING
        confidence = 0.5

        if vol.level.value == "EXTREME":
            regime = MarketRegime.VOLATILE
            confidence = 0.9
        elif vol.level.value == "HIGH" and adx < self.ranging_adx:
            regime = MarketRegime.VOLATILE
            confidence = 0.7
        elif adx >= self.trending_adx:
            if trend == "UP":
                regime = MarketRegime.TRENDING_UP
            elif trend == "DOWN":
                regime = MarketRegime.TRENDING_DOWN
            else:
                regime = MarketRegime.TRENDING_UP  # adx says trending; default up
        elif adx < self.ranging_adx and vol.level.value in ("LOW", "NORMAL"):
            regime = MarketRegime.RANGING
            confidence = 0.7
        else:
            regime = MarketRegime.RANGING
            confidence = 0.5

        if regime in (MarketRegime.TRENDING_UP, MarketRegime.TRENDING_DOWN) \
                and adx >= self.strong_trend_adx:
            confidence = 0.8

        confidence = min(0.95, confidence)

        reasoning = (
            f"regime={regime.value}; ADX={adx:.1f} "
            f"(trending>={self.trending_adx}, strong>={self.strong_trend_adx}); "
            f"volatility={vol.level.value} (atr_pct={vol.atr_percentile:.0f}); "
            f"structure={trend}"
        )

        snap = RegimeSnapshot(
            regime=regime,
            confidence=confidence,
            components={
                "volatility": vol.to_dict(),
                "adx": adx,
                "structure_trend": trend,
            },
            reasoning=reasoning,
            timestamp=current_time,
            lookback_bars=len(bars),
        )
        self._logger.info("regime classified", regime=regime.value,
                         confidence=round(confidence, 2), adx=round(adx, 1))
        return snap

    def get_status(self) -> dict:
        return RegimeSnapshot().to_dict()
