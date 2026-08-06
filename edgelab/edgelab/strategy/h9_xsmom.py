"""Hypothesis H9: Cross-Sectional Momentum on TradeLocker assets (FX + Crypto).

LEARNED DESIGN. This ports the EXACT proven mechanism of H5 (equity cross-sectional
momentum) onto instruments that TradeLocker can trade, because every non-H5 attempt
failed for a *learnable* reason:
  - H7/H8 FX carry (absolute directional bet on rate differentials): killed by the
    2024-26 rate-CUTTING regime. Lesson: absolute single-factor bets are regime-fragile.
  - Gold v1/v2/v3 (single-instrument price-action): INERT (0/1/40 trades). Lesson:
    over-filtered single-name strategies don't fire.
  - Crypto H4 (single-instrument BTC breakout): IS PF 2.73 but OOS 0 trades (regime
    break). Lesson: single-name absolute breakouts decay the moment the window ends.

H5 survived because it is (a) CROSS-SECTIONAL (ranks assets RELATIVE to each other,
not betting absolutes), (b) on a BROAD liquid universe, (c) monthly rebalance,
(d) direction-AGNOSTIC. H9 reuses that exact recipe so it inherits those properties:
  - FX universe: G10 pairs. Rank by 12-1 momentum; LONG top-N highest-momentum,
    SHORT bottom-N lowest-momentum. Direction-agnostic -> immune to the H8 rate regime.
  - Crypto universe: top liquid coins. Rank by 12-1 momentum; LONG top-N. Broad
    universe -> fixes H4's single-BTC problem; relative ranking -> regime-robust.
Same basket simulator + _compute_metrics + MonteCarlo as H5, so the bar is identical.

Honest guardrails: same validation bar as H5/H8 (PF>1.2, Sharpe>0.5, MC>=70%,
DD<4%) PLUS the new OOS-trade-count gate (inert/IS-only strategies cannot pass).
No tuning to pass. If it fails, retired like the rest.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd


# G10 FX pairs (foreign-per-USD), TradeLocker-tradable majors.
FX_UNIVERSE = ["AUDUSD=X", "NZDUSD=X", "GBPUSD=X", "EURUSD=X",
               "USDJPY=X", "USDCHF=X", "USDCAD=X"]

# Top liquid crypto (ccxt symbols), TradeLocker/Crypto-tradable.
CRYPTO_UNIVERSE = ["BTC/USDT", "ETH/USDT", "BNB/USDT", "SOL/USDT", "XRP/USDT",
                   "ADA/USDT", "DOGE/USDT", "AVAX/USDT", "DOT/USDT", "LINK/USDT"]


@dataclass
class H9Trade:
    month: str
    symbol: str
    side: str          # LONG / SHORT
    entry_price: float
    exit_price: float
    pnl: float
    exit_reason: str = "rebalance"


def _monthly_close(prices: dict[str, pd.DataFrame]) -> pd.DataFrame:
    close_m = pd.DataFrame({s: df["close"].astype(float).resample("ME").last()
                            for s, df in prices.items()})
    return close_m.dropna(how="any")


def run_h9(prices: dict[str, pd.DataFrame], initial_equity: float = 10_000.0,
           top_n: int = 3, long_short: bool = True) -> tuple[list[H9Trade], list[tuple], dict]:
    """Cross-sectional 12-1 momentum, monthly rebalance.

    For each month-end: rank by momentum (return t-12 -> t-1); long top-N, and if
    long_short, short bottom-N. Equal weight across the 2N legs. Mirrors run_h5.
    """
    close_m = _monthly_close(prices)
    empty = ([], [], {"total_trades": 0, "win_rate": 0.0, "profit_factor": 0.0,
                      "sharpe_ratio": 0.0, "max_drawdown_pct": 0.0, "total_return_pct": 0.0,
                      "avg_rr": 0.0, "avg_holding_bars": 1.0})
    if len(close_m) < 14 or close_m.shape[1] < (2 * top_n if long_short else top_n):
        return empty
    dates = close_m.index
    equity = initial_equity
    equity_curve = [(dates[0], equity)]
    trades: list[H9Trade] = []
    held: Optional[list[tuple]] = None  # (symbol, side, entry)
    n_legs = 2 * top_n if long_short else top_n

    for t in range(len(dates) - 1):
        month_end = dates[t]
        next_month_end = dates[t + 1]
        # 12-1 momentum: return from t-12 to t-1
        if t >= 13:
            mom = (close_m.iloc[t - 1] - close_m.iloc[t - 13]) / close_m.iloc[t - 13]
        else:
            mom = (close_m.iloc[t] - close_m.iloc[0]) / close_m.iloc[0]
        rank = mom.sort_values(ascending=False)
        longs = list(rank.head(top_n).index)
        shorts = list(rank.tail(top_n).index) if long_short else []
        selected = [(s, "LONG") for s in longs] + [(s, "SHORT") for s in shorts]

        if held is not None:
            for (s, side, entry) in held:
                nx = prices[s].loc[prices[s].index > month_end]
                exit_px = float(nx["close"].iloc[0]) if len(nx) else float(close_m[s].iloc[t])
                if side == "LONG":
                    pnl = (exit_px - entry) / entry * (equity / n_legs) if n_legs else 0.0
                else:
                    pnl = (entry - exit_px) / entry * (equity / n_legs) if n_legs else 0.0
                trades.append(H9Trade(str(month_end.date()), s, side, entry, exit_px, pnl))
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


def current_signal(prices: dict[str, pd.DataFrame], top_n: int = 3,
                   lookback: int = 12, long_short: bool = True) -> dict:
    """Forward-test helper: which instruments H9 would hold RIGHT NOW. Returns
    {as_of, longs, shorts, ranked}."""
    close_m = _monthly_close(prices)
    if len(close_m) < lookback + 1:
        return {"as_of": None, "longs": [], "shorts": [], "ranked": [],
                "reason": f"need >= {lookback + 1} months of data"}
    t = len(close_m) - 1
    mom = (close_m.iloc[t - 1] - close_m.iloc[t - 1 - lookback]) / close_m.iloc[t - 1 - lookback]
    ranked = sorted(mom.items(), key=lambda kv: kv[1], reverse=True)
    longs = [s for s, _ in ranked[:top_n]]
    shorts = [s for s, _ in ranked[-top_n:]] if long_short else []
    return {"as_of": str(close_m.index[t].date()), "longs": longs, "shorts": shorts,
            "ranked": [(s, float(m)) for s, m in ranked], "reason": None}
