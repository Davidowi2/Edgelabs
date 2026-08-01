"""Position data structure for EdgeLab (Phase 4, Module 1).

A Position is a plain data container the trade manager reads/writes. In live
trading it is populated from broker data; in backtesting from the backtester.
Phase 4 exercises it directly with mock data. Only the standard library.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import uuid4


class TradeDirection(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"


class TradeStatus(str, Enum):
    OPEN = "OPEN"
    PARTIAL_CLOSED = "PARTIAL_CLOSED"
    CLOSED = "CLOSED"


@dataclass
class Position:
    position_id: str = field(default_factory=lambda: str(uuid4()))
    symbol: str = ""
    direction: TradeDirection = TradeDirection.LONG
    entry_price: float = 0.0
    current_sl: Optional[float] = None
    current_tp: Optional[float] = None
    lot_size: float = 0.0
    entry_time: Optional[datetime] = None
    status: TradeStatus = TradeStatus.OPEN
    magic_number: str = ""
    current_price: float = 0.0

    # ----- derived (computed, not stored) -----
    @property
    def risk_pips(self) -> Optional[float]:
        if self.current_sl is None:
            return None
        return round(abs(self.entry_price - self.current_sl) * 10000.0, 4)

    @property
    def reward_pips(self) -> Optional[float]:
        if self.current_tp is None:
            return None
        return round(abs(self.current_tp - self.entry_price) * 10000.0, 4)

    @property
    def rr_ratio(self) -> Optional[float]:
        if self.risk_pips in (None, 0.0) or self.reward_pips is None:
            return None
        return self.reward_pips / self.risk_pips

    @property
    def is_profitable(self) -> bool:
        if self.direction == TradeDirection.LONG:
            return self.current_price > self.entry_price
        return self.current_price < self.entry_price

    @property
    def profit_pips(self) -> float:
        # signed PIP COUNT (positive = profit). 1 pip = 0.0001 price.
        if self.direction == TradeDirection.LONG:
            return round((self.current_price - self.entry_price) * 10000.0, 4)
        return round((self.entry_price - self.current_price) * 10000.0, 4)

    # ----- methods -----
    def update_price(self, new_price: float) -> None:
        self.current_price = float(new_price)

    def calculate_unrealized_pnl(self, pip_value: float = 10.0) -> float:
        """P&L in account currency. Phase 4 placeholder pip_value = 10/lot.

        profit_pips is a pip COUNT; P&L = profit_pips * lot_size * pip_value.
        """
        return self.profit_pips * self.lot_size * pip_value
