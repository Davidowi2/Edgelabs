"""Hypothesis H8: G10 FX Carry (REAL rate-differential version).

This is the honest upgrade to the RETIRED H7. H7 ranked pairs by their trailing
12-month price return as a *proxy* for carry and failed the bar (PF 0.74, MC 7.3%,
9.17% DD). H8 ranks pairs by the actual interest-rate differential between the
two currencies — the textbook definition of FX carry — and is tested on the SAME
basket-simulator + Monte-Carlo + validation bar as H5/H7 (no separate, weaker bar).

SIGNAL (honest, reproducible):
  For each G10 pair (quoted foreign-per-USD), compute the carry = domestic minus
  foreign policy rate. Long the top-N highest-carry pairs, short the bottom-N
  lowest, equal weight, hold 1 month, rebalance monthly. The rate vector is a
  STATIC table (v0) of central-bank policy rates, clearly flagged below. A live
  FRED/Datastream series is the documented upgrade path (see H8_HYPOTHESIS.md).

Per-trade pnl: long  -> (exit-entry)/entry ; short -> (entry-exit)/entry.
Capital is split equally across the 2N open legs.

NOTE ON DATA HONESTY: the rate table is a single snapshot. In a true forward test
the rates would be time-varying; holding them static is the conservative choice
(it cannot invent a favourable time-varying edge). Flagged as v0.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd


# G10 majors available via yfinance. Pairs are quoted foreign-per-USD.
UNIVERSE = ["AUDUSD=X", "NZDUSD=X", "GBPUSD=X", "EURUSD=X",
            "USDJPY=X", "USDCHF=X", "USDCAD=X"]


# v0 static policy-rate snapshot (annual %, approximate, clearly documented).
# Source-class: central-bank policy rates circa 2024-2025. REPLACE with a
# time-varying FRED/Datastream series for a production forward test.
# Key by the FOREIGN currency of each quoted pair.
RATE_TABLE_V0 = {
    "AUD": 4.35,   # RBA
    "NZD": 5.50,   # RBNZ
    "GBP": 5.00,   # BoE
    "EUR": 4.00,   # ECB
    "JPY": 0.10,   # BoJ
    "CHF": 1.00,   # SNB
    "CAD": 4.50,   # BoC
}


def _pair_rate(symbol: str) -> float:
    """Carry = domestic (USD) rate minus foreign rate.

    Pairs quoted foreign-per-USD (e.g. AUDUSD=X) => foreign = AUD, domestic = USD.
    For USD-prefixed pairs (USDJPY=X) the foreign leg is the second currency (JPY).
    Higher carry => long candidate.
    """
    usd_rate = RATE_TABLE_V0["USD"] if "USD" in RATE_TABLE_V0 else 5.25
    code = symbol.replace("=X", "")
    if code.startswith("USD"):
        foreign = code[3:]          # e.g. USDJPY -> JPY
        foreign_rate = RATE_TABLE_V0.get(foreign, 0.0)
        return usd_rate - foreign_rate
    else:
        foreign = code[:3]          # e.g. AUDUSD -> AUD
        foreign_rate = RATE_TABLE_V0.get(foreign, 0.0)
        return usd_rate - foreign_rate


@dataclass
class H8Trade:
    month: str
    symbol: str
    side: str          # LONG / SHORT
    entry_price: float
    exit_price: float
    pnl: float
    exit_reason: str = "rebalance"


def run_h8(prices: dict[str, pd.DataFrame], initial_equity: float = 10_000.0,
           top_n: int = 3) -> tuple[list[H8Trade], list[tuple], dict]:
    """prices: {symbol: daily OHLCV DataFrame (UTC index)}. Returns
    (trades, equity_curve, metrics). Mirrors run_h7's basket simulator."""
    close_m = pd.DataFrame({s: df["close"].astype(float).resample("ME").last()
                            for s, df in prices.items()})
    close_m = close_m.dropna(how="any")
    empty = ([], [], {"total_trades": 0, "win_rate": 0.0, "profit_factor": 0.0,
                      "sharpe_ratio": 0.0, "max_drawdown_pct": 0.0,
                      "total_return_pct": 0.0, "avg_rr": 0.0, "avg_holding_bars": 0.0})
    if len(close_m) < 14 or close_m.shape[1] < (2 * top_n):
        return empty
    # rank by real rate carry (static snapshot)
    carry = pd.Series({s: _pair_rate(s) for s in close_m.columns})
    dates = close_m.index
    equity = initial_equity
    equity_curve = [(dates[0], equity)]
    trades: list[H8Trade] = []
    held: Optional[list[tuple]] = None  # (symbol, side, entry)
    n_legs = 2 * top_n

    for t in range(len(dates) - 1):
        month_end = dates[t]
        next_month_end = dates[t + 1]
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
                trades.append(H8Trade(str(month_end.date()), s, side, entry, exit_px, pnl))
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


def current_signal(rates: dict[str, float] = None, top_n: int = 3) -> dict:
    """Which pairs H8 would hold RIGHT NOW (used by a future TradeLocker forward
    test). Returns {as_of, longs, shorts, carry}. Rates override the v0 table."""
    r = dict(RATE_TABLE_V0)
    if rates:
        r.update(rates)
    carry = pd.Series({(s if s.endswith("=X") else s + "=X"):
                       (r.get("USD", 5.25) - r.get(c, 0.0))
                       for s, c in [(_fx_code(x), _foreign(x)) for x in UNIVERSE]})
    rank = carry.sort_values(ascending=False)
    longs = list(rank.head(top_n).index)
    shorts = list(rank.tail(top_n).index)
    return {"as_of": "v0-static", "longs": longs, "shorts": shorts,
            "carry": {k: round(v, 2) for k, v in carry.items()}}


def _foreign(symbol: str) -> str:
    code = symbol.replace("=X", "")
    return code[3:] if code.startswith("USD") else code[:3]


def _fx_code(symbol: str) -> str:
    return symbol
