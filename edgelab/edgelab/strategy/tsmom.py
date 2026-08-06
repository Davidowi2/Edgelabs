"""Hypothesis H10 (internal): Time-Series Momentum (TSMOM) trend-following sleeve.

The ACTIVE, crisis-alpha piece for the multi-component system. Unlike H5 (cross-
sectional momentum — rank assets vs each other, long-only) and H9 (cross-sectional on
FX/crypto, which FAILED), TSMOM is DIRECTIONAL time-series momentum per Moskowitz/
Ooi/Pedersen (2012): for each asset, be long if its trailing return is positive, flat
(or short) if negative. It is UNCORRELATED to H5, and is the classic "crisis alpha" —
it tends to profit when equities crash, hedging Sleeve 1.

This is a DIFFERENT mechanism from H9 (which was cross-sectional ranking, not
directional TSMOM), so H9's failure does NOT pre-judge H10. But H10 must still earn
its place on the SAME honest bar via walk-forward (not assumed to transfer).

Per protocol: basket simulator, no live orders here.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd


# Default broad, liquid, UNCORRELATED universe spanning regimes.
DEFAULT_UNIVERSE = ["SPY", "QQQ", "TLT", "IEF", "GLD", "DBC"]


@dataclass
class TSMOMTrade:
    month: str
    symbol: str
    entry_price: float
    exit_price: float
    pnl: float
    side: str  # LONG / FLAT / SHORT
    exit_reason: str = "rebalance"


def run_tsmom(prices: dict[str, pd.DataFrame], initial_equity: float = 10_000.0,
              top_n: int = 6, lookback: int = 12, allow_short: bool = True,
              vol_target: Optional[float] = None) -> tuple[list, list, dict]:
    """Directional TSMOM across `top_n` assets. Each month, compute trailing
    return (t-1 to t-lookback-1, i.e. 12-1 month). Long if >0, short if <0 (when
    allow_short), else flat. Equal-weight across active positions, optionally
    vol-targeted (scale by target_vol / basket vol)."""
    close_m = pd.DataFrame({s: df["close"].astype(float).resample("ME").last()
                            for s, df in prices.items()}).dropna(how="any")
    if len(close_m) < lookback + 2:
        return [], [], {"total_trades": 0, "win_rate": 0.0, "profit_factor": 0.0,
                        "sharpe_ratio": 0.0, "max_drawdown_pct": 0.0,
                        "total_return_pct": 0.0, "avg_rr": 0.0, "avg_holding_bars": 0.0}
    dates = close_m.index
    equity = initial_equity
    equity_curve = [(dates[0], equity)]
    trades: list[TSMOMTrade] = []
    held: Optional[list[str]] = None
    held_side: dict = {}
    held_prices: dict = {}
    basket_rets: list = []

    def basket_vol():
        if len(basket_rets) < 2:
            return 0.0
        win = basket_rets[-12:]
        return float(np.std(win, ddof=1)) * np.sqrt(12) if len(win) >= 2 else 0.0

    for t in range(len(dates) - 1):
        month_end = dates[t]
        next_month_end = dates[t + 1]
        # trailing return t-lookback .. t-1
        if t >= lookback + 1:
            mom = (close_m.iloc[t - 1] - close_m.iloc[t - lookback - 1]) / close_m.iloc[t - lookback - 1]
        else:
            mom = (close_m.iloc[t] - close_m.iloc[0]) / close_m.iloc[0]
        # active = positive momentum (long); if allow_short, negative -> short
        longs = [s for s in close_m.columns if mom[s] > 0]
        shorts = [s for s in close_m.columns if (mom[s] < 0 and allow_short)]
        active = longs + shorts
        side = {s: ("LONG" if s in longs else "SHORT") for s in active}

        lev = 1.0
        if vol_target:
            bv = basket_vol()
            if bv > 1e-6:
                lev = min(1.5, vol_target / bv)

        if held is not None:
            rets = []
            for s in held:
                entry = held_prices[s]
                nx = prices[s].loc[prices[s].index > month_end]
                exit_px = float(nx["close"].iloc[0]) if len(nx) else float(close_m[s].iloc[t])
                direction = 1.0 if held_side[s] == "LONG" else -1.0
                exposure = equity * lev / max(len(held), 1)
                pnl = direction * (exit_px - entry) / entry * exposure
                trades.append(TSMOMTrade(str(month_end.date()), s, entry, exit_px, pnl, held_side[s]))
                equity += pnl
                rets.append(direction * (exit_px - entry) / entry)
            basket_rets.append(float(np.mean(rets)) if rets else 0.0)

        held = active
        held_side = side
        held_prices = {s: float(close_m[s].iloc[t]) for s in active}
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
    wins = [p for p in pnls if p > 0]; losses = [p for p in pnls if p <= 0]
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
