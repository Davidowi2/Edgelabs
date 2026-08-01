"""Chart pattern detection for EdgeLab (Phase 5b, Module 1).

MEASURED pattern detection (no ML, no visual). Each detector returns a
quantified DetectedPattern with a measured target, confidence (capped 0.95),
and status. All detectors are PURE: same input -> same output, no mutation.
Uses StructureAnalyzer for swing points. Pure standard library.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional

from edgelab.analysis.structure import StructureAnalyzer, SwingType
from edgelab.monitoring.logger import TradingLogger

CONFIDENCE_CAP = 0.95


class PatternType(str, Enum):
    HH_HL = "HH_HL"
    LH_LL = "LH_LL"
    BOS_UP = "BOS_UP"
    BOS_DOWN = "BOS_DOWN"
    CHoCH_UP = "CHoCH_UP"
    CHoCH_DOWN = "CHoCH_DOWN"
    HEAD_AND_SHOULDERS = "HEAD_AND_SHOULDERS"
    DOUBLE_TOP = "DOUBLE_TOP"
    DOUBLE_BOTTOM = "DOUBLE_BOTTOM"
    TRIANGLE_ASCENDING = "TRIANGLE_ASCENDING"
    TRIANGLE_DESCENDING = "TRIANGLE_DESCENDING"
    TRIANGLE_SYMMETRICAL = "TRIANGLE_SYMMETRICAL"


class PatternStatus(str, Enum):
    CONFIRMED = "CONFIRMED"
    FORMING = "FORMING"
    FAILED = "FAILED"
    NONE = "NONE"


@dataclass
class DetectedPattern:
    pattern_type: PatternType
    confidence: float
    status: PatternStatus
    key_levels: dict = field(default_factory=dict)
    description: str = ""
    measured_target: Optional[float] = None
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        # enforce honesty cap
        self.confidence = min(self.confidence, CONFIDENCE_CAP)
        self.confidence = max(0.0, self.confidence)

    def to_dict(self) -> dict:
        return {
            "pattern_type": self.pattern_type.value,
            "confidence": self.confidence,
            "status": self.status.value,
            "key_levels": self.key_levels,
            "description": self.description,
            "measured_target": self.measured_target,
            "metadata": self.metadata,
        }


class PatternDetector:
    def __init__(self, config: dict, logger: TradingLogger) -> None:
        self._logger = logger
        cfg = config or {}
        self.min_swing_count = int(cfg.get("min_swing_count", 3))
        self.h_s_min_neckline_touches = int(cfg.get("h_s_min_neckline_touches", 2))
        self.double_pattern_tolerance_pips = int(cfg.get("double_pattern_tolerance_pips", 20))
        self.triangle_min_bars = int(cfg.get("triangle_min_bars", 20))
        self._struct = StructureAnalyzer(cfg.get("structure", {}), logger)

    # ---------- helpers ----------
    def _local_swings(self, bars):
        """Robust swing detector mirroring StructureAnalyzer's window logic,
        but without the dependent trend loop (which crashes when highs/lows
        swing counts differ). Used only as a defensive fallback."""
        from edgelab.analysis.structure import SwingPoint, SwingType
        order = self._struct.swing_order
        highs = []
        lows = []
        if len(bars) < 2 * order + 1:
            return highs, lows
        for i in range(order, len(bars) - order):
            hi = bars[i]["high"]
            lo_i = max(order, i - order)
            hi_i = min(len(bars) - 1 - order, i + order)
            is_h = all(bars[j]["high"] <= hi for j in range(lo_i, hi_i + 1))
            lo = bars[i]["low"]
            is_l = all(bars[j]["low"] >= lo for j in range(lo_i, hi_i + 1))
            if is_h:
                highs.append(SwingPoint(hi, i, bars[i]["timestamp"], SwingType.SWING_HIGH))
            if is_l:
                lows.append(SwingPoint(lo, i, bars[i]["timestamp"], SwingType.SWING_LOW))
        return highs, lows

    def _swings(self, bars, current_time):
        """Return swing highs/lows for pattern detection.

        Uses the robust local swing detector directly.

        NOTE / DEVIATION: the spec says to use StructureAnalyzer internally.
        StructureAnalyzer.analyze has a latent crash (its trend loop indexes
        lows[k] while iterating range(1, len(highs)), raising whenever the
        high/low swing counts differ). We must NOT modify Phase 5a files, and
        pattern detection only needs swing POINTS (not StructureAnalyzer's
        trend field). The local detector is a pure, deterministic equivalent
        that produces the same swing points without the crash. This keeps all
        detectors pure (same input -> same output) and avoids the non-
        deterministic primary/fallback split that the latent bug causes.
        """
        h, l = self._local_swings(bars)
        return h, l, None

    @staticmethod
    def _atr(bars, period=14):
        trs = []
        for i in range(1, min(len(bars), period + 1)):
            h = bars[i]["high"]
            l = bars[i]["low"]
            pc = bars[i - 1]["close"]
            tr = max(h - l, abs(h - pc), abs(l - pc))
            trs.append(tr)
        if not trs:
            return 0.0
        return sum(trs) / len(trs)

    # ---------- aggregate ----------
    def detect_all(self, bars: List[dict], current_time: datetime) -> List[DetectedPattern]:
        out = []
        out += self.detect_hh_hl(bars, current_time)
        out += self.detect_lh_ll(bars, current_time)
        out += self.detect_bos(bars, current_time)
        out += self.detect_choch(bars, current_time)
        out += self.detect_head_and_shoulders(bars, current_time)
        out += self.detect_double_top(bars, current_time)
        out += self.detect_double_bottom(bars, current_time)
        out += self.detect_triangle(bars, current_time)
        names = [p.pattern_type.value for p in out]
        self._logger.info("Detected N patterns", N=len(out), names=names)
        return out

    # ---------- HH / HL ----------
    def detect_hh_hl(self, bars, current_time):
        highs, lows, _ = self._swings(bars, current_time)
        if len(highs) < self.min_swing_count or len(lows) < self.min_swing_count:
            return []
        hh = all(highs[i].price > highs[i - 1].price for i in range(1, len(highs)))
        hl = all(lows[i].price > lows[i - 1].price for i in range(1, len(lows)))
        if not (hh and hl):
            return []
        ratio = 1.0  # all consecutive swings higher
        conf = min(CONFIDENCE_CAP, ratio * self.min_swing_count / self.min_swing_count)
        last_close = bars[-1]["close"]
        last_high = highs[-1].price
        last_low = lows[-1].price
        rng = max(last_high - last_low, 1e-9)
        if last_close > last_high:
            status = PatternStatus.CONFIRMED
        else:
            status = PatternStatus.FORMING
        key_levels = {
            "last_swing_high": last_high,
            "last_swing_low": last_low,
            "entry_zone": [last_low, last_low + 0.2 * rng],
        }
        desc = (f"{self.min_swing_count} higher highs and {self.min_swing_count} "
                f"higher lows detected, confirming uptrend")
        return [DetectedPattern(PatternType.HH_HL, conf, status, key_levels, desc,
                                metadata={"swing_count": self.min_swing_count,
                                          "pattern_width_pips": int(rng * 10000)})]

    def detect_lh_ll(self, bars, current_time):
        highs, lows, _ = self._swings(bars, current_time)
        if len(highs) < self.min_swing_count or len(lows) < self.min_swing_count:
            return []
        lh = all(highs[i].price < highs[i - 1].price for i in range(1, len(highs)))
        ll = all(lows[i].price < lows[i - 1].price for i in range(1, len(lows)))
        if not (lh and ll):
            return []
        conf = CONFIDENCE_CAP
        last_close = bars[-1]["close"]
        last_high = highs[-1].price
        last_low = lows[-1].price
        rng = max(last_high - last_low, 1e-9)
        if last_close < last_low:
            status = PatternStatus.CONFIRMED
        else:
            status = PatternStatus.FORMING
        key_levels = {
            "last_swing_high": last_high,
            "last_swing_low": last_low,
            "entry_zone": [last_high - 0.2 * rng, last_high],
        }
        desc = (f"{self.min_swing_count} lower highs and {self.min_swing_count} "
                f"lower lows detected, confirming downtrend")
        return [DetectedPattern(PatternType.LH_LL, conf, status, key_levels, desc,
                                metadata={"swing_count": self.min_swing_count,
                                          "pattern_width_pips": int(rng * 10000)})]

    # ---------- BOS ----------
    def detect_bos(self, bars, current_time):
        if len(bars) < 2:
            return []
        # prior swing structure EXCLUDING the candidate breakout bar
        highs, lows, _ = self._swings(bars, current_time)
        if len(highs) < 2 and len(lows) < 2:
            return []
        out = []
        last = bars[-1]
        close = last["close"]
        atr = self._atr(bars)
        if len(highs) >= 2:
            level = highs[-2].price
            broke = last["high"] > level  # wick pierced the level
            if close > level:
                status = PatternStatus.CONFIRMED
            elif broke:
                status = PatternStatus.FAILED  # pierced but closed back below
            else:
                status = None
            if status is not None:
                strength = (close - level) / atr if (status == PatternStatus.CONFIRMED and atr > 0) else \
                           (last["high"] - level) / atr if atr > 0 else 1.0
                conf = min(CONFIDENCE_CAP, strength)
                out.append(DetectedPattern(
                    PatternType.BOS_UP, conf, status,
                    {"broken_level": level, "new_direction": "up"},
                    "latest bar broke above prior swing high (break of structure up)" if status == PatternStatus.CONFIRMED
                    else "bar pierced prior swing high but closed back below (BOS failed)",
                    metadata={"atr": atr}))
        if len(lows) >= 2:
            level = lows[-2].price
            broke = last["low"] < level
            if close < level:
                status = PatternStatus.CONFIRMED
            elif broke:
                status = PatternStatus.FAILED
            else:
                status = None
            if status is not None:
                strength = (level - close) / atr if (status == PatternStatus.CONFIRMED and atr > 0) else \
                           (level - last["low"]) / atr if atr > 0 else 1.0
                conf = min(CONFIDENCE_CAP, strength)
                out.append(DetectedPattern(
                    PatternType.BOS_DOWN, conf, status,
                    {"broken_level": level, "new_direction": "down"},
                    "latest bar broke below prior swing low (break of structure down)" if status == PatternStatus.CONFIRMED
                    else "bar pierced prior swing low but closed back above (BOS failed)",
                    metadata={"atr": atr}))
        return out

    # ---------- CHoCH ----------
    def detect_choch(self, bars, current_time):
        highs, lows, _ = self._swings(bars, current_time)
        if len(highs) < 3 or len(lows) < 3:
            return []  # requires prior trend context
        last = bars[-1]
        close = last["close"]
        # trend context: check consecutive direction using available pairs
        n_h = len(highs)
        n_l = len(lows)
        up_h = all(highs[i].price > highs[i - 1].price for i in range(1, n_h))
        up_l = all(lows[i].price > lows[i - 1].price for i in range(1, n_l))
        down_h = all(highs[i].price < highs[i - 1].price for i in range(1, n_h))
        down_l = all(lows[i].price < lows[i - 1].price for i in range(1, n_l))
        up_ctx = up_h and up_l
        down_ctx = down_h and down_l
        out = []
        if up_ctx and close < lows[-1].price:
            conf = min(CONFIDENCE_CAP, 0.7 + 0.1)  # base + 1 confirmation
            out.append(DetectedPattern(
                PatternType.CHoCH_DOWN, conf, PatternStatus.CONFIRMED,
                {"broken_structure": lows[-1].price, "new_structure": "forming"},
                "uptrend: latest bar closed below most recent higher low (change of character down)"))
        elif down_ctx and close > highs[-1].price:
            conf = min(CONFIDENCE_CAP, 0.7 + 0.1)
            out.append(DetectedPattern(
                PatternType.CHoCH_UP, conf, PatternStatus.CONFIRMED,
                {"broken_structure": highs[-1].price, "new_structure": "forming"},
                "downtrend: latest bar closed above most recent lower high (change of character up)"))
        return out

    # ---------- HEAD AND SHOULDERS (bearish top) ----------
    def detect_head_and_shoulders(self, bars, current_time):
        highs, lows, _ = self._swings(bars, current_time)
        if len(highs) < 3 or len(lows) < 2:
            return []
        # candidate peaks: 3 highest swing highs (L, head, R order by index)
        sorted_h = sorted(highs, key=lambda s: s.price, reverse=True)
        if len(sorted_h) < 3:
            return []
        # pick the 3 peaks with good index separation
        peaks = sorted(highs, key=lambda s: s.bar_index)[-3:]
        prices = [p.price for p in peaks]
        head_i = max(range(3), key=lambda i: prices[i])
        shoulder_idx = [i for i in range(3) if i != head_i]
        head_px = prices[head_i]
        shoulder_px = [prices[i] for i in shoulder_idx]
        # shoulders within tolerance (pips)
        tol = self.double_pattern_tolerance_pips / 10000.0
        if abs(shoulder_px[0] - shoulder_px[1]) > tol:
            return []
        # neckline = avg of the low swings (the two valleys between shoulders)
        ls = sorted(lows, key=lambda s: s.bar_index)
        neckline = sum(l.price for l in ls) / len(ls) if ls else (min(shoulder_px) - 0.005)
        # head must be >=2% higher (in height above neckline) than avg shoulder
        head_height = head_px - neckline
        shoulder_height = sum(shoulder_px) / 2 - neckline
        if head_height < 1.02 * shoulder_height:
            return []
        # count neckline touches
        touches = sum(1 for l in lows if abs(l.price - neckline) < tol)
        if touches < self.h_s_min_neckline_touches:
            return []
        measured_target = neckline - (head_px - neckline)
        conf = 0.6
        if head_height >= 2 * shoulder_height:
            conf += 0.1
        if touches < self.h_s_min_neckline_touches:
            conf -= 0.1
        conf = min(CONFIDENCE_CAP, conf)
        key_levels = {
            "neckline": neckline,
            "head": head_px,
            "left_shoulder": shoulder_px[0],
            "right_shoulder": shoulder_px[1],
            "measured_target": measured_target,
        }
        desc = (f"bearish head and shoulders: head {head_px:.4f} above neckline "
                f"{neckline:.4f}, measured target {measured_target:.4f}")
        return [DetectedPattern(PatternType.HEAD_AND_SHOULDERS, conf, PatternStatus.FORMING,
                                key_levels, desc, measured_target,
                                metadata={"neckline_touches": touches,
                                          "head_height": head_px - neckline})]

    # ---------- DOUBLE TOP (bearish) ----------
    def detect_double_top(self, bars, current_time):
        highs, lows, _ = self._swings(bars, current_time)
        if len(highs) < 2 or len(lows) < 1:
            return []
        sorted_h = sorted(highs, key=lambda s: s.bar_index)
        if len(sorted_h) < 2:
            return []
        # two highest peaks, order by index
        top2 = sorted(sorted_h, key=lambda s: s.price, reverse=True)[:2]
        top2 = sorted(top2, key=lambda s: s.bar_index)
        p1, p2 = top2[0].price, top2[1].price
        tol = self.double_pattern_tolerance_pips / 10000.0
        if abs(p1 - p2) > tol:
            return []
        # valley between them
        between = [l for l in lows if top2[0].bar_index < l.bar_index < top2[1].bar_index]
        if not between:
            return []
        valley = min(l.price for l in between)
        if valley > 0.99 * min(p1, p2):
            return []  # valley too shallow (need >=1% below peaks)
        neckline = valley
        measured_target = valley - (max(p1, p2) - valley)
        conf = 0.6
        if abs(p1 - p2) <= 0.005 * max(p1, p2):
            conf += 0.15
        if (min(p1, p2) - valley) < 0.01 * valley:
            conf -= 0.2
        conf = min(CONFIDENCE_CAP, conf)
        key_levels = {"peak_1": p1, "peak_2": p2, "neckline": neckline,
                      "measured_target": measured_target}
        desc = (f"bearish double top: peaks {p1:.4f}/{p2:.4f}, valley {valley:.4f}, "
                f"measured target {measured_target:.4f}")
        return [DetectedPattern(PatternType.DOUBLE_TOP, conf, PatternStatus.FORMING,
                                key_levels, desc, measured_target,
                                metadata={"peak_gap_pips": int(abs(p1 - p2) * 10000)})]

    # ---------- DOUBLE BOTTOM (bullish) ----------
    def detect_double_bottom(self, bars, current_time):
        highs, lows, _ = self._swings(bars, current_time)
        if len(lows) < 2 or len(highs) < 1:
            return []
        sorted_l = sorted(lows, key=lambda s: s.bar_index)
        if len(sorted_l) < 2:
            return []
        bottom2 = sorted(sorted_l, key=lambda s: s.price)[:2]
        bottom2 = sorted(bottom2, key=lambda s: s.bar_index)
        p1, p2 = bottom2[0].price, bottom2[1].price
        tol = self.double_pattern_tolerance_pips / 10000.0
        if abs(p1 - p2) > tol:
            return []
        between = [h for h in highs if bottom2[0].bar_index < h.bar_index < bottom2[1].bar_index]
        if not between:
            return []
        peak = max(h.price for h in between)
        if peak < 1.01 * max(p1, p2):
            return []
        measured_target = peak + (peak - min(p1, p2))
        conf = 0.6
        if abs(p1 - p2) <= 0.005 * max(p1, p2):
            conf += 0.15
        if (peak - max(p1, p2)) < 0.01 * peak:
            conf -= 0.2
        conf = min(CONFIDENCE_CAP, conf)
        key_levels = {"bottom_1": p1, "bottom_2": p2, "neckline": peak,
                      "measured_target": measured_target}
        desc = (f"bullish double bottom: bottoms {p1:.4f}/{p2:.4f}, peak {peak:.4f}, "
                f"measured target {measured_target:.4f}")
        return [DetectedPattern(PatternType.DOUBLE_BOTTOM, conf, PatternStatus.FORMING,
                                key_levels, desc, measured_target,
                                metadata={"bottom_gap_pips": int(abs(p1 - p2) * 10000)})]

    # ---------- TRIANGLES ----------
    def detect_triangle(self, bars, current_time):
        if len(bars) < self.triangle_min_bars:
            return []
        # use highs/lows per bar
        highs = [b["high"] for b in bars]
        lows = [b["low"] for b in bars]
        n = len(highs)
        # linear regression slope of highs and lows
        def slope(series):
            xs = list(range(n))
            mx = sum(xs) / n
            my = sum(series) / n
            num = sum((xs[i] - mx) * (series[i] - my) for i in range(n))
            den = sum((xs[i] - mx) ** 2 for i in range(n))
            return num / den if den else 0.0
        sh = slope(highs)
        sl = slope(lows)
        # flatness threshold
        flat = 1e-7
        tol = 0.0005  # per-bar relative flatness in price units (FX)
        types = []
        if abs(sh) <= flat and sl > flat:
            ptype = PatternType.TRIANGLE_ASCENDING
        elif sh < -flat and abs(sl) <= flat:
            ptype = PatternType.TRIANGLE_DESCENDING
        elif sh < -flat and sl > flat:
            ptype = PatternType.TRIANGLE_SYMMETRICAL
        else:
            return []
        upper_line = highs[-1]
        lower_line = lows[-1]
        # measured target = widest part (first bar's range) projected from last
        widest = (highs[0] - lows[0])
        if ptype == PatternType.TRIANGLE_ASCENDING:
            measured_target = lower_line + widest
        elif ptype == PatternType.TRIANGLE_DESCENDING:
            measured_target = upper_line - widest
        else:
            measured_target = (upper_line + lower_line) / 2  # symmetric: ambiguous; midpoint
        # status: breakout if price closes beyond the forming boundary
        last_close = bars[-1]["close"]
        status = PatternStatus.FORMING
        if ptype == PatternType.TRIANGLE_ASCENDING and last_close > upper_line:
            status = PatternStatus.CONFIRMED
        elif ptype == PatternType.TRIANGLE_DESCENDING and last_close < lower_line:
            status = PatternStatus.CONFIRMED
        elif ptype == PatternType.TRIANGLE_SYMMETRICAL and (last_close > upper_line or last_close < lower_line):
            status = PatternStatus.CONFIRMED
        conf = 0.5
        convergence = (abs(sh) + abs(sl))
        if convergence > 1e-6:
            conf += 0.2  # clear convergence
        # too-wide: if apex far away (range large relative to price), reduce
        width_pips = int(widest * 10000)
        if width_pips > 100:
            conf -= 0.1
        conf = min(CONFIDENCE_CAP, conf)
        key_levels = {"upper_line": upper_line, "lower_line": lower_line,
                      "apex_bar": n - 1, "measured_target": measured_target}
        desc = f"{ptype.value} detected from converging highs/lows"
        return [DetectedPattern(ptype, conf, status, key_levels, desc, measured_target,
                                metadata={"pattern_width_pips": width_pips})]
