"""Hypothesis H2: Structure Pullback (XAUUSD H4) — re-specification.

NEW hypothesis distinct from structure_pullback_h4 (v1). Rules per H2_HYPOTHESIS.md,
written before running. Only two principled changes vs v1:
  - EMA proximity band 0.5% -> 1.5%
  - trigger: directional close (close>open long / close<open short) instead of
    strict rejection candle
HTF bias (>=70%), session (NY overlap), stop (1.5 ATR), trailing (+1R/+2R),
risk (1%) are UNCHANGED from v1.
"""

from __future__ import annotations

from typing import Optional

import pandas as pd

from edgelab.strategy.indicators import atr, ema, in_window

NY_OVERLAP = (8, 0, 11, 0)
EMA_BAND = 0.015  # H2 change: 1.5% (was 0.5%)


class StructurePullbackH4H2Strategy:
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
        need = 20
        if i < need:
            return None
        win = df.iloc[i - need:i]
        hh = list(win["high"].astype(float))
        ll = list(win["low"].astype(float))
        hu = sum(1 for k in range(1, len(hh)) if hh[k] > hh[k - 1])
        lu = sum(1 for k in range(1, len(ll)) if ll[k] > ll[k - 1])
        if hu >= 14 and lu >= 14:
            return "bullish"
        if hu <= 6 and lu <= 6:
            return "bearish"
        return None

    def _directional_close(self, bar: pd.Series, direction: str) -> bool:
        o = float(bar["open"]); c = float(bar["close"])
        # H2 change: any bar where close is on the bias side (won the bar)
        return c > o if direction == "LONG" else c < o

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
        if abs(close - ema_v) / ema_v > EMA_BAND:
            return None
        bar = df.iloc[i]
        if bias == "bullish" and self._directional_close(bar, "LONG"):
            n = float(r["atr20"])
            return {"direction": "LONG", "entry_price": close,
                    "stop_loss": float(bar["low"]) - 1.5 * n,
                    "take_profit": None, "strategy_id": "h2_structure_pullback_h4",
                    "atr": n}
        if bias == "bearish" and self._directional_close(bar, "SHORT"):
            n = float(r["atr20"])
            return {"direction": "SHORT", "entry_price": close,
                    "stop_loss": float(bar["high"]) + 1.5 * n,
                    "take_profit": None, "strategy_id": "h2_structure_pullback_h4",
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
