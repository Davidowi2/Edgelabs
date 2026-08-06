"""Run hypothesis H9 (Cross-Sectional Momentum on FX + Crypto) through the honest
basket simulator + Monte Carlo, with the SAME bar as H5/H8 PLUS the new OOS
trade-count gate (inert / IS-only strategies cannot pass).

Honest, no tuning. Mirrors run_h8_backtest.py but on two TradeLocker-tradable
universes. Dry backtest only — NO live orders, NO TradeLocker connection.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from edgelab.backtest.monte_carlo import run_monte_carlo
from edgelab.data.market_feed import MarketDataFeed
from edgelab.strategy.h9_xsmom import (run_h9, current_signal, FX_UNIVERSE,
                                         CRYPTO_UNIVERSE)

OOS_MIN_TRADES = 30   # new gate: a strategy must actually trade OOS to qualify


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

    # ---------- H9 FX: G10 cross-sectional momentum (long/short) ----------
    print("=== H9-FX: G10 Cross-Sectional Momentum (long top-3 / short bottom-3) ===")
    fx_prices = {}
    for s in FX_UNIVERSE:
        try:
            fx_prices[s] = feed.get(s, source="yfinance", interval="1d", years=2)
        except Exception as e:  # noqa: BLE001
            print(f"  skip {s}: {e}")
    if fx_prices:
        min_len = min(len(v) for v in fx_prices.values())
        print(f"  universe: {len(fx_prices)} pairs, min bars={min_len}")
        sig = current_signal(fx_prices)
        print(f"  current_signal({sig['as_of']}): longs {sig['longs']} / shorts {sig['shorts']}")
        tr, eq, m = run_h9(fx_prices, initial_equity=10000.0, top_n=3, long_short=True)
        print_res("FULL", m, tr)
        fx_pass, fx_base, fx_gate = bar_pass(m, m["total_trades"])
        print(f"  H9-FX bar: {'PASS' if fx_pass else 'FAIL'} "
              f"(PF={m['profit_factor']:.2f} Sharpe={m['sharpe_ratio']:.2f} "
              f"DD={m['max_drawdown_pct']:.2f}% trades={m['total_trades']} "
              f"OOS-gate={'PASS' if fx_gate else 'FAIL'})")
        if not fx_pass:
            print("  => H9-FX did NOT clear the bar per RESEARCH_PROTOCOL_v1. Honest outcome.")
    else:
        print("  No FX data; H9-FX not run.")

    # ---------- H9 Crypto: top-10 cross-sectional momentum (long-only) ----------
    print("\n=== H9-Crypto: Top-10 Cross-Sectional Momentum (long top-3) ===")
    cx_prices = {}
    for s in CRYPTO_UNIVERSE:
        try:
            cx_prices[s] = feed.get(s, source="ccxt", interval="1d", years=3)
        except Exception as e:  # noqa: BLE001
            print(f"  skip {s}: {e}")
    if cx_prices:
        min_len = min(len(v) for v in cx_prices.values())
        print(f"  universe: {len(cx_prices)} coins, min bars={min_len}")
        sig = current_signal(cx_prices)
        print(f"  current_signal({sig['as_of']}): longs {sig['longs']}")
        tr, eq, m = run_h9(cx_prices, initial_equity=10000.0, top_n=3, long_short=False)
        print_res("FULL", m, tr)
        cx_pass, cx_base, cx_gate = bar_pass(m, m["total_trades"])
        print(f"  H9-Crypto bar: {'PASS' if cx_pass else 'FAIL'} "
              f"(PF={m['profit_factor']:.2f} Sharpe={m['sharpe_ratio']:.2f} "
              f"DD={m['max_drawdown_pct']:.2f}% trades={m['total_trades']} "
              f"OOS-gate={'PASS' if cx_gate else 'FAIL'})")
        if not cx_pass:
            print("  => H9-Crypto did NOT clear the bar per RESEARCH_PROTOCOL_v1. Honest outcome.")
    else:
        print("  No crypto data; H9-Crypto not run.")


if __name__ == "__main__":
    main()
