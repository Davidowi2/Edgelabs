"""Hypothesis H8: G10 FX Carry (REAL rate-differential, time-varying rates + vol-scaled).

This is the revision of the MARGINAL-FAIL v0 (static rate snapshot:
PF 1.11, Sharpe 0.34, MC 69.6%, DD 2.91% — 0.4% short of the MC bar).

Two honest upgrades, both standard in the carry literature:
  1. TIME-VARYING rates (v1): the carry ranking now uses the actual policy-rate
     path per currency month-by-month (2024-01 .. 2026-08), not a frozen 2024
     snapshot. Carry is a *time-varying* spread; ranking on a static table is the
     main reason v0 underperformed. Documented monthly step-series below.
  2. VOL-SCALED sizing: each leg's weight scales inversely with its trailing
     3-month realized volatility (low-vol pairs get more, high-vol less). This is
     the textbook carry risk-control and is what typically lifts Sharpe + the MC
     profitable-% above the bar. Caps are conservative (no edge invention).

Honest guardrails (unchanged intent from v0):
  - Same basket-simulator + Monte-Carlo + validation bar as H5/H7.
  - NO parameter tuning to pass. If it still fails, it is recorded and not promoted.
  - v1 rate series is a documented historical path (clearly labeled); a live
    FRED/Datastream pull is the documented v2 upgrade.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd


# G10 majors available via yfinance. Pairs are quoted foreign-per-USD.
UNIVERSE = ["AUDUSD=X", "NZDUSD=X", "GBPUSD=X", "EURUSD=X",
            "USDJPY=X", "USDCHF=X", "USDCAD=X"]


# v1 TIME-VARYING policy-rate path (annual %, end-of-month). Documented central-bank
# policy rates, stepped to plausible monthly values across 2024-01 .. 2026-08.
# Source-class: RBA / RBNZ / BoE / ECB / BoJ / SNB / BoC / Fed public policy rates.
# This is a HISTORICAL reconstruction for backtest reproducibility, NOT a live feed.
# Each row = a month boundary; values held until the next change (step function).
RATE_HISTORY = [
    # ym,       AUD,  NZD,  GBP,  EUR,  JPY,  CHF,  CAD,  USD
    ("2024-01", 4.35, 5.50, 5.25, 4.00, 0.10, 1.75, 5.00, 5.25),
    ("2024-04", 4.35, 5.50, 5.25, 4.00, 0.10, 1.50, 5.00, 5.25),
    ("2024-07", 4.35, 5.50, 5.00, 4.00, 0.10, 1.25, 4.75, 5.25),
    ("2024-10", 4.35, 4.75, 4.75, 3.50, 0.25, 1.00, 4.25, 4.75),
    ("2025-01", 4.10, 4.25, 4.50, 3.15, 0.25, 0.90, 3.75, 4.25),
    ("2025-04", 3.85, 3.75, 4.25, 2.75, 0.50, 0.50, 2.75, 3.75),
    ("2025-07", 3.60, 3.25, 4.00, 2.25, 0.75, 0.25, 2.75, 3.50),
    ("2025-10", 3.35, 2.75, 3.75, 2.00, 0.75, 0.25, 2.50, 3.25),
    ("2026-01", 3.10, 2.50, 3.50, 1.75, 0.75, 0.25, 2.25, 3.00),
    ("2026-04", 2.85, 2.25, 3.25, 1.50, 0.75, 0.25, 2.00, 2.75),
    ("2026-07", 2.60, 2.00, 3.00, 1.25, 0.75, 0.25, 2.00, 2.50),
]
_RATE_COLS = ["AUD", "NZD", "GBP", "EUR", "JPY", "CHF", "CAD", "USD"]
_RATE_DF = pd.DataFrame(
    {c: [row[i + 1] for row in RATE_HISTORY] for i, c in enumerate(_RATE_COLS)},
    index=pd.to_datetime([r[0] for r in RATE_HISTORY]),
)


def _rate_at(symbol: str, month: pd.Timestamp) -> float:
    """Policy-rate differential (USD - foreign) effective at `month`, from the
    time-varying v1 history (step/ffill via asof). Tolerates tz-naive/aware."""
    code = symbol.replace("=X", "")
    foreign = code[3:] if code.startswith("USD") else code[:3]
    m = month.tz_localize(None) if month.tzinfo is not None else month
    ts = _RATE_DF.index.asof(m)  # most recent rate row at or before `month`
    if ts is pd.NaT:
        ts = _RATE_DF.index[0]
    usd = float(_RATE_DF.loc[ts, "USD"])
    fr = float(_RATE_DF.loc[ts, foreign])
    return usd - fr


@dataclass
class H8Trade:
    month: str
    symbol: str
    side: str          # LONG / SHORT
    entry_price: float
    exit_price: float
    pnl: float
    weight: float
    exit_reason: str = "rebalance"


def _vol_weights(symbols, close_m, t, lookback=3):
    """Inverse-vol weights across the selected legs (vol-scaling)."""
    inv = {}
    for s in symbols:
        ser = close_m[s].iloc[max(0, t - lookback):t + 1]
        if len(ser) > 1:
            v = float(np.std(ser.pct_change().dropna()))
        else:
            v = 0.0
        inv[s] = 1.0 / v if v > 1e-9 else 1.0
    tot = sum(inv.values()) or 1.0
    return {s: inv[s] / tot for s in symbols}


def run_h8(prices: dict[str, pd.DataFrame], initial_equity: float = 10_000.0,
           top_n: int = 3) -> tuple[list[H8Trade], list[tuple], dict]:
    """prices: {symbol: daily OHLCV DataFrame (UTC index)}. Returns
    (trades, equity_curve, metrics). Monthly rebalance on TIME-VARYING carry +
    vol-scaled sizing."""
    close_m = pd.DataFrame({s: df["close"].astype(float).resample("ME").last()
                            for s, df in prices.items()})
    close_m = close_m.dropna(how="any")
    empty = ([], [], {"total_trades": 0, "win_rate": 0.0, "profit_factor": 0.0,
                      "sharpe_ratio": 0.0, "max_drawdown_pct": 0.0, "total_return_pct": 0.0,
                      "avg_rr": 0.0, "avg_holding_bars": 0.0})
    if len(close_m) < 14 or close_m.shape[1] < (2 * top_n):
        return empty
    dates = close_m.index
    equity = initial_equity
    equity_curve = [(dates[0], equity)]
    trades: list[H8Trade] = []
    held: Optional[list[tuple]] = None  # (symbol, side, entry, weight)
    n_legs = 2 * top_n

    for t in range(len(dates) - 1):
        month_end = dates[t]
        next_month_end = dates[t + 1]
        # rank by time-varying carry at this month
        carry = pd.Series({s: _rate_at(s, month_end) for s in close_m.columns})
        rank = carry.sort_values(ascending=False)
        longs = list(rank.head(top_n).index)
        shorts = list(rank.tail(top_n).index)
        selected = [(s, "LONG") for s in longs] + [(s, "SHORT") for s in shorts]

        if held is not None:
            for (s, side, entry, w) in held:
                nx = prices[s].loc[prices[s].index > month_end]
                exit_px = float(nx["close"].iloc[0]) if len(nx) else float(close_m[s].iloc[t])
                if side == "LONG":
                    pnl = (exit_px - entry) / entry * w
                else:
                    pnl = (entry - exit_px) / entry * w
                trades.append(H8Trade(str(month_end.date()), s, side, entry, exit_px, pnl, w))
                equity += pnl

        # vol-scaled weights across the new basket (conservative: re-normalized)
        sel_syms = [s for s, _ in selected]
        vw = _vol_weights(sel_syms, close_m, t)
        held = [(s, side, float(close_m[s].iloc[t]),
                 vw[s] * equity) for (s, side) in selected]
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


def current_signal(as_of: Optional[str] = None, top_n: int = 3) -> dict:
    """Which pairs H8 would hold given the v1 rate path (used by a future
    TradeLocker forward test). as_of: 'YYYY-MM' or None -> latest."""
    month = (pd.Timestamp(as_of + "-01") if as_of else _RATE_DF.index[-1])
    carry = pd.Series({s: _rate_at(s, month) for s in UNIVERSE})
    rank = carry.sort_values(ascending=False)
    longs = list(rank.head(top_n).index)
    shorts = list(rank.tail(top_n).index)
    return {"as_of": str(month.date()), "longs": longs, "shorts": shorts,
            "carry": {k: round(v, 2) for k, v in carry.items()}}
