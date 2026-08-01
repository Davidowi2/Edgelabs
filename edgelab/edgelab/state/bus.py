"""Shared state bus for EdgeLab."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional


@dataclass
class Position:
    symbol: str
    direction: str
    entry_price: float
    stop_loss: Optional[float]
    take_profit: Optional[float]
    lot_size: float
    entry_time: datetime
    trade_id: str
    pnl: Optional[float] = field(default=None, repr=False)
    exit_price: Optional[float] = field(default=None, repr=False)
    exit_time: Optional[datetime] = field(default=None, repr=False)


class StateBus:
    """Mutable shared state. Strategy, risk, and backtester read/write here."""

    def __init__(self, initial_equity: float) -> None:
        self.equity: float = initial_equity
        self.initial_equity: float = initial_equity
        self.open_positions: List[Position] = []
        self.closed_trades: List[Position] = []
        self.current_pnl: float = 0.0
        self.peak_equity: float = initial_equity
        self.daily_pnl: float = 0.0
        self.daily_start_equity: float = initial_equity
        self.today: Optional[str] = None
        self.is_session_trading_allowed: bool = True

    def reset_daily(self, now: datetime) -> None:
        date_str = now.date().isoformat()
        if self.today == date_str:
            return
        self.daily_pnl = 0.0
        self.daily_start_equity = self.equity
        self.today = date_str

    def add_position(self, position: Position) -> None:
        self.open_positions.append(position)

    def close_position(self, trade_id: str, exit_price: float, exit_time: datetime) -> Optional[Position]:
        for index, position in enumerate(self.open_positions):
            if position.trade_id == trade_id:
                pnl = self._calculate_pnl(position, exit_price)
                position.pnl = pnl
                position.exit_price = exit_price
                position.exit_time = exit_time
                self.current_pnl += pnl
                self.equity += pnl
                self.daily_pnl += pnl
                if self.equity > self.peak_equity:
                    self.peak_equity = self.equity
                self.closed_trades.append(position)
                self.open_positions.pop(index)
                return position
        return None

    def _calculate_pnl(self, position: Position, exit_price: float) -> float:
        multiplier = 1 if position.direction.upper() == "LONG" else -1
        return multiplier * (exit_price - position.entry_price) * position.lot_size
