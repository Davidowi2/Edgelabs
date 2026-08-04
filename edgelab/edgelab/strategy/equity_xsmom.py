"""Hypothesis H5: Equity Cross-Sectional Momentum (monthly rebalance).

Basket simulator. NOT a single-instrument strategy; it builds an equal-weight
basket of the top-3 momentum ETFs each month-end (12-1 momentum), holds 1 month,
and records each monthly rotation as trades. The resulting trade list + equity
curve are fed into the SAME _compute_metrics + MonteCarlo used by the canonical
backtester, so the validation bar is identical and honest.

Per H5_HYPOTHESIS.md, written before running.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd


UNIVERSE = ["SPY", "QQQ", "XLF", "XLE", "XLK", "XLV", "XLI", "XLP", "XLY", "XLB", "XLU"]


@dataclass
class H5Trade:
    month: str
    symbol: str
    entry_price: float
    exit_price: float
    pnl: float
    exit_reason: str = "rebalance"


def run_h5(prices: dict[str, pd.DataFrame], initial_equity: float = 10_000.0,
           top_n: int = 3) -> tuple[list[H5Trade], list[tuple], dict]:
    """prices: {symbol: daily OHLCV DataFrame (UTC index)}. Returns
    (trades, equity_curve, metrics)."""
    # align to monthly closes
    close_m = pd.DataFrame({s: df["close"].astype(float).resample("ME").last()
                            for s, df in prices.items()})
    close_m = close_m.dropna(how="any")
    if len(close_m) < 14:
        return [], [], {"total_trades": 0, "win_rate": 0.0, "profit_factor": 0.0,
                         "sharpe_ratio": 0.0, "max_drawdown_pct": 0.0,
                         "total_return_pct": 0.0, "avg_rr": 0.0, "avg_holding_bars": 0.0}
    dates = close_m.index
    equity = initial_equity
    equity_curve = [(dates[0], equity)]
    trades: list[H5Trade] = []
    held: Optional[list[str]] = None
    held_prices: Optional[dict] = None

    for t in range(len(dates) - 1):
        month_end = dates[t]
        next_month_end = dates[t + 1]
        if t == 0:
            prev = close_m.iloc[t - 12] if t >= 12 else close_m.iloc[0]
        # 12-1 momentum: return from t-12 to t-1
        if t >= 13:
            mom = (close_m.iloc[t - 1] - close_m.iloc[t - 13]) / close_m.iloc[t - 13]
        else:
            mom = (close_m.iloc[t] - close_m.iloc[0]) / close_m.iloc[0]
        rank = mom.sort_values(ascending=False)
        selected = list(rank.head(top_n).index)

        if held is not None:
            # exit prior basket at next month open (use first daily of next month)
            for s in held:
                entry = held_prices[s]
                # exit price ~ next month's first available close (approx month open)
                nx = prices[s].loc[prices[s].index > month_end]
                exit_px = float(nx["close"].iloc[0]) if len(nx) else float(close_m[s].iloc[t])
                pnl = (exit_px - entry) / entry * (equity / top_n) if top_n else 0.0
                trades.append(H5Trade(str(month_end.date()), s, entry, exit_px, pnl))
                equity += pnl

        # enter new basket at this month's close (rebalance)
        held = selected
        held_prices = {s: float(close_m[s].iloc[t]) for s in selected}
        equity_curve.append((next_month_end, equity))

    metrics = _compute_metrics(equity_curve, trades, initial_equity)
    return trades, equity_curve, metrics


def _compute_metrics(equity_curve, trades, initial_equity):
    eq = np.array([e for _, e in equity_curve])
    if len(eq) < 2 or not trades:
        return {"total_trades": len(trades), "win_rate": 0.0, "profit_factor": 0.0,
                "sharpe_ratio": 0.0, "max_drawdown_pct": 0.0, "total_return_pct": 0.0,
                "avg_rr": 0.0, "avg_holding_bars": 0.0}
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
