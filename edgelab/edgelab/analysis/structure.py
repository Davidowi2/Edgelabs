"""Market structure reader for EdgeLab (Phase 5a, Module 1).

Reads raw OHLC to detect trend direction, strength, and key S/R levels — the
"what does the chart say" analysis. Pure standard library. On edge cases
(too few bars, no swings, all swings one side) it returns RANGE safely.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional

from edgelab.monitoring.logger import TradingLogger


class Trend(str, Enum):
    UP = "UP"
    DOWN = "DOWN"
    RANGE = "RANGE"


class SwingType(str, Enum):
    SWING_HIGH = "SWING_HIGH"
    SWING_LOW = "SWING_LOW"


@dataclass
class SwingPoint:
    price: float
    bar_index: int
    timestamp: datetime
    type: SwingType


@dataclass
class MarketSnapshot:
    trend: Trend = Trend.RANGE
    trend_strength: float = 0.0
    swing_highs: List[SwingPoint] = field(default_factory=list)
    swing_lows: List[SwingPoint] = field(default_factory=list)
    key_resistance: Optional[float] = None
    key_support: Optional[float] = None
    last_update: Optional[datetime] = None

    def to_dict(self) -> dict:
        return {
            "trend": self.trend.value,
            "trend_strength": self.trend_strength,
            "swing_highs": [
                {"price": s.price, "bar_index": s.bar_index,
                 "timestamp": s.timestamp.isoformat(), "type": s.type.value}
                for s in self.swing_highs
            ],
            "swing_lows": [
                {"price": s.price, "bar_index": s.bar_index,
                 "timestamp": s.timestamp.isoformat(), "type": s.type.value}
                for s in self.swing_lows
            ],
            "key_resistance": self.key_resistance,
            "key_support": self.key_support,
            "last_update": self.last_update.isoformat() if self.last_update else None,
        }


class StructureAnalyzer:
    def __init__(self, config: dict, logger: TradingLogger) -> None:
        self._logger = logger
        cfg = config or {}
        self.lookback_bars = int(cfg.get("lookback_bars", 200))
        self.swing_order = int(cfg.get("swing_order", 3))
        self._last: Optional[MarketSnapshot] = None

    def _swing_high(self, bars, i, order):
        hi = bars[i]["high"]
        lo_i = max(order, i - order)
        hi_i = min(len(bars) - 1 - order, i + order)
        for j in range(lo_i, hi_i + 1):
            if bars[j]["high"] > hi:
                return False
        return True

    def _swing_low(self, bars, i, order):
        lo = bars[i]["low"]
        lo_i = max(order, i - order)
        hi_i = min(len(bars) - 1 - order, i + order)
        for j in range(lo_i, hi_i + 1):
            if bars[j]["low"] < lo:
                return False
        return True

    def analyze(self, bars: List[dict], current_time: datetime) -> MarketSnapshot:
        snap = MarketSnapshot(last_update=current_time)
        if not bars or len(bars) < 2 * self.swing_order + 1:
            self._logger.info("structure: insufficient bars, default RANGE",
                              n=len(bars) if bars else 0)
            self._last = snap
            return snap

        order = self.swing_order
        highs: List[SwingPoint] = []
        lows: List[SwingPoint] = []
        for i in range(order, len(bars) - order):
            if self._swing_high(bars, i, order):
                highs.append(SwingPoint(bars[i]["high"], i, bars[i]["timestamp"], SwingType.SWING_HIGH))
            if self._swing_low(bars, i, order):
                lows.append(SwingPoint(bars[i]["low"], i, bars[i]["timestamp"], SwingType.SWING_LOW))

        snap.swing_highs = highs[-5:]
        snap.swing_lows = lows[-5:]

        # Trend: compare consecutive recent swings (HH/HL vs LH/LL)
        if len(highs) >= 2 and len(lows) >= 2:
            hh = highs[-1].price > highs[-2].price
            hl = lows[-1].price > lows[-2].price
            lh = highs[-1].price < highs[-2].price
            ll = lows[-1].price < lows[-2].price
            if hh and hl:
                snap.trend = Trend.UP
            elif lh and ll:
                snap.trend = Trend.DOWN
            else:
                snap.trend = Trend.RANGE
            # strength = fraction of recent consecutive swing pairs that are
            # consistently up (or down). Range 0..1.
            up_pairs = 0
            down_pairs = 0
            # Use min() to handle edge cases where swing high/low counts differ
            for k in range(1, min(len(highs), len(lows))):
                if highs[k].price > highs[k - 1].price and lows[k].price > lows[k - 1].price:
                    up_pairs += 1
                if highs[k].price < highs[k - 1].price and lows[k].price < lows[k - 1].price:
                    down_pairs += 1
            total_pairs = len(highs) - 1
            if snap.trend == Trend.UP:
                snap.trend_strength = up_pairs / total_pairs if total_pairs else 0.5
            elif snap.trend == Trend.DOWN:
                snap.trend_strength = down_pairs / total_pairs if total_pairs else 0.5
            else:
                snap.trend_strength = 0.0
            snap.trend_strength = max(0.0, min(1.0, snap.trend_strength))
        else:
            snap.trend = Trend.RANGE
            snap.trend_strength = 0.0

        # Key levels relative to last close
        last_close = bars[-1]["close"]
        above = sorted([s.price for s in highs if s.price > last_close])
        below = sorted([s.price for s in lows if s.price < last_close], reverse=True)
        snap.key_resistance = above[0] if above else None
        snap.key_support = below[0] if below else None

        self._logger.info("structure analyzed", trend=snap.trend.value,
                          strength=round(snap.trend_strength, 3))
        self._last = snap
        return snap

    def get_status(self) -> dict:
        if self._last is None:
            return MarketSnapshot().to_dict()
        return self._last.to_dict()
