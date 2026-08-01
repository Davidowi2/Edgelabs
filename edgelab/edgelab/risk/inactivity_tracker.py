"""Inactivity tracker for EdgeLab (Phase 3, Module 3).

Prevents the 30-day no-trade auto-closure by warning well ahead of the limit.
Independent of the drawdown check (different risk). Only the standard library.
"""

from __future__ import annotations

from datetime import datetime
from typing import Tuple

from edgelab.risk.account_state import AccountState
from edgelab.monitoring.logger import TradingLogger
from edgelab.time.broker_time import BrokerTime


class InactivityTracker:
    def __init__(self, account_state: AccountState, config: dict, logger: TradingLogger, broker_time: BrokerTime) -> None:
        self._state = account_state
        self._logger = logger
        self._bt = broker_time
        cfg = config or {}
        self.warning_days = int(cfg.get("warning_days", 21))
        self.danger_days = int(cfg.get("danger_days", 27))
        self.kill_days = int(cfg.get("kill_days", 29))
        self.inactivity_limit_days = int(cfg.get("inactivity_limit_days", 30))

    def check_inactivity(self, current_time: datetime) -> Tuple[str, int, str]:
        days_since = self._state.get_days_since_last_trade(current_time)
        if days_since >= 10 ** 8:  # never traded sentinel
            level = "critical"
            days_until_kill = self.inactivity_limit_days
            msg = f"inactivity: never traded, {days_until_kill}d until kill"
            self._logger.warning("inactivity risk", inact_level=level,
                                 days_since=None, days_until_kill=days_until_kill)
            return level, days_until_kill, msg

        days_until_kill = self.inactivity_limit_days - days_since

        if days_since < self.warning_days:
            level = "safe"
        elif days_since < self.danger_days:
            level = "warning"
        elif days_since < self.kill_days:
            level = "danger"
        else:
            level = "critical"

        msg = f"inactivity: {days_since}d since last trade, {days_until_kill}d until kill"
        if level in ("danger", "critical"):
            self._logger.warning("inactivity risk", inact_level=level, days_since=days_since,
                                 days_until_kill=days_until_kill)
        else:
            self._logger.info("inactivity check", inact_level=level, days_since=days_since,
                              days_until_kill=days_until_kill)
        return level, days_until_kill, msg

    def record_trade_activity(self, current_time: datetime) -> None:
        self._state.record_trade_closed(current_time)
