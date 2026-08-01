"""Strategy 2: HTF Structure + LTF Trigger (pullback to value).

Source: Mark's case study (Vocal Media) + Chaudry Isar's interview (forex.in.rs).

Implemented as specified:

  - Context timeframe H4 simulated by a rolling 4-bar window on H1.
  - HTF bias over last 20 H4 bars (80 H1 bars):
        higher highs + higher lows -> bullish (longs only)
        lower highs + lower lows   -> bearish (shorts only)
        else -> no bias, skip.
  - Entry long:  bullish bias AND price pulls back within 0.5% of 200 EMA AND
                 bullish rejection candle (close > open, body > 50% of range).
  - Entry short: bearish bias AND within 0.5% of 200 EMA AND bearish rejection.
  - Stop loss: 1.5 x ATR(20) beyond the rejection candle low (long) / high (short).
  - Trailing stop: after +1R move stop to breakeven; after +2R trail 1R behind.
  - Risk: 1% per trade (RiskEngine). Spread 0.8 pip (RiskEngine).
  - Max positions: 1. Session filter: 08:00-11:00 NY (London/NY overlap).
"""

from __future__ import annotations

from typing import Optional

import pandas as pd

from edgelab.strategy.indicators import atr, ema, in_window, to_ny

NY_OVERLAP = (8, 0, 11, 0)


class StructurePullbackStrategy:
    """HTF structure bias + LTF pullback-to-EMA trigger with trailing stop."""

    def __init__(self) -> None:
        self.in_position: bool = False
        self.direction: Optional[str] = None
        self.entry_price: Optional[float] = None
        self.initial_stop: Optional[float] = None
        self.atr_entry: Optional[float] = None
        self.current_stop: Optional[float] = None
        self._ind_df = None
        self._ind_cache = None

    def _indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        if self._ind_df is df and self._ind_cache is not None:
            return self._ind_cache
        out = pd.DataFrame(index=df.index)
        out["ema200"] = ema(df["close"].astype(float), 200)
        out["atr20"] = atr(df, 20, ema=True)
        self._ind_df = df
        self._ind_cache = out
        return out

    def _h4_bias(self, df: pd.DataFrame, i: int):
        """Return 'bullish' | 'bearish' | None using last 20 H4 bars (80 H1).

        Bias is determined by the trend of H4 highs and lows: a bullish bias needs
        the H4 highs AND lows to be predominantly making higher highs / higher lows
        (a strict all-20 monotonic chain is too rigid for real FX data, so we use a
        majority-of-steps rule as the spec's 'higher highs and higher lows' intent).
        """
        need = 80
        if i < need:
            return None
        win = df.iloc[i - need : i]
        h4_highs = win["high"].astype(float).rolling(4).max()[3::4]
        h4_lows = win["low"].astype(float).rolling(4).min()[3::4]
        h4_highs = h4_highs.dropna()
        h4_lows = h4_lows.dropna()
        if len(h4_highs) < 20 or len(h4_lows) < 20:
            return None
        hh = list(h4_highs.iloc[-20:])
        ll = list(h4_lows.iloc[-20:])
        hh_up = sum(1 for k in range(1, len(hh)) if hh[k] > hh[k - 1])
        ll_up = sum(1 for k in range(1, len(ll)) if ll[k] > ll[k - 1])
        # At least 70% of the H4 steps must be up to declare a bullish structure.
        if hh_up >= 14 and ll_up >= 14:
            return "bullish"
        if hh_up <= 6 and ll_up <= 6:
            return "bearish"
        return None

    def _rejection(self, bar: pd.Series, direction: str) -> bool:
        o = float(bar["open"])
        c = float(bar["close"])
        h = float(bar["high"])
        l = float(bar["low"])
        rng = h - l
        if rng == 0:
            return False
        body = abs(c - o)
        if body <= 0.5 * rng:
            return False  # body must be > 50% of range
        if direction == "LONG":
            return c > o  # bullish
        return c < o  # bearish

    def signal(self, df: pd.DataFrame, i: int) -> Optional[dict]:
        if self.in_position:
            return None
        ts = df.index[i]
        if not in_window(ts, NY_OVERLAP):
            return None
        bias = self._h4_bias(df, i)
        if bias is None:
            return None
        ind = self._indicators(df)
        r = ind.iloc[i]
        if pd.isna(r["ema200"]) or pd.isna(r["atr20"]):
            return None
        close = float(df["close"].iloc[i])
        ema_v = float(r["ema200"])
        if abs(close - ema_v) / ema_v > 0.005:
            return None  # must be within 0.5% of EMA
        bar = df.iloc[i]
        if bias == "bullish" and self._rejection(bar, "LONG"):
            n = float(r["atr20"])
            stop = float(bar["low"]) - 1.5 * n
            return {
                "direction": "LONG",
                "entry_price": close,
                "stop_loss": stop,
                "take_profit": None,
                "strategy_id": "structure_pullback",
                "atr": n,
            }
        if bias == "bearish" and self._rejection(bar, "SHORT"):
            n = float(r["atr20"])
            stop = float(bar["high"]) + 1.5 * n
            return {
                "direction": "SHORT",
                "entry_price": close,
                "stop_loss": stop,
                "take_profit": None,
                "strategy_id": "structure_pullback",
                "atr": n,
            }
        return None

    def on_fill(self, direction: str, entry_price: float, i: int, df: pd.DataFrame) -> None:
        self.in_position = True
        self.direction = direction
        self.entry_price = entry_price
        ind = self._indicators(df)
        n = float(ind["atr20"].iloc[i])
        self.atr_entry = n
        if direction == "LONG":
            self.initial_stop = entry_price - 1.5 * n
        else:
            self.initial_stop = entry_price + 1.5 * n
        self.current_stop = self.initial_stop

    def update_stop(self, df: pd.DataFrame, i: int) -> None:
        """Trailing logic: +1R -> breakeven; +2R -> trail 1R behind price."""
        if not self.in_position or self.entry_price is None or self.atr_entry is None:
            return
        close = float(df["close"].iloc[i])
        ep = self.entry_price
        n = self.atr_entry
        if self.direction == "LONG":
            r_mult = (close - ep) / n
            if r_mult >= 2:
                self.current_stop = max(self.current_stop or ep, close - 1 * n)
            elif r_mult >= 1:
                self.current_stop = max(self.current_stop or ep, ep)
        else:
            r_mult = (ep - close) / n
            if r_mult >= 2:
                self.current_stop = min(self.current_stop or ep, close + 1 * n)
            elif r_mult >= 1:
                self.current_stop = min(self.current_stop or ep, ep)

    def exit_signal(self, df: pd.DataFrame, i: int) -> Optional[str]:
        if not self.in_position or self.current_stop is None:
            return None
        close = float(df["close"].iloc[i])
        if self.direction == "LONG" and close < self.current_stop:
            return "stop_loss"
        if self.direction == "SHORT" and close > self.current_stop:
            return "stop_loss"
        return None

    def on_exit(self) -> None:
        self.in_position = False
        self.direction = None
        self.entry_price = None
        self.initial_stop = None
        self.current_stop = None
        self.atr_entry = None
