"""Account-level state tracker for EdgeLab (Phase 3, Module 1).

Tracks the data the per-trade risk engine does NOT: daily starting balance,
peak equity, total/daily drawdown, daily P&L, and trade-inactivity. Backtesting
and live trading use the same internal state, so risk decisions are identical.

Only the standard library is used.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from edgelab.monitoring.logger import TradingLogger
from edgelab.time.broker_time import BrokerTime


class AccountState:
    def __init__(self, initial_balance: float, broker_time: BrokerTime, logger: TradingLogger) -> None:
        self.initial_balance = float(initial_balance)
        self._bt = broker_time
        self._logger = logger

        self.current_equity = self.initial_balance
        self.peak_equity = self.initial_balance
        self.daily_starting_balance = self.initial_balance
        self.daily_starting_equity = self.initial_balance
        self.daily_high_equity = self.initial_balance

        self.last_trade_timestamp: Optional[datetime] = None
        self.last_update_timestamp: Optional[datetime] = None
        # broker-time date of the current daily window
        self._daily_date = None

    # ----- helpers -----
    def _broker_time(self, dt: datetime) -> datetime:
        return self._bt.to_broker_time(dt)

    def is_new_day(self, current_time: datetime) -> bool:
        b = self._broker_time(current_time)
        if self._daily_date is None:
            return True
        return b.date() != self._daily_date

    # ----- update -----
    def update(self, current_equity: float, current_time: datetime) -> None:
        self.current_equity = float(current_equity)
        bt_now = self._broker_time(current_time)

        if self.is_new_day(current_time):
            self._daily_date = bt_now.date()
            # Daily starting balance is the equity at the first tick of the day.
            # Daily starting equity is the higher of opening balance or equity.
            self.daily_starting_balance = self.current_equity
            self.daily_starting_equity = max(self.initial_balance, self.current_equity)
            self.daily_high_equity = self.current_equity

        if self.current_equity > self.peak_equity:
            self.peak_equity = self.current_equity
        if self.current_equity > self.daily_high_equity:
            self.daily_high_equity = self.current_equity

        self.last_update_timestamp = bt_now

    # ----- metrics -----
    def get_daily_pnl(self) -> float:
        return self.current_equity - self.daily_starting_equity

    def get_daily_pnl_pct(self) -> float:
        if self.daily_starting_equity == 0:
            return 0.0
        return self.get_daily_pnl() / self.daily_starting_equity

    def get_daily_drawdown(self) -> float:
        return max(0.0, self.daily_high_equity - self.current_equity)

    def get_daily_drawdown_pct(self) -> float:
        if self.daily_starting_equity == 0:
            return 0.0
        return max(0.0, self.get_daily_drawdown() / self.daily_starting_equity)

    def get_total_drawdown(self) -> float:
        return max(0.0, self.peak_equity - self.current_equity)

    def get_total_drawdown_pct(self) -> float:
        if self.peak_equity == 0:
            return 0.0
        return max(0.0, self.get_total_drawdown() / self.peak_equity)

    def get_days_since_last_trade(self, current_time: datetime) -> int:
        if self.last_trade_timestamp is None:
            return 10 ** 9  # effectively "never"
        bt_now = self._broker_time(current_time)
        bt_last = self._broker_time(self.last_trade_timestamp)
        return max(0, (bt_now.date() - bt_last.date()).days)

    def record_trade_closed(self, current_time: datetime) -> None:
        self.last_trade_timestamp = self._broker_time(current_time)
