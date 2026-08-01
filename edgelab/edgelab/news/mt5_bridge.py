"""MT5 economic-calendar bridge for EdgeLab (Phase 2, Module 4).

This is a STUB. The live system runs inside the TradeLocker/MT5 terminal via
Python integration; from standalone Python we cannot reach the MQL5 calendar,
so the bridge returns an empty list and the static config remains the source
of truth. The static config is always the fallback (fail-open design).

Only the standard library is used here; no MT5 package is imported at runtime.
"""

from __future__ import annotations

import logging
from typing import List

from edgelab.news.static_config import NewsEvent

logger = logging.getLogger("edgelab.news.mt5_bridge")

# TODO(MQL5-integration): When running inside the MT5 Python environment, replace
# ``fetch_events_from_mt5`` with a call to the terminal's calendar API:
#   1. import MetaTrader5 as mt5
#   2. mt5.initialize() and confirm mt5.terminal_info().connected
#   3. use mt5.events_calendar / CalendarEventByCountry + CalendarValueHistoryByEvent
#      to pull events for the requested currencies over ``days_ahead``.
#   4. convert each MQL5 CalendarEvent into a NewsEvent (UTC datetime, impact
#      mapped high/medium/low), and return the list.
# Until then this always returns [] so the rest of the system keeps working on
# the static calendar alone.


def is_mt5_environment() -> bool:
    """True only if the MQL5 Python package is importable AND connected.

    Never raises on import failure: a missing package simply means we are in
    standalone mode.
    """
    try:
        import importlib

        importlib.import_module("MetaTrader5")
    except Exception:  # noqa: BLE001 - any failure => not MT5 mode
        return False
    # Package present but terminal not connected => not usable.
    try:
        import MetaTrader5 as mt5  # type: ignore

        info = mt5.terminal_info()  # type: ignore[attr-defined]
        return bool(info and getattr(info, "connected", False))
    except Exception:  # noqa: BLE001
        return False


def fetch_events_from_mt5(currencies: List[str], days_ahead: int = 7) -> List[NewsEvent]:
    """Return live MT5 calendar events via the MQL5 terminal calendar API.

    STUB: in standalone Python there is no terminal to query, so we return an
    empty list and let the caller fall back to the static config. When deployed
    inside MT5, implement using MQL5 CalendarEventByCountry /
    CalendarValueHistoryByEvent as described in this module's docstring.
    """
    logger.info("MT5 bridge not active in standalone Python mode", currencies=currencies)
    return []
