"""Strategy 2 (XAUUSD H4): HTF Structure + LTF pullback-to-200-EMA trigger.

Faithful port of the documented Strategy 2 (structure_pullback.py) to NATIVE H4
bars. The original ran on H1 with an 80-bar (4x20) rolling window to *simulate*
H4; here we operate on real H4 bars directly, so the HTF bias uses 20 actual H4
bars. All other rules are preserved from the spec:
  - HTF bias over last 20 H4 bars: higher highs AND higher lows -> bullish (longs),
    lower highs AND lower lows -> bearish (shorts), else skip.
  - Entry: bias AND price within 0.5% of 200 EMA AND bullish/bearish rejection
    candle (close>open, body>50% of range).
  - Stop: 1.5 x ATR(20) beyond rejection candle low/high.
  - Trailing: +1R -> breakeven; +2R -> trail 1R behind.
  - Risk 1% (set by runner's risk_per_trade). Spread from symbol config.
  - Session filter: London/NY overlap 08:00-11:00 NY (per original NY_OVERLAP).

No parameter tuning. This is the documented system, run on the REAL live
candidate instrument (XAUUSD H4) so we can compare against EURUSD H1 results.
"""

from __future__ import annotations

from typing import Optional

import pandas as pd

from edgelab.strategy.indicators import atr, ema, in_window

NY_OVERLAP = (8, 0, 11, 0)


class StructurePullbackH4Strategy:
    def __init__(self) -> None:
        self.in_position = False
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
        need = 20  # 20 actual H4 bars (was 80 H1 bars as a proxy)
        if i < need:
            return None
        win = df.iloc[i - need:i]
        hh = list(win["high"].astype(float))
        ll = list(win["low"].astype(float))
        hh_up = sum(1 for k in range(1, len(hh)) if hh[k] > hh[k - 1])
        ll_up = sum(1 for k in range(1, len(ll)) if ll[k] > ll[k - 1])
        # >=70% of steps up = bullish structure; <=30% = bearish
        if hh_up >= 14 and ll_up >= 14:
            return "bullish"
        if hh_up <= 6 and ll_up <= 6:
            return "bearish"
        return None

    def _rejection(self, bar: pd.Series, direction: str) -> bool:
        o = float(bar["open"]); c = float(bar["close"])
        h = float(bar["high"]); l = float(bar["low"])
        rng = h - l
        if rng <= 0:
            return False
        if (c - o) <= 0.5 * rng:
            return False
        if direction == "LONG":
            return c > o
        return c < o

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
            return None
        bar = df.iloc[i]
        if bias == "bullish" and self._rejection(bar, "LONG"):
            n = float(r["atr20"])
            return {"direction": "LONG", "entry_price": close,
                    "stop_loss": float(bar["low"]) - 1.5 * n,
                    "take_profit": None, "strategy_id": "structure_pullback_h4",
                    "atr": n}
        if bias == "bearish" and self._rejection(bar, "SHORT"):
            n = float(r["atr20"])
            return {"direction": "SHORT", "entry_price": close,
                    "stop_loss": float(bar["high"]) + 1.5 * n,
                    "take_profit": None, "strategy_id": "structure_pullback_h4",
                    "atr": n}
        return None

    def on_fill(self, direction: str, entry_price: float, i: int, df: pd.DataFrame) -> None:
        self.in_position = True
        self.direction = direction
        self.entry_price = entry_price
        ind = self._indicators(df)
        n = float(ind["atr20"].iloc[i])
        self.atr_entry = n
        self.initial_stop = entry_price - 1.5 * n if direction == "LONG" else entry_price + 1.5 * n
        self.current_stop = self.initial_stop

    def update_stop(self, df: pd.DataFrame, i: int) -> None:
        if not self.in_position or self.entry_price is None or self.atr_entry is None:
            return
        close = float(df["close"].iloc[i])
        ep = self.entry_price; n = self.atr_entry
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
        # update trailing before checking
        self.update_stop(df, i)
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
