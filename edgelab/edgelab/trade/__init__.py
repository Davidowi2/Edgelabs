"""EdgeLab trade-management package (Phase 4, Module 4).

Unified TradeManager: given a position + market data, returns recommended
management actions (SL watchdog + trailing stop). evaluate_all() does NOT mutate
the position — the caller (live broker integration) decides whether to apply.
Only the standard library.
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, Optional

from edgelab.monitoring.logger import TradingLogger
from edgelab.time.broker_time import BrokerTime
from edgelab.trade.position import Position, TradeDirection, TradeStatus
from edgelab.trade.sl_watchdog import SLWatchdog
from edgelab.trade.trailing_stop import TrailingStopManager

__all__ = [
    "Position",
    "TradeDirection",
    "TradeStatus",
    "SLWatchdog",
    "TrailingStopManager",
    "TradeManager",
]


class TradeManager:
    def __init__(self, config: dict, logger: TradingLogger, broker_time: BrokerTime) -> None:
        self._logger = logger
        self._bt = broker_time
        cfg = config or {}
        self._sl = SLWatchdog(cfg.get("sl_watchdog", {}), logger, broker_time)
        self._ts = TrailingStopManager(cfg.get("trailing_stop", {}), logger, broker_time)

    def evaluate_all(self, position: Position, account_balance: float,
                    current_price: float, current_time: datetime) -> Dict:
        # Step 1: update price (this is the manager's only state touch)
        position.update_price(current_price)
        self._logger.info("trade manager evaluate", position_id=position.position_id,
                          current_price=current_price)

        # Step 2 + 3
        sl_result = self._sl.check_position(position, account_balance, current_time)
        ts_result = self._ts.evaluate(position, current_time)

        action = self._determine_priority_action(sl_result, ts_result)
        self._logger.info("trade manager decision", position_id=position.position_id,
                          action=action)

        return {
            "position_id": position.position_id,
            "current_price": current_price,
            "unrealized_pnl": position.calculate_unrealized_pnl(),
            "sl_watchdog": sl_result,
            "trailing_stop": ts_result,
            "recommended_action": action,
            "timestamp": current_time,
        }

    @staticmethod
    def _determine_priority_action(sl_result: Dict, ts_result: Dict) -> str:
        # 1) no SL = highest priority risk -> close
        if sl_result.get("status") == "critical":
            return "close_position"
        # 2) SL too wide -> tighten (overrides trailing)
        if sl_result.get("status") == "warning":
            return "tighten_sl"
        # 3) trailing recommendation
        ts_action = ts_result.get("action")
        if ts_action in ("partial_close", "trail_stop", "move_to_breakeven"):
            return ts_action
        # 4) nothing
        return "none"
