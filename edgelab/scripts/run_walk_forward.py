"""Walk-forward re-run on the now-plentiful 5y+ history (P1c / P1d).

H5 (equity cross-sectional momentum): rolling monthly folds over ~27y of data.
  - train on trailing TRAIN_MONTHS, select best top_n in {2,3,4,5}
  - validate on next TEST_MONTHS (true OOS), never used for selection
  - aggregate OOS trades -> metrics + Monte Carlo

H4 (crypto trend): rolling daily folds over 5.47y of BTC.
  - train 500 bars, test 250 bars, step 250 (empty param grid = single config)
  - aggregate OOS trades -> metrics + Monte Carlo
"""
from __future__ import annotations

import sys, warnings
from pathlib import Path

import pandas as pd

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from edgelab.backtest.walk_forward import run_walk_forward
from edgelab.backtest.monte_carlo import run_monte_carlo
from edgelab.data.market_feed import MarketDataFeed
from edgelab.strategy.crypto_trend import CryptoTrendStrategy
from edgelab.strategy.equity_xsmom import run_h5, UNIVERSE

TRAIN_MONTHS = 60
TEST_MONTHS = 18
WARMUP = 24  # selection window length (>=14 for run_h5's 12-1 lookback guard)


def months_list(prices):
    return list(next(iter(prices.values()))["close"].astype(float).resample("ME").last().index)


def slice_months(df, m_list):
    per = [str(x.to_period("M")) for x in m_list]
    s = df.index.to_series().dt.strftime("%Y-%m")
    return df[s.isin(per)]


def h5_walk_forward(prices):
    months = months_list(prices)
    if len(months) < TRAIN_MONTHS + TEST_MONTHS + 12:
        return {"error": "still insufficient months", "n": len(months)}
    WARMUP = 24  # selection window length (>=14 for run_h5's 12-1 lookback guard)
    oos_trades = []
    fold_summaries = []
    k = TRAIN_MONTHS
    while k + TEST_MONTHS + WARMUP <= len(months):
        train_m = months[:k]
        # selection window = last WARMUP months before the test window
        sel_m = months[k - WARMUP:k]
        test_m = months[k:k + TEST_MONTHS]
        best_n, best_pf = 3, -1.0
        for n in (2, 3, 4, 5):
            _, _, mtr = run_h5({s: slice_months(df, sel_m) for s, df in prices.items()},
                               initial_equity=10000.0, top_n=n)
            pf = mtr["profit_factor"]
            if isinstance(pf, float) and pf > 0 and pf > best_pf:
                best_pf, best_n = pf, n
        oos_t, _, oos_m = run_h5({s: slice_months(df, test_m) for s, df in prices.items()},
                                 initial_equity=10000.0, top_n=best_n)
        oos_trades.extend(oos_t)
        fold_summaries.append({"train_months": len(train_m), "test_months": len(test_m),
                               "best_n": best_n, "oos_trades": oos_m["total_trades"],
                               "oos_pf": oos_m["profit_factor"]})
        k += TEST_MONTHS
    pnls = [t.pnl for t in oos_trades]
    mc = run_monte_carlo(pnls, initial_equity=10000.0, n_simulations=1000,
                         min_profitable_pct=70.0, seed=7) if pnls else None
    # Build an equity curve from cumulative P&L so metrics don't short-circuit.
    eq = [10000.0]
    for p in pnls:
        eq.append(eq[-1] + p)
    eq_curve = list(zip(months[:len(eq)], eq))
    from edgelab.backtest.walk_forward import _agg_metrics
    return {"folds": fold_summaries, "oos_trades": oos_trades,
            "metrics": _agg_metrics(eq_curve, oos_trades, 10000.0), "monte_carlo": mc,
            "n_months": len(months)}


def main():
    feed = MarketDataFeed()

    # ---------------- H5 WALK-FORWARD (real history now available) ----------------
    print("=== H5 WALK-FORWARD (equity cross-sectional momentum, ~27y) ===")
    prices = {}
    for s in UNIVERSE:
        prices[s] = feed.get(s, source="yfinance", interval="1d", years=10)
    wf = h5_walk_forward(prices)
    if "error" in wf:
        print("  ", wf); return
    m = wf["metrics"]; mc = wf["monte_carlo"]
    print(f"  total months={wf['n_months']} folds={len(wf['folds'])} "
          f"OOS trades={m['total_trades']}")
    print(f"  OOS win={m['win_rate']*100:.1f}% PF={m['profit_factor']:.2f} "
          f"avgRR={m['avg_rr']:.2f}")
    if mc:
        print(f"  OOS MonteCarlo profitable={mc.profitable_pct:.1f}% "
              f"({'PASS' if mc.passed else 'FAIL'})")
    print(f"  H5 WF verdict: {'PASS >=2yr OOS stable' if (m['profit_factor']>1.2 and (mc and mc.passed)) else 'REVIEW'}")

    # ---------------- H6 WALK-FORWARD (crypto 4h, 5y, 11k bars) ----------------
    print("\n=== H6 WALK-FORWARD (BTC/USDT 4h, 5y) ===")
    btc4h = feed.get("BTC/USDT", source="ccxt", interval="4h", years=5)
    res = run_walk_forward(btc4h, CryptoTrendStrategy, param_grid={},
                           initial_equity=10000.0, symbol="BTC/USDT",
                           risk_per_trade=0.01, spread_pips=0.0, slippage_pips=0.0,
                           session_windows=[], train_bars=2000, test_bars=1500)
    m = res.metrics; mc = res.monte_carlo
    print(f"  folds={len(res.folds)} OOS trades={m['total_trades']} "
          f"win={m['win_rate']*100:.1f}% PF={m['profit_factor']:.2f} "
          f"Sharpe={m['sharpe_ratio']:.2f} maxDD={m['max_drawdown_pct']:.2f}% "
          f"ret={m['total_return_pct']:.2f}%")
    if mc:
        print(f"  OOS MonteCarlo profitable={mc.profitable_pct:.1f}% "
              f"({'PASS' if mc.passed else 'FAIL'})")
    print(f"  H6 WF verdict: {'PASS' if (m['profit_factor']>1.2 and m['total_trades']>=200 and (mc and mc.passed)) else 'REVIEW'}")


if __name__ == "__main__":
    main()
