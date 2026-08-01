"""News filter core for EdgeLab (Phase 2, Module 3).

The ``NewsFilter`` answers two questions for a given symbol:
  * is_trading_allowed(symbol, now) -> (bool, reason)
  * get_size_multiplier(symbol, now) -> float   (0.5 on high-impact days)

Design rules (locked by the phase spec):
  * All timestamps use BrokerTime (broker GMT+3), never naive UTC.
  * Huge-impact events (FOMC, NFP, CPI) get a 60/60 min buffer.
  * HIGH impact: 30/30 min. MEDIUM: 15/15 min. LOW: no block.
  * Fail open: if data is unavailable the system trades WITHOUT filtering.
  * Every decision is logged (DEBUG for audit, INFO for key decisions).

Only the standard library is used.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import List, Optional, Tuple

from edgelab.news.currency_map import get_currencies_for_symbol
from edgelab.news.static_config import NewsEvent, load_events_from_json
from edgelab.monitoring.logger import TradingLogger
from edgelab.time.broker_time import BrokerTime

# Events that get an extended 60/60 buffer regardless of "impact" label.
EXTENDED_EVENT_KEYWORDS = ("FOMC", "Non-Farm Payrolls", "NFP", "CPI")
EXTENDED_PRE = 60
EXTENDED_POST = 60


class NewsFilter:
    def __init__(
        self,
        config: dict,
        static_events: List[NewsEvent],
        logger: TradingLogger,
        broker_time: BrokerTime,
    ) -> None:
        self._config = config or {}
        self._events = list(static_events or [])
        self._logger = logger
        self._bt = broker_time

        self.high_pre = int(self._config.get("high_impact_pre_minutes", 30))
        self.high_post = int(self._config.get("high_impact_post_minutes", 30))
        self.med_pre = int(self._config.get("medium_impact_pre_minutes", 15))
        self.med_post = int(self._config.get("medium_impact_post_minutes", 15))
        self.size_reduction = float(self._config.get("high_impact_day_size_reduction", 0.5))

    # ----- internal helpers -----
    def _relevant_events(self, symbol: str) -> List[NewsEvent]:
        currencies = get_currencies_for_symbol(symbol)
        if not currencies:
            return []
        return [e for e in self._events if e.currency in currencies]

    def _windows(self, event: NewsEvent) -> Tuple[int, int]:
        name = (event.name or "").upper()
        if any(k.upper() in name for k in EXTENDED_EVENT_KEYWORDS):
            return EXTENDED_PRE, EXTENDED_POST
        if event.impact == "high":
            return self.high_pre, self.high_post
        if event.impact == "medium":
            return self.med_pre, self.med_post
        return 0, 0  # low impact -> no block

    def _as_broker(self, dt_utc: datetime) -> datetime:
        return self._bt.to_broker_time(dt_utc)

    # ----- public API -----
    def is_trading_allowed(
        self, symbol: str, current_time: Optional[datetime] = None
    ) -> Tuple[bool, str]:
        now = self._as_broker(current_time) if current_time is not None else self._bt.now()
        events = self._relevant_events(symbol)
        if not events:
            self._logger.debug("news check: no relevant events", symbol=symbol, allowed=True)
            return True, "no relevant events"

        for ev in events:
            ev_broker = self._as_broker(ev.datetime_utc)
            pre, post = self._windows(ev)
            if pre <= 0 and post <= 0:
                continue
            delta_min = (ev_broker - now).total_seconds() / 60.0
            if -post <= delta_min <= pre:
                if delta_min >= 0:
                    reason = f"pre-blackout: {ev.name}"
                else:
                    reason = f"post-blackout: {ev.name}"
                if ev.impact == "medium":
                    reason = f"medium-impact blackout: {ev.name}"
                self._logger.info(
                    "trade blocked by news", symbol=symbol, reason=reason,
                    event_utc=ev.datetime_utc.isoformat(),
                )
                return False, reason
        self._logger.debug("news check passed", symbol=symbol, allowed=True)
        return True, "outside all blackouts"

    def get_size_multiplier(
        self, symbol: str, current_time: Optional[datetime] = None
    ) -> float:
        now = self._as_broker(current_time) if current_time is not None else self._bt.now()
        today = now.date()
        for ev in self._relevant_events(symbol):
            ev_day = self._as_broker(ev.datetime_utc).date()
            if ev_day == today and ev.impact == "high":
                self._logger.info(
                    "size reduced on high-impact day", symbol=symbol,
                    multiplier=self.size_reduction, event=ev.name,
                )
                return self.size_reduction
        return 1.0

    def get_next_event(self, symbol: str) -> Optional[NewsEvent]:
        now = self._bt.now()
        future = [
            e for e in self._relevant_events(symbol)
            if self._as_broker(e.datetime_utc) >= now
        ]
        if not future:
            return None
        return min(future, key=lambda e: e.datetime_utc)

    def get_events_today(self, symbol: str) -> List[NewsEvent]:
        now = self._bt.now()
        today = now.date()
        return [
            e for e in self._relevant_events(symbol)
            if self._as_broker(e.datetime_utc).date() == today
        ]

    def refresh(self, file_path: Optional[str] = None) -> bool:
        """Reload events from a JSON file. Returns True on success, False on any failure."""
        path = file_path or self._config.get("news", {}).get("static_calendar_path")
        if not path:
            self._logger.error("news refresh: no calendar path configured")
            return False
        events = load_events_from_json(path)
        if events:
            self._events = events
            self._logger.info("news calendar refreshed", count=len(events))
            return True
        self._logger.error("news refresh failed: empty/invalid calendar", path=path)
        return False
