"""Stop-loss watchdog for EdgeLab (Phase 4, Module 2).

Enforces the #1 cause of account blowups: a position with no stop loss, or a
stop loss too wide for the account. Never-had-an-SL is critical immediately
(decision #7). A position whose SL was REMOVED after having one runs a timed
warning -> critical escalation (generalizes the 30-second no-SL violation).
Only the standard library.
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, Optional

from edgelab.monitoring.logger import TradingLogger
from edgelab.time.broker_time import BrokerTime
from edgelab.trade.position import Position


class SLWatchdog:
    def __init__(self, config: dict, logger: TradingLogger, broker_time: BrokerTime) -> None:
        self._logger = logger
        self._bt = broker_time
        cfg = config or {}
        self.max_risk_pct = float(cfg.get("max_risk_pct", 0.015))
        self.sl_timer_seconds = float(cfg.get("sl_timer_seconds", 25))
        # position_id -> broker time when its SL was first seen as removed
        self._no_sl_start: Dict[str, datetime] = {}
        # position_id -> True once we have EVER seen it with an SL
        self._ever_had_sl: Dict[str, bool] = {}

    def _risk_amount(self, position: Position, account_balance: float, pip_value: float = 10.0) -> float:
        if position.risk_pips is None:
            return float("inf")  # no SL -> unbounded risk
        return position.risk_pips * pip_value * position.lot_size

    def check_position(self, position: Position, account_balance: float, current_time: datetime) -> Dict:
        bt_time = self._bt.to_broker_time(current_time)
        pid = position.position_id
        has_sl = position.current_sl is not None
        if has_sl:
            self._ever_had_sl[pid] = True
            self._no_sl_start.pop(pid, None)

        # (1) NO stop loss at all -> critical
        if position.current_sl is None:
            if not self._ever_had_sl.get(pid, False):
                # never had an SL: immediate critical
                self._logger.warning("SL watchdog CRITICAL: position never had SL",
                                     position_id=pid, symbol=position.symbol)
                return {"status": "critical", "action": "flag_critical",
                        "details": {"reason": "no_stop_loss_ever"}}
            # had an SL, then removed -> timed escalation
            if pid not in self._no_sl_start:
                self._no_sl_start[pid] = bt_time
            elapsed = (bt_time - self._no_sl_start[pid]).total_seconds()
            if elapsed >= self.sl_timer_seconds:
                self._logger.warning("SL watchdog CRITICAL: SL removed beyond timer",
                                     position_id=pid, elapsed_s=elapsed)
                return {"status": "critical", "action": "flag_critical",
                        "details": {"reason": "sl_removed_timeout", "elapsed_s": elapsed}}
            self._logger.info("SL watchdog WARNING: SL removed, timer running",
                              position_id=pid, elapsed_s=elapsed)
            return {"status": "warning", "action": "flag_critical",
                    "details": {"reason": "sl_removed_timer", "elapsed_s": elapsed}}

        # (2) SL too wide for account -> warning (tighten)
        risk = self._risk_amount(position, account_balance)
        limit = self.max_risk_pct * account_balance
        if risk > limit:
            self._logger.info("SL watchdog WARNING: SL too wide",
                              position_id=pid, risk=risk, limit=limit)
            return {"status": "warning", "action": "tighten_sl",
                    "details": {"risk": risk, "limit": limit}}

        # (3) within limits -> ok
        self._logger.info("SL watchdog OK", position_id=pid, risk=risk, limit=limit)
        return {"status": "ok", "action": "none",
                "details": {"risk": risk, "limit": limit}}
