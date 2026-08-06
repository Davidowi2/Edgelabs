"""H5 vol-targeted variant (Multi-Component Design, Sleeve 1).

Faithful Moreira-Muir "volatility-managed portfolio" applied to the PROVEN H5
cross-sectional equity momentum basket. At each monthly rebalance we estimate the
basket's trailing realized volatility and scale exposure so the basket targets a
fixed annual vol (default 12%), capped at max_leverage.

REDUCES TO RAW H5 when leverage == 1 (target_vol high / vol low), so we can compare
honestly on the same 5y bar + OOS gate. No tuning-to-pass: target_vol and
max_leverage are fixed a-priori literature values (Moreira & Muir 2017 use ~15%;
we use 12% and cap at 1.5x for prudence).

Per Edgelabs protocol: offline backtest only; no live orders here.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd


@dataclass
class H5VTrade:
    month: str
    symbol: str
    entry_price: float
    exit_price: float
    pnl: float
    leverage: float
    exit_reason: str = "rebalance"


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
    gw, gl = sum(wins), abs(sum(losses))
    pf = gw / gl if gl > 0 else (float("inf") if gw > 0 else 0.0)
    aw = gw / len(wins) if wins else 0.0
    al = gl / len(losses) if losses else 0.0
    avg_rr = aw / al if al > 0 else (float("inf") if aw > 0 else 0.0)
    return {"total_trades": len(trades), "win_rate": win_rate, "profit_factor": pf,
            "sharpe_ratio": sharpe, "max_drawdown_pct": max_dd,
            "total_return_pct": total_return_pct, "avg_rr": avg_rr,
            "avg_holding_bars": 1.0}


def run_h5_voltarget(prices: dict[str, pd.DataFrame], initial_equity: float = 10_000.0,
                     top_n: int = 3, target_vol_annual: float = 0.12,
                     vol_lookback: int = 12, max_leverage: float = 1.5) -> tuple[list, list, dict]:
    """Vol-managed H5. Same selection (12-1 momentum top-3) as raw H5, but exposure
    scaled by L = clamp(target_vol / realized_basket_vol, 0, max_leverage)."""
    close_m = pd.DataFrame({s: df["close"].astype(float).resample("ME").last()
                            for s, df in prices.items()}).dropna(how="any")
    if len(close_m) < 14:
        return [], [], {"total_trades": 0, "win_rate": 0.0, "profit_factor": 0.0,
                        "sharpe_ratio": 0.0, "max_drawdown_pct": 0.0,
                        "total_return_pct": 0.0, "avg_rr": 0.0, "avg_holding_bars": 0.0}
    dates = close_m.index
    equity = initial_equity
    equity_curve = [(dates[0], equity)]
    trades: list[H5VTrade] = []
    held: Optional[list[str]] = None
    held_prices: Optional[dict] = None
    basket_rets: list[float] = []  # trailing basket monthly returns (for vol est)

    def basket_vol() -> float:
        if len(basket_rets) < 2:
            return 0.0
        win = basket_rets[-vol_lookback:]
        if len(win) < 2:
            return 0.0
        return float(np.std(win, ddof=1)) * np.sqrt(12)

    for t in range(len(dates) - 1):
        month_end = dates[t]
        next_month_end = dates[t + 1]
        if t >= 13:
            mom = (close_m.iloc[t - 1] - close_m.iloc[t - 13]) / close_m.iloc[t - 13]
        else:
            mom = (close_m.iloc[t] - close_m.iloc[0]) / close_m.iloc[0]
        rank = mom.sort_values(ascending=False)
        selected = list(rank.head(top_n).index)

        lev = 1.0
        if held is not None:
            bv = basket_vol()
            if bv > 1e-6:
                lev = min(max_leverage, target_vol_annual / bv)
            # exit prior basket
            rets = []
            for s in held:
                entry = held_prices[s]
                nx = prices[s].loc[prices[s].index > month_end]
                exit_px = float(nx["close"].iloc[0]) if len(nx) else float(close_m[s].iloc[t])
                exposure = equity * lev / top_n
                pnl = (exit_px - entry) / entry * exposure
                trades.append(H5VTrade(str(month_end.date()), s, entry, exit_px, pnl, lev))
                equity += pnl
                rets.append((exit_px - entry) / entry)
            basket_rets.append(float(np.mean(rets)) if rets else 0.0)

        held = selected
        held_prices = {s: float(close_m[s].iloc[t]) for s in selected}
        equity_curve.append((next_month_end, equity))

    metrics = _compute_metrics(equity_curve, trades, initial_equity)
    return trades, equity_curve, metrics
