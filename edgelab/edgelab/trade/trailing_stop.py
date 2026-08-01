"""Trailing stop + partial close for EdgeLab (Phase 4, Module 3).

Locks in profit as a position moves in our favor. The ONLY contract that matters:
a new SL can NEVER be further from price than the existing SL (tighten-only).
Partial close scales out at profit targets, guarded by a minimum lot. evaluate()
does NOT mutate the position — it returns a recommendation for the caller.
Only the standard library.
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from edgelab.monitoring.logger import TradingLogger
from edgelab.time.broker_time import BrokerTime
from edgelab.trade.position import Position, TradeDirection, TradeStatus


def _dist(sl: float, price: float, direction: TradeDirection) -> float:
    """Distance of SL from price, signed toward 'closer to price' = smaller positive.

    For LONG a good (tight) SL is BELOW price; for SHORT ABOVE price.
    Lower absolute value = tighter. Returns abs(sl - price).
    """
    return abs(sl - price)


class TrailingStopManager:
    def __init__(self, config: dict, logger: TradingLogger, broker_time: BrokerTime) -> None:
        self._logger = logger
        self._bt = broker_time
        cfg = config or {}
        self.breakeven_trigger_pips = float(cfg.get("breakeven_trigger_pips", 20))
        self.breakeven_buffer_pips = float(cfg.get("breakeven_buffer_pips", 5))
        self.trail_start_pips = float(cfg.get("trail_start_pips", 40))
        self.trail_step_pips = float(cfg.get("trail_step_pips", 20))
        self.partial_close_levels: List[Dict] = cfg.get(
            "partial_close_levels",
            [{"profit_pips": 40, "close_pct": 0.5}, {"profit_pips": 80, "close_pct": 0.5}],
        )
        self.min_lot_after_close = float(cfg.get("min_lot_after_close", 0.01))

    def _breakeven_sl(self, position: Position) -> float:
        if position.direction == TradeDirection.LONG:
            return position.entry_price + self.breakeven_buffer_pips / 10000.0
        return position.entry_price - self.breakeven_buffer_pips / 10000.0

    def _trail_sl(self, position: Position) -> float:
        if position.direction == TradeDirection.LONG:
            return position.current_price - self.trail_step_pips / 10000.0
        return position.current_price + self.trail_step_pips / 10000.0

    def _tighten(self, proposed: float, existing: Optional[float], position: Position) -> float:
        """Return the tighter of proposed/existing SL. Tighten-only contract."""
        if existing is None:
            return proposed
        # tighter = closer to current_price
        if _dist(proposed, position.current_price, position.direction) < \
           _dist(existing, position.current_price, position.direction):
            return proposed
        return existing

    def evaluate(self, position: Position, current_time: datetime) -> Dict:
        self._bt.to_broker_time(current_time)  # validate/normalize timezone
        profit = position.profit_pips  # signed pips (already direction-aware)
        proposed: Optional[float] = None
        action = "none"
        close_pct: Optional[float] = None
        reason = "within parameters"

        # (1) partial close levels (first match wins, status-aware)
        for lvl in self.partial_close_levels:
            if profit >= lvl["profit_pips"]:
                remaining = position.lot_size * (1.0 - lvl["close_pct"])
                if remaining >= self.min_lot_after_close:
                    action = "partial_close"
                    close_pct = lvl["close_pct"]
                    reason = f"partial close at {lvl['profit_pips']} pips"
                    self._logger.info("trailing: partial close", position_id=position.position_id,
                                      profit_pips=profit, close_pct=close_pct)
                    break
                reason = "partial close skipped: remaining lot below min"

        # (2) trail stop
        if action == "none" and profit >= self.trail_start_pips:
            proposed = self._trail_sl(position)
            action = "trail_stop"
            reason = f"trailing at {profit} pips"
            self._logger.info("trailing: trail stop", position_id=position.position_id,
                              new_sl=proposed)

        # (3) breakeven
        if action == "none" and profit >= self.breakeven_trigger_pips:
            be = self._breakeven_sl(position)
            # only if current SL is NOT already at/beyond the breakeven level
            if position.direction == TradeDirection.LONG:
                already = position.current_sl is not None and position.current_sl >= be
            else:
                already = position.current_sl is not None and position.current_sl <= be
            if not already:
                proposed = be
                action = "move_to_breakeven"
                reason = f"breakeven at {profit} pips"
                self._logger.info("trailing: move to breakeven", position_id=position.position_id,
                                  new_sl=proposed)

        if proposed is not None:
            final_sl = self._tighten(proposed, position.current_sl, position)
            if final_sl != proposed:
                self._logger.info("trailing: SL tightened-only (rejected looser)",
                                  position_id=position.position_id,
                                  proposed=proposed, kept=final_sl)
            return {"action": action, "new_sl": final_sl, "partial_close_pct": close_pct, "reason": reason}

        return {"action": action, "new_sl": None, "partial_close_pct": close_pct, "reason": reason}
