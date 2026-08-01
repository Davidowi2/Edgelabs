"""Broker-time handling for EdgeLab.

The live trading system operates in the *broker's* timezone (e.g. TradeLocker
servers typically run at UTC+3, observing US DST). Naive UTC math is the single
most common source of silent session/timing bugs, so all timestamp logic in the
system should route through BrokerTime.

Only the Python standard library is used. No third-party dependencies.

Session boundaries (broker-local hours):
    asian     00:00 - 07:00
    london    07:00 - 12:00
    overlap   12:00 - 16:00   (London still open AND New York open)
    ny        12:00 - 16:00   (treated identically to overlap at the hour level)
    closed    everything else
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

# US DST window: second Sunday of March -> first Sunday of November.
_DST_START_MONTH = 3
_DST_END_MONTH = 11

logger = logging.getLogger(__name__)


# Phase 1.5 hotfix: timezone-trap guardrails.
# UTC offsets legally range from UTC-12 (Baker/Howland) to UTC+14 (Line Islands).
# Anything outside that is impossible. A few Pacific zones use UTC+13/+14, which
# is rare (and worth warning about) but not wrong.
MAX_REASONABLE_OFFSET = 14   # hours, hard max (UTC+14)
UNUSUAL_OFFSET = 12          # hours; >=12 is unusual (Pacific islands only)
REJECT_BELOW = -12           # hours, hard min (UTC-12)
ACCEPT_BELOW = -11           # hours; >= -11 is valid (e.g. UTC-11 American Samoa)


def _validate_offset(offset_str: str | int) -> tuple[int, bool, str]:
    """Validate a broker timezone offset before construction.

    Returns ``(parsed_hours, is_valid, message)``.

    * greater than +14  -> invalid (impossible)
    * less than -12     -> invalid (impossible)
    * between +12..+14  -> valid, but unusual (warns)
    * everything else   -> valid, silent
    """
    if isinstance(offset_str, int):
        parsed = offset_str
    else:
        s = str(offset_str).strip()
        if s in ("", "+", "-"):
            raise ValueError(f"Invalid timezone offset: {offset_str!r}")
        sign = 1
        if s[0] in "+-":
            if s[0] == "-":
                sign = -1
            s = s[1:]
        if not s.isdigit():
            raise ValueError(f"Invalid timezone offset: {offset_str!r}")
        parsed = sign * int(s)

    if parsed > MAX_REASONABLE_OFFSET:
        return (parsed, False,
                f"Offset +{parsed} is beyond UTC+{MAX_REASONABLE_OFFSET} max. Possible typo?")
    if parsed < REJECT_BELOW:
        return (parsed, False,
                f"Offset {parsed} is beyond UTC{REJECT_BELOW} min. Possible typo?")
    if parsed >= UNUSUAL_OFFSET:
        return (parsed, True, f"Offset +{parsed} is unusual. Verify broker timezone.")
    return (parsed, True, "")


def _parse_offset(offset: str | int) -> int:
    """Return a timezone offset in minutes from a string like '+3', '-5', '+0' or int."""
    if isinstance(offset, int):
        return offset * 60
    s = str(offset).strip()
    if s in ("", "+", "-"):
        raise ValueError(f"Invalid timezone offset: {offset!r}")
    sign = 1
    if s[0] in "+-":
        if s[0] == "-":
            sign = -1
        s = s[1:]
    if not s.isdigit():
        raise ValueError(f"Invalid timezone offset: {offset!r}")
    return sign * int(s) * 60


def _us_dst_active(dt_utc: datetime) -> bool:
    """True if the given UTC datetime falls inside the US DST window."""
    if dt_utc.month < _DST_START_MONTH or dt_utc.month > _DST_END_MONTH:
        return False
    if dt_utc.month > _DST_START_MONTH and dt_utc.month < _DST_END_MONTH:
        return True
    # March: after the second Sunday. November: before the first Sunday.
    year = dt_utc.year

    def _nth_weekday(year: int, month: int, weekday: int, n: int) -> int:
        # weekday: Monday=0 ... Sunday=6
        first = datetime(year, month, 1)
        offset = (weekday - first.weekday()) % 7
        return 1 + offset + (n - 1) * 7

    if dt_utc.month == _DST_START_MONTH:  # March: starts 2nd Sunday at 02:00 local
        start_day = _nth_weekday(year, 3, 6, 2)  # Sunday=6, 2nd
        return dt_utc.day > start_day or (dt_utc.day == start_day and dt_utc.hour >= 2)
    # November: ends 1st Sunday at 02:00 local
    end_day = _nth_weekday(year, 11, 6, 1)
    return dt_utc.day < end_day or (dt_utc.day == end_day and dt_utc.hour < 2)


class BrokerTime:
    """Timezone-aware clock pinned to the broker's wall clock."""

    # Phase 1.5 hotfix guardrails (re-exported as class constants)
    MAX_REASONABLE_OFFSET = MAX_REASONABLE_OFFSET
    UNUSUAL_OFFSET = UNUSUAL_OFFSET
    REJECT_BELOW = REJECT_BELOW
    ACCEPT_BELOW = ACCEPT_BELOW

    @classmethod
    def _validate_offset(cls, offset_str: str | int) -> tuple[int, bool, str]:
        """Validate a broker offset (see module-level ``_validate_offset``)."""
        return _validate_offset(offset_str)

    def __init__(self, offset: str | int = "+0", dst: bool = True) -> None:
        # Phase 1.5 hotfix: fail LOUDLY on impossible offsets instead of
        # silently producing 3 months of corrupt timestamps.
        parsed, is_valid, msg = self._validate_offset(offset)
        if not is_valid:
            raise ValueError(msg)
        if msg:
            logger.warning("BrokerTime unusual offset: %s", msg)

        self.offset_minutes = _parse_offset(offset)
        self.dst = dst
        effective = self._effective_offset_minutes(datetime.now(timezone.utc))
        logger.info(
            "BrokerTime initialized",
            extra={
                "configured_offset_min": self.offset_minutes,
                "dst_enabled": self.dst,
                "effective_offset_min": effective,
            },
        )

    # ----- offset resolution -----
    def _effective_offset_minutes(self, dt_utc: datetime) -> int:
        shift = 60 if (self.dst and _us_dst_active(dt_utc)) else 0
        return self.offset_minutes + shift

    def _tz(self, dt_utc: datetime) -> timezone:
        return timezone(timedelta(minutes=self._effective_offset_minutes(dt_utc)))

    # ----- public API -----
    def now(self) -> datetime:
        dt_utc = datetime.now(timezone.utc)
        return dt_utc.astimezone(self._tz(dt_utc))

    def utc_now(self) -> datetime:
        return datetime.now(timezone.utc)

    def to_broker_time(self, dt: datetime) -> datetime:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(self._tz(dt.astimezone(timezone.utc)))

    def to_utc(self, dt: datetime) -> datetime:
        if dt.tzinfo is None:
            # Interpret naive input as broker-local time.
            return dt.replace(tzinfo=self._tz(datetime.now(timezone.utc))).astimezone(timezone.utc)
        return dt.astimezone(timezone.utc)

    def is_weekend(self, dt: datetime | None = None) -> bool:
        ref = (dt or self.now()).astimezone(timezone.utc)
        return ref.weekday() >= 5  # Saturday=5, Sunday=6

    def session_name(self, hour: int) -> str:
        if 0 <= hour < 7:
            return "asian"
        if 7 <= hour < 12:
            return "london"
        if 12 <= hour < 16:
            # London/NY overlap window. At the hour level "ny" and "overlap"
            # are the same band (12:00-16:00 broker time), so we label it
            # "overlap" per the spec's emphasis on the combined window.
            return "overlap"
        return "closed"

    def minutes_since(self, dt: datetime) -> int:
        return int((self.now() - self.to_broker_time(dt)).total_seconds() // 60)

    def minutes_until(self, dt: datetime) -> int:
        return int((self.to_broker_time(dt) - self.now()).total_seconds() // 60)
