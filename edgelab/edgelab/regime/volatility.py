"""Volatility classification for EdgeLab (Phase 6, Module 1).

Quantifies current market volatility relative to recent history. This is the
PRIMARY input for regime detection: a percentile of current ATR(14) against the
recent distribution tells the system whether volatility is low / normal / high /
extreme. Also reports expanding/contracting state (ATR slope) and Bollinger-band
width percentile. Pure standard library, no ML.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional

from edgelab.monitoring.logger import TradingLogger


class VolatilityLevel(str, Enum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    EXTREME = "EXTREME"


@dataclass
class VolatilitySnapshot:
    current_atr: float = 0.0
    atr_percentile: float = 50.0
    atr_percent: float = 0.0
    bb_width_percentile: float = 50.0
    level: VolatilityLevel = VolatilityLevel.NORMAL
    expanding: bool = False
    contracting: bool = False
    lookback_days: int = 90

    def to_dict(self) -> dict:
        return {
            "current_atr": self.current_atr,
            "atr_percentile": self.atr_percentile,
            "atr_percent": self.atr_percent,
            "bb_width_percentile": self.bb_width_percentile,
            "level": self.level.value,
            "expanding": self.expanding,
            "contracting": self.contracting,
            "lookback_days": self.lookback_days,
        }


def _true_range(bar, prev_close):
    high = bar["high"]
    low = bar["low"]
    pc = prev_close
    return max(high - low, abs(high - pc), abs(low - pc))


def _atr_series(bars: List[dict], period: int) -> List[float]:
    """Wilder's smoothed ATR series. Returns a list aligned with bars[period:]."""
    if len(bars) < period + 1:
        return []
    trs = []
    prev_close = bars[0]["close"]
    for b in bars:
        trs.append(_true_range(b, prev_close))
        prev_close = b["close"]
    # initial ATR = simple average of first `period` TRs
    atr = sum(trs[:period]) / period
    out = [atr]
    for i in range(period, len(trs)):
        atr = (atr * (period - 1) + trs[i]) / period
        out.append(atr)
    return out


def _sma(series: List[float], period: int) -> Optional[float]:
    if len(series) < period:
        return None
    return sum(series[-period:]) / period


def _stdev(series: List[float], period: int) -> Optional[float]:
    if len(series) < period:
        return None
    window = series[-period:]
    mean = sum(window) / period
    var = sum((x - mean) ** 2 for x in window) / period
    return var ** 0.5


class VolatilityClassifier:
    def __init__(self, config: dict, logger: TradingLogger) -> None:
        self._logger = logger
        cfg = config or {}
        self.atr_period = int(cfg.get("atr_period", 14))
        self.lookback_days = int(cfg.get("lookback_days", 90))
        self.low_thr = float(cfg.get("low_threshold_percentile", 25))
        self.high_thr = float(cfg.get("high_threshold_percentile", 75))
        self.extreme_thr = float(cfg.get("extreme_threshold_percentile", 95))
        self.bb_period = int(cfg.get("bb_period", 20))

    def classify(self, bars: List[dict], current_time: datetime) -> VolatilitySnapshot:
        snap = VolatilitySnapshot(lookback_days=self.lookback_days)
        if not bars or len(bars) < self.atr_period + 1:
            self._logger.info("volatility: insufficient bars, safe NORMAL",
                              n=len(bars) if bars else 0)
            return snap

        atr_series = _atr_series(bars, self.atr_period)
        if not atr_series:
            return snap

        current_atr = atr_series[-1]
        snap.current_atr = current_atr

        # percentile of current ATR within the recent distribution.
        # Round to 8 dp so floating-point drift in a (near-)constant ATR series
        # does not flip the comparison; a constant series pins to 0% (LOW).
        hist = atr_series[:-1]  # exclude current
        if hist:
            cur_r = round(current_atr, 8)
            below = sum(1 for a in hist if round(a, 8) < cur_r)
            snap.atr_percentile = 100.0 * below / len(hist)
        else:
            snap.atr_percentile = 50.0

        # ATR as percentage of price (last close)
        last_close = bars[-1]["close"]
        snap.atr_percent = (current_atr / last_close) * 100.0 if last_close else 0.0

        # Bollinger-band width percentile (20-period, 2 sigma) using closes
        closes = [b["close"] for b in bars]
        mid = _sma(closes, self.bb_period)
        sd = _stdev(closes, self.bb_period)
        if mid is not None and sd is not None and mid != 0:
            width = 4.0 * sd / mid  # 2 sigma up + 2 sigma down
            # distribution of historical widths
            widths = []
            for j in range(self.bb_period, len(closes) + 1):
                w_mid = _sma(closes[:j], self.bb_period)
                w_sd = _stdev(closes[:j], self.bb_period)
                if w_mid and w_mid != 0:
                    widths.append(4.0 * w_sd / w_mid)
            if len(widths) > 1:
                below_w = sum(1 for w in widths[:-1] if w <= width)
                snap.bb_width_percentile = 100.0 * below_w / (len(widths) - 1)
            else:
                snap.bb_width_percentile = 50.0
        else:
            snap.bb_width_percentile = 50.0

        # expanding / contracting: current ATR vs ATR 5 bars ago
        if len(atr_series) > 5:
            prev = atr_series[-6]
            snap.expanding = current_atr > prev
            snap.contracting = current_atr < prev

        # level from ATR percentile thresholds
        snap.level = self._level(snap.atr_percentile)

        self._logger.info("volatility classified", vol_level=snap.level.value,
                          atr_pct=round(snap.atr_percentile, 1))
        return snap

    def _level(self, pct: float) -> VolatilityLevel:
        if pct < self.low_thr:
            return VolatilityLevel.LOW
        if pct < self.high_thr:
            return VolatilityLevel.NORMAL
        if pct < self.extreme_thr:
            return VolatilityLevel.HIGH
        return VolatilityLevel.EXTREME

    def get_status(self) -> dict:
        # convenience: callers may query last snapshot via classify; here we
        # return the schema with safe defaults (no stored snapshot).
        return VolatilitySnapshot(lookback_days=self.lookback_days).to_dict()
