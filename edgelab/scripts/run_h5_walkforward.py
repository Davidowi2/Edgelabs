"""Apply the walk-forward discipline (learned from tf-trend / our own harness) to H5.

The external 'systematic-trend-following' repo's key contribution is WALK-FORWARD
evaluation (rolling 1y-train / 3mo-test folds) — which our engine already supports
(edgelab/backtest/walk_forward.py). The point here: re-validate H5 (raw + vol-targeted)
ACROSS MANY OOS folds, not just one 80/20 split. If the edge is real, it survives
every fold; if it was a lucky split (like our crypto H4), walk-forward exposes it.

H5 has no tunable params, so we pass an empty grid — the harness then validates the
fixed 12-1 top-3 config on each OOS fold directly (true, parameter-free OOS).

Per protocol: offline backtest only, no live orders.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from edgelab.backtest.walk_forward import run_walk_forward, _agg_metrics
from edgelab.backtest.monte_carlo import run_monte_carlo
from edgelab.data.market_feed import MarketDataFeed
from edgelab.strategy.equity_xsmom import run_h5, UNIVERSE
from edgelab.strategy.h5_voltarget import run_h5_voltarget

OOS_MIN_TRADES = 30


def run_h5_walk_forward_folds(prices, runner, top_n=3,
                              train_bars=21, test_bars=3):
    """Roll non-overlapping OOS windows over the monthly-close panel and run H5 on
    each, attributing trades whose entry month falls inside the window. train_bars
    is the warm-up (so 12-1 momentum exists before the first OOS fold). Disjoint
    folds => this is a 'multiple OOS windows' robustness check (anti lucky-split),
    exactly the tf-trend discipline, applied to our parameter-free H5."""
    close_m = pd.DataFrame({s: df["close"].astype(float).resample("ME").last()
                            for s, df in prices.items()}).dropna(how="any")
    dates = close_m.index
    dates_naive = pd.to_datetime([d.date() for d in dates])  # avoid tz compare errors
    n = len(dates)
    # Compute H5 ONCE over the full panel; attribute trades to folds by entry month.
    full_tr, _, _ = runner({s: df for s, df in prices.items()}, initial_equity=10000.0, top_n=top_n)
    oos_trades = []
    folds = []
    fi = train_bars  # warm-up so 12-1 lookback is populated
    while fi + test_bars <= n:
        oos_start = dates_naive[fi]
        oos_end = dates_naive[min(fi + test_bars, n - 1)]
        cnt = 0
        for t in full_tr:
            td = pd.Timestamp(t.month)
            if oos_start <= td <= oos_end:
                oos_trades.append(t)
                cnt += 1
        folds.append({"fold": fi, "oos_trades": cnt})
        fi += test_bars
    pnls = [t.pnl for t in oos_trades]
    eq = [10000.0]
    for p in pnls:
        eq.append(eq[-1] + p)
    metrics = _agg_metrics(list(zip([dates_naive[0]] + [pd.Timestamp(t.month) for t in oos_trades], eq)),
                           oos_trades, 10000.0)
    mc = run_monte_carlo(pnls, initial_equity=10000.0, n_simulations=1000,
                         min_profitable_pct=70.0, seed=7) if pnls else None
    return oos_trades, folds, metrics, mc


def print_res(name, m, mc, trades):
    mc_s = f"MC={mc.profitable_pct:.1f}% {'PASS' if mc.passed else 'FAIL'}" if mc else "MC=n/a"
    print(f"  {name}: OOS trades={len(trades)} win={m['win_rate']*100:.1f}% "
          f"PF={m['profit_factor']:.2f} Sharpe={m['sharpe_ratio']:.2f} "
          f"maxDD={m['max_drawdown_pct']:.2f}% ret={m['total_return_pct']:.2f}% {mc_s}")


def main():
    feed = MarketDataFeed()
    prices = {}
    for s in UNIVERSE:
        try:
            prices[s] = feed.get(s, source="yfinance", interval="1d", years=5)
        except Exception as e:  # noqa: BLE001
            print(f"  skip {s}: {e}")
    if not prices:
        print("No data; abort.")
        return

    print("=== H5 walk-forward (rolling 1y-train / 3mo-test folds, 5y) ===")
    # RAW H5
    rt, rf, rm, rmc = run_h5_walk_forward_folds(prices, run_h5, top_n=3)
    print_res("RAW H5 OOS (walk-fwd)", rm, rmc, rt)
    # VOL-TARGETED H5
    vt, vf, vm, vmc = run_h5_walk_forward_folds(prices, run_h5_voltarget, top_n=3)
    print_res("VT  H5 OOS (walk-fwd)", vm, vmc, vt)

    print("\n=== Verdict ===")
    raw_ok = rm["profit_factor"] > 1.2 and rm["sharpe_ratio"] > 0.5 and len(rt) >= OOS_MIN_TRADES
    vt_ok = vm["profit_factor"] > 1.2 and vm["sharpe_ratio"] > 0.5 and len(vt) >= OOS_MIN_TRADES
    print(f"  RAW H5 walk-fwd edge holds: {'YES' if raw_ok else 'NO'} (PF={rm['profit_factor']:.2f}, {len(rt)} trades)")
    print(f"  VT  H5 walk-fwd edge holds: {'YES' if vt_ok else 'NO'} (PF={vm['profit_factor']:.2f}, {len(vt)} trades)")
    print(f"  If both YES -> H5 edge is ROBUST across folds (not a lucky single split).")
    print(f"  This is the tf-trend discipline applied to our proven strategy.")


if __name__ == "__main__":
    main()
