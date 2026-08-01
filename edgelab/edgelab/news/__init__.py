"""EdgeLab news-filter package (Phase 2, Module 5).

Single import point + factory. ``create_news_filter`` is fail-open: if the
static calendar is missing or unreadable it returns a no-op filter (trades
without news filtering) and logs a CRITICAL warning, never raising.

Only the standard library is used.
"""

from __future__ import annotations

from typing import Optional

from edgelab.news.currency_map import get_currencies_for_symbol
from edgelab.news.filter import NewsFilter
from edgelab.news.mt5_bridge import fetch_events_from_mt5, is_mt5_environment
from edgelab.news.static_config import NewsEvent, load_events_from_json
from edgelab.monitoring.logger import TradingLogger
from edgelab.time.broker_time import BrokerTime

__all__ = [
    "NewsFilter",
    "NewsEvent",
    "create_news_filter",
    "get_news_filter_status",
    "fetch_events_from_mt5",
    "is_mt5_environment",
    "load_events_from_json",
]


def create_news_filter(config: dict, logger: TradingLogger, broker_time: BrokerTime) -> NewsFilter:
    """Build a NewsFilter from config. Never raises.

    Steps:
      1. Load static events from config["news"]["static_calendar_path"].
      2. Optionally enrich with MT5 calendar (if running in MT5 env).
      3. Return a NewsFilter. On any failure, return a pass-through filter and
         log CRITICAL so the operator knows filtering is disabled.
    """
    cfg = config or {}
    events: list[NewsEvent] = []
    try:
        calendar_path = (cfg.get("news") or {}).get("static_calendar_path")
        if calendar_path:
            events = load_events_from_json(calendar_path)
        # Optional live enrichment (standalone => empty, harmless).
        if is_mt5_environment():
            try:
                live = fetch_events_from_mt5([])
                events = events + live
            except Exception:  # noqa: BLE001 - live data is best-effort
                pass
    except Exception as exc:  # noqa: BLE001 - never let construction crash startup
        logger.critical("news filter construction failed", error=repr(exc))
        return NewsFilter(cfg, [], logger, broker_time)

    if not events:
        logger.critical(
            "news calendar empty/unavailable: trading WITHOUT news filtering (fail-open)",
            path=str(calendar_path),
        )
    else:
        logger.info("news filter loaded", event_count=len(events))
    return NewsFilter(cfg, events, logger, broker_time)


def get_news_filter_status(filter_obj: NewsFilter, symbol: str) -> dict:
    """Convenience status dict the rest of the system can call at any entry point."""
    allowed, reason = filter_obj.is_trading_allowed(symbol)
    nxt = filter_obj.get_next_event(symbol)
    return {
        "trading_allowed": allowed,
        "reason": reason,
        "size_multiplier": filter_obj.get_size_multiplier(symbol),
        "next_event": nxt.id if nxt else None,
    }
