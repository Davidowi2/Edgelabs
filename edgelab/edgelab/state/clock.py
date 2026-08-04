"""Clock and session detection.

NOTE (Phase 1): a module-level `broker_clock` (BrokerTime) is now available so
other modules can obtain broker-local time consistently. The original NY-based
`in_session` / `to_ny` behavior is preserved unchanged to keep existing tests
green. New code that needs broker time should use `broker_clock.now()`.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from edgelab.time.broker_time import BrokerTime

NY_TZ = ZoneInfo("America/New_York")

# Broker wall clock (TradeLocker-style UTC+3, US DST observed).
broker_clock = BrokerTime(offset="+3", dst=True)


class Clock:
    def __init__(self, session_windows: list[list[int]] | None = None) -> None:
        # None -> use the constitution's default NY windows.
        # []   -> NO session gate (strategy defines its own gating).
        self.session_windows = session_windows
        if self.session_windows is None:
            self.session_windows = [
                [8, 0, 11, 0],
                [13, 30, 16, 0],
            ]

    def now_ny(self) -> datetime:
        return datetime.now(NY_TZ)

    def to_ny(self, dt: datetime) -> datetime:
        return dt.astimezone(NY_TZ)

    def now_broker(self) -> datetime:
        """Current time in the broker's timezone (Phase 1 addition)."""
        return broker_clock.now()

    def in_session(self, dt: datetime) -> bool:
        # Empty list => no gate: always considered in session.
        if not self.session_windows:
            return True
        # Normalize to NY: if naive, assume it is already NY wall-clock time.
        local = self.to_ny(dt) if dt.tzinfo is not None else dt
        current_minutes = local.hour * 60 + local.minute
        for start_h, start_m, end_h, end_m in self.session_windows:
            start = start_h * 60 + start_m
            end = end_h * 60 + end_m
            if start <= current_minutes <= end:
                return True
        return False
