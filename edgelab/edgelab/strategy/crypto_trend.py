"""Hypothesis H4: Crypto Trend (BTC/USDT, daily).

NEW hypothesis, uncorrelated edge class vs the retired FX/gold trend family.
Per H4_HYPOTHESIS.md, written before running:
  - long only when close > EMA200
  - entry: 20-bar highest-close breakout (close == max close last 20 bars)
  - stop: 2 x ATR(20) below entry
  - exit: stop, or close < EMA50, or 30-bar time stop
  - no session filter (24/7)
  - 1% risk via RiskEngine
"""

from __future__ import annotations

from typing import Optional

import pandas as pd

from edgelab.strategy.indicators import atr, ema


class CryptoTrendStrategy:
    def __init__(self) -> None:
        self.in_position = False
        self.entry_price: Optional[float] = None
        self.stop: Optional[float] = None
        self.atr_entry: Optional[float] = None
        self.bars_in_trade = 0
        self._df = None
        self._ind = None

    def _indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        if self._df is df and self._ind is not None:
            return self._ind
        out = pd.DataFrame(index=df.index)
        out["ema200"] = ema(df["close"].astype(float), 200)
        out["ema50"] = ema(df["close"].astype(float), 50)
        out["atr20"] = atr(df, 20, ema=True)
        self._df = df
        self._ind = out
        return out

    def signal(self, df: pd.DataFrame, i: int) -> Optional[dict]:
        if self.in_position:
            return None
        if i < 200:
            return None
        ind = self._indicators(df)
        r = ind.iloc[i]
        if pd.isna(r["ema200"]) or pd.isna(r["atr20"]) or pd.isna(r["ema50"]):
            return None
        close = float(df["close"].iloc[i])
        if close <= float(r["ema200"]):  # uptrend filter
            return None
        # 20-bar highest close breakout
        if i < 20:
            return None
        window = df["close"].iloc[i - 20:i]
        if close < float(window.max()):
            return None
        n = float(r["atr20"])
        return {"direction": "LONG", "entry_price": close,
                "stop_loss": close - 2.0 * n,
                "take_profit": None, "strategy_id": "h4_crypto_trend",
                "atr": n}

    def on_fill(self, direction: str, entry_price: float, i: int, df: pd.DataFrame) -> None:
        self.in_position = True
        self.entry_price = entry_price
        ind = self._indicators(df)
        self.atr_entry = float(ind["atr20"].iloc[i])
        self.stop = entry_price - 2.0 * self.atr_entry
        self.bars_in_trade = 0

    def exit_signal(self, df: pd.DataFrame, i: int) -> Optional[str]:
        if not self.in_position or self.stop is None:
            return None
        self.bars_in_trade += 1
        close = float(df["close"].iloc[i])
        ind = self._indicators(df)
        # trend invalidation
        if close < float(ind["ema50"].iloc[i]):
            return "trend_exit"
        # time stop
        if self.bars_in_trade >= 30:
            return "time_stop"
        # hard stop
        if close < self.stop:
            return "stop_loss"
        return None

    def on_exit(self) -> None:
        self.in_position = False
        self.entry_price = None
        self.stop = None
        self.atr_entry = None
        self.bars_in_trade = 0
