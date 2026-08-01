"""Strategy 3: Session Volatility Expansion (time-of-day breakout).

Source: common session-trading patterns + Isar's session windows.

Implemented as specified:

  - Timeframe H1. Session windows in NY time:
        London: 03:00-06:00, NY: 08:00-11:00.
  - At session open track first 2 H1 bars -> session range (high/low).
  - Entry long:  break above session range high AND prior 4H candle bullish.
  - Entry short: break below session range low  AND prior 4H candle bearish.
  - Stop loss: opposite side of session range.
  - Take profit: 1.5 x range size from entry.
  - Time stop: exit at market if open > 6 H1 bars after entry.
  - Risk: 0.5% per trade (RiskEngine). Spread 0.8 pip (RiskEngine).
  - Max positions: 1. Only one trade per session.
"""

from __future__ import annotations

from typing import Optional

import pandas as pd

from edgelab.strategy.indicators import in_window

LONDON = (3, 0, 6, 0)
NY = (8, 0, 11, 0)
SESSIONS = [LONDON, NY]


class SessionExpansionStrategy:
    """Session-range breakout; one trade per session; time stop after 6 bars."""

    def __init__(self) -> None:
        self.in_position: bool = False
        self.direction: Optional[str] = None
        self.entry_bar_index: Optional[int] = None
        self.entry_price: Optional[float] = None
        self.stop_loss: Optional[float] = None
        self.take_profit: Optional[float] = None
        self.active_session_key: Optional[tuple] = None
        self.session_range_high: Optional[float] = None
        self.session_range_low: Optional[float] = None
        self.session_first_bar_idx: Optional[int] = None
        self.session_bars_seen: int = 0
        self.traded_sessions: set = set()
        self._pending_stop: Optional[float] = None
        self._pending_tp: Optional[float] = None

    def _session_of(self, ts) -> Optional[tuple]:
        for w in SESSIONS:
            if in_window(ts, w):
                return w
        return None

    def _prior_4h_bullish(self, df: pd.DataFrame, i: int) -> Optional[bool]:
        base = i - 4
        if base < 0:
            return None
        o = float(df["open"].iloc[base])
        c = float(df["close"].iloc[i - 1]) if i - 1 >= 0 else float(df["close"].iloc[i])
        return c > o

    def signal(self, df: pd.DataFrame, i: int) -> Optional[dict]:
        ts = df.index[i]
        sess = self._session_of(ts)
        if sess is None:
            return None
        # Only one trade per session OCCURRENCE (reset when a new session begins).
        if self.active_session_key != sess:
            # new session occurrence -> clear the per-session trade lock
            self.traded_sessions = set()
            self.active_session_key = sess
            self.session_first_bar_idx = i
            self.session_bars_seen = 0
            self.session_range_high = None
            self.session_range_low = None
        if sess in self.traded_sessions:
            return None
        if self.in_position:
            # Manage existing position (time stop + exits handled in exit_signal/runner)
            return None

        if self.session_bars_seen == 0 or self.session_bars_seen == 1:
            high = float(df["high"].iloc[i])
            low = float(df["low"].iloc[i])
            if self.session_range_high is None:
                self.session_range_high = high
                self.session_range_low = low
            else:
                self.session_range_high = max(self.session_range_high, high)
                self.session_range_low = min(self.session_range_low, low)
            self.session_bars_seen += 1
            return None

        # After 2 bars, session range is defined at the close of bar 2 (this bar already counted).
        if self.session_range_high is None or self.session_range_low is None:
            return None
        rng_high = self.session_range_high
        rng_low = self.session_range_low
        range_size = rng_high - rng_low
        if range_size <= 0:
            return None
        close = float(df["close"].iloc[i])
        prior_bull = self._prior_4h_bullish(df, i)
        if prior_bull is None:
            return None

        if close > rng_high and prior_bull:
            self.traded_sessions.add(sess)
            self._pending_stop = rng_low
            self._pending_tp = close + 1.5 * range_size
            return {
                "direction": "LONG",
                "entry_price": close,
                "stop_loss": rng_low,
                "take_profit": close + 1.5 * range_size,
                "strategy_id": "session_expansion",
                "range_size": range_size,
            }
        if close < rng_low and not prior_bull:
            self.traded_sessions.add(sess)
            self._pending_stop = rng_high
            self._pending_tp = close - 1.5 * range_size
            return {
                "direction": "SHORT",
                "entry_price": close,
                "stop_loss": rng_high,
                "take_profit": close - 1.5 * range_size,
                "strategy_id": "session_expansion",
                "range_size": range_size,
            }
        return None

    def on_fill(self, direction: str, entry_price: float, i: int, df: pd.DataFrame) -> None:
        self.in_position = True
        self.direction = direction
        self.entry_bar_index = i
        self.entry_price = entry_price
        # carry the latest proposed stop/take so exit_signal can evaluate them
        self.stop_loss = getattr(self, "_pending_stop", self.stop_loss)
        self.take_profit = getattr(self, "_pending_tp", self.take_profit)

    def exit_signal(self, df: pd.DataFrame, i: int) -> Optional[str]:
        if not self.in_position:
            return None
        # Time stop: flat if > 6 H1 bars after entry
        if self.entry_bar_index is not None and (i - self.entry_bar_index) > 6:
            return "time_stop"
        close = float(df["close"].iloc[i])
        if self.direction == "LONG" and self.take_profit is not None and close >= self.take_profit:
            return "take_profit"
        if self.direction == "SHORT" and self.take_profit is not None and close <= self.take_profit:
            return "take_profit"
        if self.direction == "LONG" and self.stop_loss is not None and close <= self.stop_loss:
            return "stop_loss"
        if self.direction == "SHORT" and self.stop_loss is not None and close >= self.stop_loss:
            return "stop_loss"
        return None

    def on_exit(self) -> None:
        self.in_position = False
        self.direction = None
        self.entry_bar_index = None
        self.entry_price = None
        self.stop_loss = None
        self.take_profit = None
