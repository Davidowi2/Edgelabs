"""Phase H fallback: Combination strategy (meta-strategy over the three failed ones).

Combines, as gates, the three documented approaches' key components:
  1. Trend filter from Strategy 1: 200 EMA direction (price > EMA -> long only;
     price < EMA -> short only).
  2. Session filter from Strategy 3: trade only during the London/NY overlap
     session (08:00-11:00 NY).
  3. Structure filter from Strategy 2: HTF (H4) bias must be bullish (longs) or
     bearish (shorts); otherwise skip.
Entry: simplest pullback logic -- price within 0.5% of 200 EMA plus a rejection
candle (reusing Strategy 2's trigger). Stop: 2 x ATR(20). Exit: 20-period
opposite breakout (reusing Turtle's exit). Risk: 0.5% per trade.

This file is always present; only RUN when Phase G shows all three failed.
"""

from __future__ import annotations

from typing import Optional

import pandas as pd

from edgelab.strategy.indicators import atr, ema, in_window, to_ny
from edgelab.strategy.structure_pullback import StructurePullbackStrategy
from edgelab.strategy.turtle import TurtleStrategy

OVERLAP = (8, 0, 11, 0)


class CombinationStrategy:
    """Three-filter meta-strategy: EMA trend + session + HTF structure."""

    def __init__(self) -> None:
        self._struct = StructurePullbackStrategy()
        self._turtle = TurtleStrategy()
        self.in_position: bool = False
        self.direction: Optional[str] = None
        self.entry_price: Optional[float] = None
        self.turtle_exit: Optional[float] = None
        self._ind_df = None
        self._ind_cache = None

    def _indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        if self._ind_df is df and self._ind_cache is not None:
            return self._ind_cache
        out = pd.DataFrame(index=df.index)
        out["ema200"] = ema(df["close"].astype(float), 200)
        out["atr20"] = atr(df, 20, ema=True)
        out["exit_long_level"] = df["low"].astype(float).shift(1).rolling(20, min_periods=20).min()
        out["exit_short_level"] = df["high"].astype(float).shift(1).rolling(20, min_periods=20).max()
        self._ind_df = df
        self._ind_cache = out
        return out

    def _ema_bias(self, df: pd.DataFrame, i: int) -> Optional[str]:
        ind = self._indicators(df)
        r = ind.iloc[i]
        if pd.isna(r["ema200"]):
            return None
        close = float(df["close"].iloc[i])
        if close > float(r["ema200"]):
            return "bullish"
        if close < float(r["ema200"]):
            return "bearish"
        return None

    def signal(self, df: pd.DataFrame, i: int) -> Optional[dict]:
        if self.in_position:
            return None
        ts = df.index[i]
        if not in_window(ts, OVERLAP):
            return None
        ema_bias = self._ema_bias(df, i)
        if ema_bias is None:
            return None
        htf_bias = self._struct._h4_bias(df, i)
        if htf_bias is None or htf_bias != ema_bias:
            return None  # filters must align
        # Reuse Strategy 2 trigger (rejection candle + within 0.5% of EMA)
        sig = self._struct.signal(df, i)
        if sig is None:
            return None
        # Re-price stop to 2 x ATR(20) per combination spec
        ind = self._indicators(df)
        n = float(ind["atr20"].iloc[i])
        close = float(df["close"].iloc[i])
        if sig["direction"] == "LONG":
            stop = close - 2 * n
        else:
            stop = close + 2 * n
        return {
            "direction": sig["direction"],
            "entry_price": close,
            "stop_loss": stop,
            "take_profit": None,
            "strategy_id": "combination",
            "atr": n,
        }

    def on_fill(self, direction: str, entry_price: float, i: int, df: pd.DataFrame) -> None:
        self.in_position = True
        self.direction = direction
        self.entry_price = entry_price
        # Exit level is not fixed; exit_signal recomputes the rolling 20-period
        # opposite breakout each bar.

    def exit_signal(self, df: pd.DataFrame, i: int) -> Optional[str]:
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
        self.entry_price = None
        self.turtle_exit = None
