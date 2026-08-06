"""Track 1: validate H5 (equity cross-sectional momentum) on the FULL 5-year bar.

Honest re-validation per RESEARCH_PROTOCOL_v1 (the 5y minimum H5 was never tested
against — only ~2y). Reports:
  - FULL 5y sample metrics
  - IS (first 4y) / OOS (last 1y) split through the honest bar + new OOS trade gate
  - Broadened universe test (adds bonds TLT/IEF for diversification; kept only if
    edge is NOT diluted)
  - Comparison vs the prior 2y result (PF 1.39)
No tuning. No live orders. Dry backtest only.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from edgelab.backtest.monte_carlo import run_monte_carlo
from edgelab.data.market_feed import MarketDataFeed
from edgelab.strategy.equity_xsmom import run_h5, current_signal, UNIVERSE

OOS_MIN_TRADES = 30


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


def bar_pass(m, oos_trades):
    base = (m["profit_factor"] > 1.2 and m["sharpe_ratio"] > 0.5
            and m["max_drawdown_pct"] < 4.0)
    gate = oos_trades >= OOS_MIN_TRADES
    return base and gate, base, gate


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

    min_len = min(len(v) for v in prices.values())
    years = (prices[UNIVERSE[0]].index[-1] - prices[UNIVERSE[0]].index[0]).days / 365.25
    print(f"=== H5 validation: {len(prices)} symbols, min bars={min_len}, span={years:.2f}y ===")

    # FULL 5y
    tr, eq, m = run_h5(prices, initial_equity=10000.0, top_n=3)
    print_res("FULL 5y", m, tr)
    full_pass, _, _ = bar_pass(m, m["total_trades"])

    # IS/OOS split: first 4y / last 1y (by bar count)
    split = int(min_len * 0.8)
    is_prices = {s: df.iloc[:split] for s, df in prices.items()}
    oos_prices = {s: df.iloc[split:] for s, df in prices.items()}
    is_tr, is_eq, is_m = run_h5(is_prices, initial_equity=10000.0, top_n=3)
    print_res("IS (4y)", is_m, is_tr)
    oos_tr, oos_eq, oos_m = run_h5(oos_prices, initial_equity=10000.0, top_n=3)
    print_res("OOS (1y)", oos_m, oos_tr)
    oos_pass, oos_base, oos_gate = bar_pass(oos_m, oos_m["total_trades"])

    print(f"\n  H5 FULL 5y bar: {'PASS' if full_pass else 'FAIL'}")
    print(f"  H5 OOS 1y bar: {'PASS' if oos_pass else 'FAIL'} "
          f"(PF={oos_m['profit_factor']:.2f} Sharpe={oos_m['sharpe_ratio']:.2f} "
          f"DD={oos_m['max_drawdown_pct']:.2f}% trades={oos_m['total_trades']} "
          f"OOS-gate={'PASS' if oos_gate else 'FAIL'})")
    print(f"  vs prior 2y result: PF 1.39. 5y PF = {m['profit_factor']:.2f}.")

    # Broadened universe: add bonds for diversification (kept only if edge holds)
    print("\n=== Broadened universe (H5 + bonds TLT/IEF) ===")
    broad = dict(prices)
    for b in ["TLT", "IEF"]:
        try:
            broad[b] = feed.get(b, source="yfinance", interval="1d", years=5)
            print(f"  added {b} bars={len(broad[b])}")
        except Exception as e:
            print(f"  skip {b}: {e}")
    bt, beq, bm = run_h5(broad, initial_equity=10000.0, top_n=3)
    print_res("FULL 5y (broad)", bm, bt)
    bpass, _, _ = bar_pass(bm, bm["total_trades"])
    print(f"  Broadened bar: {'PASS' if bpass else 'FAIL'} "
          f"(PF={bm['profit_factor']:.2f} vs base {m['profit_factor']:.2f})")
    print("  => Broadening kept only if PF holds >= base; else base universe preferred.")

    sig = current_signal(prices)
    print(f"\n  current_signal({sig['as_of']}): {sig['selected']}")


if __name__ == "__main__":
    main()
