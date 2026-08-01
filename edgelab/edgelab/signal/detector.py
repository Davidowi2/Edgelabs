"""Base signal detector for EdgeLab (Phase 7, Module 1).

Detects the 200 EMA pullback base signal on XAUUSD H4. This is Signal 1 of the
3-way confluence. It ONLY detects the raw setup (momentum / pullback). It does
NOT check structure or regime -- those are separate signals (Phase 5b / 6).

Long-only, XAUUSD-only, H4-only for Phase 7. Pure standard library.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional


class SignalType(str, Enum):
    EMA_PULLBACK_LONG = "EMA_PULLBACK_LONG"
    EMA_PULLBACK_SHORT = "EMA_PULLBACK_SHORT"  # reserved for future phases


@dataclass
class BaseSignal:
    signal_type: SignalType
    symbol: str
    timeframe: str
    timestamp: datetime
    bar_index: int
    entry_price: float
    stop_loss: float
    target_1: float
    target_2: float
    atr_at_signal: float
    trend_confirmed: bool
    pullback_distance_atr: float
    reversal_candle_type: str  # "engulfing" | "pin_bar" | "none"
    rsi_at_signal: float
    signal_confidence: float = 0.5
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "signal_type": self.signal_type.value,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "bar_index": self.bar_index,
            "entry_price": self.entry_price,
            "stop_loss": self.stop_loss,
            "target_1": self.target_1,
            "target_2": self.target_2,
            "atr_at_signal": self.atr_at_signal,
            "trend_confirmed": self.trend_confirmed,
            "pullback_distance_atr": self.pullback_distance_atr,
            "reversal_candle_type": self.reversal_candle_type,
            "rsi_at_signal": self.rsi_at_signal,
            "signal_confidence": self.signal_confidence,
            "metadata": self.metadata,
        }


class SignalDetector:
    def __init__(self, config: dict, logger) -> None:
        self._logger = logger
        cfg = config or {}
        self.ema_period = int(cfg.get("ema_period", 200))
        self.atr_period = int(cfg.get("atr_period", 14))
        self.rsi_period = int(cfg.get("rsi_period", 14))
        self.pullback_distance_atr_max = float(cfg.get("pullback_distance_atr_max", 1.5))
        self.rsi_oversold_threshold = float(cfg.get("rsi_oversold_threshold", 30.0))
        self.min_candle_body_ratio = float(cfg.get("min_candle_body_ratio", 0.5))
        # minimum bars needed: EMA warmup + ATR warmup + buffer
        self.min_bars = self.ema_period + self.atr_period

    # ---------- indicators (standard definitions) ----------
    def calculate_ema(self, bars: List[dict], period: int) -> List[float]:
        closes = [b["close"] for b in bars]
        if len(closes) < period:
            return []
        k = 2.0 / (period + 1)
        ema = sum(closes[:period]) / period
        out = [ema]
        for p in closes[period:]:
            ema = p * k + ema * (1 - k)
            out.append(ema)
        return out

    def calculate_atr(self, bars: List[dict], period: int) -> List[float]:
        if len(bars) < period + 1:
            return []
        trs = []
        for i in range(1, len(bars)):
            h = bars[i]["high"]
            l = bars[i]["low"]
            pc = bars[i - 1]["close"]
            trs.append(max(h - l, abs(h - pc), abs(l - pc)))
        atr = sum(trs[:period]) / period
        out = [atr]
        for v in trs[period:]:
            atr = (atr * (period - 1) + v) / period
            out.append(atr)
        return out

    def calculate_rsi(self, bars: List[dict], period: int) -> List[float]:
        closes = [b["close"] for b in bars]
        if len(closes) < period + 1:
            return []

        def _rsi(ag, al):
            if al == 0 and ag == 0:
                return 50.0
            if al == 0:
                return 100.0
            if ag == 0:
                return 0.0
            rs = ag / al
            return 100.0 - 100.0 / (1.0 + rs)

        gains = []
        losses = []
        for i in range(1, len(closes)):
            d = closes[i] - closes[i - 1]
            gains.append(max(d, 0.0))
            losses.append(max(-d, 0.0))
        ag = sum(gains[:period]) / period
        al = sum(losses[:period]) / period
        out = [_rsi(ag, al)]
        for i in range(period, len(gains)):
            ag = (ag * (period - 1) + gains[i]) / period
            al = (al * (period - 1) + losses[i]) / period
            out.append(_rsi(ag, al))
        return out

    def detect_reversal_candle(self, bar: dict, prev_bar: Optional[dict] = None) -> Optional[str]:
        o = bar["open"]
        h = bar["high"]
        l = bar["low"]
        c = bar["close"]
        rng = h - l
        if rng <= 0:
            return None
        body = c - o
        # bullish engulfing: current bullish, prior bearish, current body engulfs prior
        if prev_bar is not None:
            po = prev_bar["open"]
            pc = prev_bar["close"]
            if c > o and pc < po and o <= pc and c >= po:
                return "engulfing"
        # bullish pin bar: small body near the top, long lower wick
        upper_wick = h - max(o, c)
        lower_wick = min(o, c) - l
        if (body > 0 and body <= 0.33 * rng
                and lower_wick >= 2.0 * body and lower_wick > upper_wick
                and lower_wick >= 0.6 * rng):
            return "pin_bar"
        return None

    # ---------- detection ----------
    def detect(self, bars: List[dict], current_time: datetime,
               symbol: str = "XAUUSD") -> Optional[BaseSignal]:
        if symbol != "XAUUSD":
            self._logger.debug("signal detector: only XAUUSD supported", symbol=symbol)
            return None
        if len(bars) < self.min_bars:
            self._logger.debug("signal detector: insufficient bars",
                               have=len(bars), need=self.min_bars)
            return None

        ema = self.calculate_ema(bars, self.ema_period)
        atr = self.calculate_atr(bars, self.atr_period)
        rsi = self.calculate_rsi(bars, self.rsi_period)
        if not ema or not atr or not rsi or len(rsi) < 2 or len(ema) < 5:
            return None

        ema_now = ema[-1]
        atr_now = atr[-1]
        rsi_now = rsi[-1]
        rsi_prev = rsi[-2]
        cur = bars[-1]

        # 5a: trend -- EMA sloping up (last 5 EMA values strictly increasing)
        last5 = ema[-5:]
        trend_up = all(last5[i] < last5[i + 1] for i in range(4))
        # 5b: price above 200 EMA
        price_above = cur["close"] > ema_now
        # 5c: pullback within N x ATR of the EMA
        dist = abs(cur["close"] - ema_now)
        pullback_ok = atr_now > 0 and dist <= self.pullback_distance_atr_max * atr_now
        # 5d: reversal candle (bullish, body > 50% of range)
        rc = self.detect_reversal_candle(cur, bars[-2] if len(bars) >= 2 else None)
        rng = cur["high"] - cur["low"]
        candle_ok = (cur["close"] > cur["open"] and rng > 0
                     and (cur["close"] - cur["open"]) / rng >= self.min_candle_body_ratio)
        # 5e: RSI crossing above oversold
        rsi_ok = (rsi_now > self.rsi_oversold_threshold
                  and rsi_prev < self.rsi_oversold_threshold)

        if not (trend_up and price_above and pullback_ok and rc is not None
                and candle_ok and rsi_ok):
            return None

        entry = cur["close"]
        sl = cur["low"] - 2.0 * atr_now
        risk = entry - sl
        t1 = entry + 2.0 * risk
        t2 = entry + 3.0 * risk
        rc_type = rc if rc is not None else "none"

        sig = BaseSignal(
            signal_type=SignalType.EMA_PULLBACK_LONG,
            symbol=symbol,
            timeframe="H4",
            timestamp=current_time,
            bar_index=len(bars) - 1,
            entry_price=entry,
            stop_loss=sl,
            target_1=t1,
            target_2=t2,
            atr_at_signal=atr_now,
            trend_confirmed=trend_up,
            pullback_distance_atr=(dist / atr_now) if atr_now > 0 else 0.0,
            reversal_candle_type=rc_type,
            rsi_at_signal=rsi_now,
            signal_confidence=0.5,
            metadata={
                "ema200": round(ema_now, 4),
                "rsi14": round(rsi_now, 4),
                "atr14": round(atr_now, 4),
                "pullback_distance_atr": round((dist / atr_now) if atr_now > 0 else 0.0, 4),
                "reversal_type": rc_type,
            },
        )
        self._logger.info("base signal detected", symbol=symbol, entry=round(entry, 2),
                          sl=round(sl, 2), t1=round(t1, 2), atr=round(atr_now, 3))
        return sig
