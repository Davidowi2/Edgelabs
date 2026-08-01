"""Strategy 1: Modernized Turtle (trend following).

Source: Richard Dennis's original Turtle rules + Curtis Faith's modifications
("Way of the Turtle") + Garner "Tuning up the Turtle" research.

Implemented exactly as specified in the strategy brief:

  - N (ATR): 20-period EMA-smoothed ATR.
  - Entry long:  close > 55-period high AND close > 200 EMA (trend filter).
  - Entry short: close < 55-period low  AND close < 200 EMA.
  - Stop loss: 2 x N from entry.
  - Exit long:  close < 20-period low.   Exit short: close > 20-period high.
  - Position sizing: 1% of equity per trade (handled by RiskEngine via stop).
  - Spread: 0.8 pip worse fill at entry (RiskEngine spread).
  - Max positions: 1 (no pyramiding).

The strategy is stateful: it remembers whether it is in a position and the
Turtle exit level so the backtest runner can query exits via `exit_signal()`.
"""

from __future__ import annotations

from typing import Optional

import pandas as pd

from edgelab.strategy.indicators import atr, ema, rolling_high, rolling_low


class TurtleStrategy:
    """Modernized Turtle trend-following strategy (1-position, 2N stop)."""

    def __init__(self) -> None:
        self.in_position: bool = False
        self.direction: Optional[str] = None
        self.turtle_exit: Optional[float] = None  # price level for exit
        self.entry_price: Optional[float] = None
        self._ind_df = None
        self._ind_cache = None

    def _indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        # Cache per DataFrame identity so the backtester's per-bar calls reuse one
        # precomputed frame instead of recomputing ATR/EMA every bar.
        if self._ind_df is df and self._ind_cache is not None:
            return self._ind_cache
        out = pd.DataFrame(index=df.index)
        out["close"] = df["close"].astype(float)
        out["atr20"] = atr(df, 20, ema=True)
        # Entry breakouts compare to the PRIOR 55-bar extreme (Donchian): exclude current bar.
        out["hh55"] = df["high"].astype(float).shift(1).rolling(55, min_periods=55).max()
        out["ll55"] = df["low"].astype(float).shift(1).rolling(55, min_periods=55).min()
        out["ema200"] = ema(df["close"].astype(float), 200)
        self._ind_df = df
        self._ind_cache = out
        return out

    def signal(self, df: pd.DataFrame, i: int) -> Optional[dict]:
        """Entry signal for bar i (None if flat, a position exists, or no setup)."""
        if self.in_position:
            return None
        ind = self._indicators(df)
        if i < 200:  # need 200 bars for EMA200 warmup
            return None
        r = ind.iloc[i]
        if pd.isna(r["atr20"]) or pd.isna(r["hh55"]) or pd.isna(r["ema200"]):
            return None
        close = float(r["close"])
        # Long setup
        if close > float(r["hh55"]) and close > float(r["ema200"]):
            n = float(r["atr20"])
            stop = close - 2 * n
            return {
                "direction": "LONG",
                "entry_price": close,
                "stop_loss": stop,
                "take_profit": None,
                "strategy_id": "turtle",
                "atr": n,
            }
        # Short setup
        if close < float(r["ll55"]) and close < float(r["ema200"]):
            n = float(r["atr20"])
            stop = close + 2 * n
            return {
                "direction": "SHORT",
                "entry_price": close,
                "stop_loss": stop,
                "take_profit": None,
                "strategy_id": "turtle",
                "atr": n,
            }
        return None

    def on_fill(self, direction: str, entry_price: float, i: int, df: pd.DataFrame) -> None:
        """Called by the runner when an entry is accepted."""
        self.in_position = True
        self.direction = direction
        self.entry_price = entry_price

    def exit_signal(self, df: pd.DataFrame, i: int) -> Optional[str]:
        """Return exit reason ('turtle_exit') if the close breaches the rolling
        20-period low (long) / high (short) of the prior 20 bars."""
        if not self.in_position or self.direction is None:
            return None
        close = float(df["close"].iloc[i])
        if self.direction == "LONG":
            level = float(df["low"].astype(float).shift(1).rolling(20, min_periods=20).min().iloc[i])
            if close < level:
                return "turtle_exit"
        else:
            level = float(df["high"].astype(float).shift(1).rolling(20, min_periods=20).max().iloc[i])
            if close > level:
                return "turtle_exit"
        return None

    def on_exit(self) -> None:
        self.in_position = False
        self.direction = None
        self.turtle_exit = None
        self.entry_price = None
