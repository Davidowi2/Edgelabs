"""Spread shock guard for EdgeLab (Phase 8, Module 1).

Detects abnormal spread conditions and blocks trades when the spread is too
wide. Compares the current spread to a ROLLING BASELINE MEDIAN (not just a
static ceiling) and supports session-aware absolute ceilings. Pure standard
library only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional


class SpreadVerdict(str, Enum):
    OK = "OK"
    ELEVATED = "ELEVATED"
    SHOCK = "SHOCK"
    BLOCKED = "BLOCKED"


@dataclass
class SpreadSnapshot:
    current_spread: float
    baseline_median: float
    baseline_samples: int
    percentile: float
    verdict: SpreadVerdict
    reason: str = ""
    cooldown_until: Optional[datetime] = None


class SpreadGuard:
    def __init__(self, config: dict, logger) -> None:
        cfg = config or {}
        self._logger = logger
        self.max_spread_points = float(cfg.get("max_spread_points", 35.0))
        self.shock_multiplier = float(cfg.get("shock_multiplier", 2.0))
        self.elevated_multiplier = float(cfg.get("elevated_multiplier", 1.5))
        self.baseline_window = int(cfg.get("baseline_window", 60))
        self.cooldown_after_shock_seconds = float(
            cfg.get("cooldown_after_shock_seconds", 900))
        self.session_max_overrides = dict(cfg.get("session_max_overrides", {}) or {})
        self._samples: List[float] = []
        self._cooldown_until: Optional[datetime] = None

    # ---------- baseline ----------
    def update_baseline(self, spread: float) -> None:
        self._samples.append(float(spread))
        if len(self._samples) > self.baseline_window:
            self._samples.pop(0)

    def _baseline_median(self) -> float:
        if not self._samples:
            return 0.0
        s = sorted(self._samples)
        n = len(s)
        mid = n // 2
        if n % 2 == 1:
            return s[mid]
        return (s[mid - 1] + s[mid]) / 2.0

    def _percentile_rank(self, value: float) -> float:
        """Percentile rank of `value` within the baseline (0-100), where the
        maximum value returns 100.0."""
        if not self._samples:
            return 0.0
        below = sum(1 for s in self._samples if s < value)
        equal = sum(1 for s in self._samples if s == value)
        return (below + equal) / len(self._samples) * 100.0

    # ---------- session ----------
    def _get_session(self, current_time: datetime) -> str:
        # Use the wall-clock hour in UTC for session classification.
        try:
            dt = current_time
            if dt.tzinfo is not None:
                from datetime import timezone as _tz
                dt = dt.astimezone(_tz.utc)
            hour = dt.hour
        except Exception:
            hour = 0
        if 22 <= hour or hour < 8:
            return "asian"
        if 8 <= hour < 13:
            return "london"
        if 13 <= hour < 17:
            return "overlap"
        return "ny"  # 17 <= hour < 22

    # ---------- check ----------
    def check_spread(self, current_spread: float, current_time: datetime) -> SpreadSnapshot:
        session = self._get_session(current_time)
        reason = ""

        # Step 1 (reordered from spec): insufficient baseline -> OK.
        # During warmup we have no baseline to judge abnormality, so we are
        # permissive rather than falsely blocking. (Spec step 4 promoted here
        # so the absolute ceiling does not fire on a single huge sample before
        # the rolling baseline exists.)
        if len(self._samples) < 10:
            snap = SpreadSnapshot(
                current_spread=current_spread,
                baseline_median=self._baseline_median(),
                baseline_samples=len(self._samples),
                percentile=self._percentile_rank(current_spread),
                verdict=SpreadVerdict.OK,
                reason="insufficient baseline samples",
            )
            return snap

        # Step 2: session-specific absolute ceiling
        ceiling = self.session_max_overrides.get(session, self.max_spread_points)
        if current_spread > ceiling:
            verdict = SpreadVerdict.BLOCKED
            reason = f"spread {current_spread:.1f} > {ceiling:.1f} ceiling ({session})"
            snap = SpreadSnapshot(
                current_spread=current_spread,
                baseline_median=self._baseline_median(),
                baseline_samples=len(self._samples),
                percentile=self._percentile_rank(current_spread),
                verdict=verdict, reason=reason,
                cooldown_until=self._cooldown_until,
            )
            self._logger.warning("spread blocked", spread=current_spread, session=session)
            return snap

        median = self._baseline_median()
        pct = self._percentile_rank(current_spread)

        # Step 5: SHOCK
        if median > 0 and current_spread > self.shock_multiplier * median:
            verdict = SpreadVerdict.SHOCK
            reason = (f"spread {current_spread:.1f} > {self.shock_multiplier}x "
                      f"baseline median {median:.1f}")
            try:
                from datetime import timedelta
                self._cooldown_until = current_time + timedelta(
                    seconds=self.cooldown_after_shock_seconds)
            except Exception:
                self._cooldown_until = None
            snap = SpreadSnapshot(
                current_spread=current_spread, baseline_median=median,
                baseline_samples=len(self._samples), percentile=pct,
                verdict=verdict, reason=reason,
                cooldown_until=self._cooldown_until,
            )
            self._logger.warning("spread shock", spread=current_spread, median=median)
            return snap

        # Step 6: ELEVATED
        if median > 0 and current_spread > self.elevated_multiplier * median:
            verdict = SpreadVerdict.ELEVATED
            reason = (f"spread {current_spread:.1f} > {self.elevated_multiplier}x "
                      f"baseline median {median:.1f}")
            snap = SpreadSnapshot(
                current_spread=current_spread, baseline_median=median,
                baseline_samples=len(self._samples), percentile=pct,
                verdict=verdict, reason=reason,
                cooldown_until=self._cooldown_until,
            )
            return snap

        # Step 7: OK
        snap = SpreadSnapshot(
            current_spread=current_spread, baseline_median=median,
            baseline_samples=len(self._samples), percentile=pct,
            verdict=SpreadVerdict.OK, reason="spread within normal range",
            cooldown_until=self._cooldown_until,
        )
        return snap

    # ---------- helpers ----------
    def is_blocked(self, snapshot: SpreadSnapshot) -> bool:
        return snapshot.verdict in (SpreadVerdict.SHOCK, SpreadVerdict.BLOCKED)

    def get_cooldown_remaining(self, current_time: datetime) -> float:
        if self._cooldown_until is None:
            return 0.0
        try:
            delta = (self._cooldown_until - current_time).total_seconds()
        except Exception:
            return 0.0
        return max(0.0, delta)
