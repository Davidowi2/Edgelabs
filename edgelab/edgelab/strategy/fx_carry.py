"""Hypothesis H7: G10 FX Carry (monthly rebalance).

Basket simulator, mirroring the H5 equity cross-sectional momentum design so
the validation bar is identical and honest. Written before running
(per RESEARCH_PROTOCOL_v1); see H7_HYPOTHESIS.md.

SIGNAL (honest, reproducible, no external rate data):
  FX carry is driven by interest-rate differentials. Without a rate time series
  we use the standard academic *carry proxy*: each pair's trailing 12-month spot
  return. The forward-premium anomaly says high-yield currencies tend to keep
  appreciating, so the 12M return ranks yield-seeking behaviour well enough to
  be a reproducible, testable proxy. The REAL upgrade path is a policy-rate time
  series (e.g. FRED/Datastream); this proxy is explicitly a stand-in and is
  flagged as such in the report.

  Long the top-N highest 12M-return pairs, short the bottom-N lowest, equal
  weight, hold 1 month, rebalance monthly. This is a DIFFERENT asset class
  (G10 FX) from equity momentum (H5) -> the diversification value is the low
  correlation, independent of whether the proxy perfectly captures carry.

Per-trade pnl: long  -> (exit-entry)/entry ; short -> (entry-exit)/entry.
Capital is split equally across the 2N open legs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd


# G10 majors available via yfinance (adjust as data allows). Pairs are quoted
# as foreign-per-USD where the first leg is the commodity/risk currency.
UNIVERSE = ["AUDUSD=X", "NZDUSD=X", "GBPUSD=X", "EURUSD=X",
            "USDJPY=X", "USDCHF=X", "USDCAD=X"]


@dataclass
class H7Trade:
    month: str
    symbol: str
    side: str          # LONG / SHORT
    entry_price: float
    exit_price: float
    pnl: float
    exit_reason: str = "rebalance"


def _carry_proxy(close_m: pd.DataFrame, t: int) -> pd.Series:
    """12-month trailing return of each pair as the carry proxy at month t."""
    if t >= 13:
        return (close_m.iloc[t - 1] - close_m.iloc[t - 13]) / close_m.iloc[t - 13]
    return (close_m.iloc[t] - close_m.iloc[0]) / close_m.iloc[0]


def run_h7(prices: dict[str, pd.DataFrame], initial_equity: float = 10_000.0,
           top_n: int = 3) -> tuple[list[H7Trade], list[tuple], dict]:
    """prices: {symbol: daily OHLCV DataFrame (UTC index)}. Returns
    (trades, equity_curve, metrics)."""
    close_m = pd.DataFrame({s: df["close"].astype(float).resample("ME").last()
                            for s, df in prices.items()})
    close_m = close_m.dropna(how="any")
    empty = ([], [], {"total_trades": 0, "win_rate": 0.0, "profit_factor": 0.0,
                      "sharpe_ratio": 0.0, "max_drawdown_pct": 0.0,
                      "total_return_pct": 0.0, "avg_rr": 0.0, "avg_holding_bars": 0.0})
    if len(close_m) < 14 or close_m.shape[1] < (2 * top_n):
        return empty
    dates = close_m.index
    equity = initial_equity
    equity_curve = [(dates[0], equity)]
    trades: list[H7Trade] = []
    held: Optional[list[tuple]] = None  # (symbol, side, entry)
    n_legs = 2 * top_n

    for t in range(len(dates) - 1):
        month_end = dates[t]
        next_month_end = dates[t + 1]
        carry = _carry_proxy(close_m, t)
        rank = carry.sort_values(ascending=False)
        longs = list(rank.head(top_n).index)
        shorts = list(rank.tail(top_n).index)
        selected = [(s, "LONG") for s in longs] + [(s, "SHORT") for s in shorts]

        if held is not None:
            weight = equity / n_legs if n_legs else 0.0
            for (s, side, entry) in held:
                nx = prices[s].loc[prices[s].index > month_end]
                exit_px = float(nx["close"].iloc[0]) if len(nx) else float(close_m[s].iloc[t])
                if side == "LONG":
                    pnl = (exit_px - entry) / entry * weight
                else:
                    pnl = (entry - exit_px) / entry * weight
                trades.append(H7Trade(str(month_end.date()), s, side, entry, exit_px, pnl))
                equity += pnl

        held = [(s, side, float(close_m[s].iloc[t])) for (s, side) in selected]
        equity_curve.append((next_month_end, equity))

    metrics = _compute_metrics(equity_curve, trades, initial_equity)
    return trades, equity_curve, metrics


def _compute_metrics(equity_curve, trades, initial_equity):
    eq = np.array([e for _, e in equity_curve])
    if len(eq) < 2 or not trades:
        return {"total_trades": len(trades), "win_rate": 0.0, "profit_factor": 0.0,
                "sharpe_ratio": 0.0, "max_drawdown_pct": 0.0, "total_return_pct": 0.0,
                "avg_rr": 0.0, "avg_holding_bars": 1.0}
    ret = np.diff(eq)
    total_return_pct = (eq[-1] - initial_equity) / initial_equity * 100
    peak = np.maximum.accumulate(eq)
    dd = (peak - eq) / np.where(peak == 0, 1, peak)
    max_dd = float(np.max(dd)) * 100
    sharpe = 0.0
    if len(ret) > 1 and np.std(ret) > 0:
        sharpe = float(np.mean(ret) / np.std(ret)) * np.sqrt(12)
    pnls = [t.pnl for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    win_rate = len(wins) / len(pnls)
    gw = sum(wins); gl = abs(sum(losses))
    pf = gw / gl if gl > 0 else (float("inf") if gw > 0 else 0.0)
    aw = gw / len(wins) if wins else 0.0
    al = gl / len(losses) if losses else 0.0
    avg_rr = aw / al if al > 0 else (float("inf") if aw > 0 else 0.0)
    return {"total_trades": len(trades), "win_rate": win_rate, "profit_factor": pf,
            "sharpe_ratio": sharpe, "max_drawdown_pct": max_dd,
            "total_return_pct": total_return_pct, "avg_rr": avg_rr,
            "avg_holding_bars": 1.0}
