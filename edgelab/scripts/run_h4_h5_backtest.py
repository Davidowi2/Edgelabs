"""Run hypotheses H4 (crypto trend) and H5 (equity cross-sectional momentum)
through the honest canonical backtester / basket simulator + Monte Carlo.

No tuning. Each hypothesis was written before running (H4_HYPOTHESIS.md,
H5_HYPOTHESIS.md). Reports IS/OOS (where applicable) + Monte Carlo per the repo
validation bar. New helper; no repo module modified.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from edgelab.backtest.canonical import run_canonical_backtest
from edgelab.backtest.monte_carlo import run_monte_carlo
from edgelab.data.market_feed import MarketDataFeed
from edgelab.strategy.crypto_trend import CryptoTrendStrategy
from edgelab.strategy.equity_xsmom import run_h5, UNIVERSE


def mc_block(pnls):
    if not pnls:
        return None
    return run_monte_carlo(pnls, initial_equity=10000.0, n_simulations=1000,
                           min_profitable_pct=70.0, seed=7)


def print_res(name, m, trades):
    pnls = [t.pnl for t in trades]
    mc = mc_block(pnls)
    mc_s = f"MC={mc.profitable_pct:.1f}% {'PASS' if mc.passed else 'FAIL'}" if mc else "MC=n/a"
    print(f"  {name}: trades={m['total_trades']} win={m['win_rate']*100:.1f}% "
          f"PF={m['profit_factor']:.2f} Sharpe={m['sharpe_ratio']:.2f} "
          f"maxDD={m['max_drawdown_pct']:.2f}% ret={m['total_return_pct']:.2f}% "
          f"RR={m['avg_rr']:.2f} {mc_s}")


def main():
    feed = MarketDataFeed()

    # ---------- H4: crypto trend (BTC/USDT daily) ----------
    print("=== H4: Crypto Trend (BTC/USDT daily) ===")
    btc = feed.get("BTC/USDT", source="ccxt", interval="1d", years=3)
    print(f"  data: {btc.index[0]}..{btc.index[-1]} bars={len(btc)} "
          f"span(y)={(btc.index[-1]-btc.index[0]).days/365.25:.2f} (wants>=5)")
    split = int(len(btc) * 0.8)
    is_r = run_canonical_backtest(btc.iloc[:split], CryptoTrendStrategy(),
                                  initial_equity=10000.0, symbol="BTC/USDT",
                                  risk_per_trade=0.01, spread_pips=0.0,
                                  slippage_pips=0.0, session_windows=[])
    print_res("IS", is_r.metrics, is_r.trades)
    oos_r = run_canonical_backtest(btc.iloc[split:], CryptoTrendStrategy(),
                                   initial_equity=10000.0, symbol="BTC/USDT",
                                   risk_per_trade=0.01, spread_pips=0.0,
                                   slippage_pips=0.0, session_windows=[])
    print_res("OOS", oos_r.metrics, oos_r.trades)
    full_r = run_canonical_backtest(btc, CryptoTrendStrategy(),
                                    initial_equity=10000.0, symbol="BTC/USDT",
                                    risk_per_trade=0.01, spread_pips=0.0,
                                    slippage_pips=0.0, session_windows=[])
    print_res("FULL", full_r.metrics, full_r.trades)
    h4_pass = (oos_r.metrics["profit_factor"] > 1.2 and
               oos_r.metrics["max_drawdown_pct"] < 5.0 and
               oos_r.metrics["sharpe_ratio"] > 0.5)
    print(f"  H4 OOS bar: {'PASS' if h4_pass else 'FAIL'} (PF={oos_r.metrics['profit_factor']:.2f})")
    if not h4_pass:
        print("  => H4 RETIRED per RESEARCH_PROTOCOL if it fails the bar.")
        print("     NOTE: crypto DD on 1% risk per trade may exceed 5% at portfolio level;")
        print("           the bar uses per-trade risk, so we report PF/Sharpe primarily.")

    # ---------- H5: equity cross-sectional momentum ----------
    print("\n=== H5: Equity Cross-Sectional Momentum (monthly) ===")
    prices = {}
    for s in UNIVERSE:
        try:
            prices[s] = feed.get(s, source="yfinance", interval="1d", years=2)
        except Exception as e:  # noqa: BLE001
            print(f"  skip {s}: {e}")
    if prices:
        min_len = min(len(v) for v in prices.values())
        print(f"  universe: {len(prices)} symbols, min bars={min_len}")
        trades, eq, m = run_h5(prices, initial_equity=10000.0, top_n=3)
        print_res("FULL", m, trades)
        h5_pass = (m["profit_factor"] > 1.2 and m["sharpe_ratio"] > 0.5)
        print(f"  H5 bar: {'PASS' if h5_pass else 'FAIL'} (PF={m['profit_factor']:.2f})")
        if not h5_pass:
            print("  => H5 RETIRED per RESEARCH_PROTOCOL if it fails the bar.")
    else:
        print("  No equity data fetched; H5 not run.")


if __name__ == "__main__":
    main()
