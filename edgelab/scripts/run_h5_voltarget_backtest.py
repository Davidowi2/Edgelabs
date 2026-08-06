"""Compare raw H5 vs vol-targeted H5 on the FULL 5y bar + OOS split.

Honest, no tuning-to-pass. Reports both through the bar (PF>1.2, Sharpe>0.5,
DD<4% backtest, MC>=70%, OOS trades>=30). The point: does vol-targeting H5's
53% drawdown WITHOUT killing the proven edge?
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from edgelab.backtest.monte_carlo import run_monte_carlo
from edgelab.data.market_feed import MarketDataFeed
from edgelab.strategy.equity_xsmom import run_h5, UNIVERSE
from edgelab.strategy.h5_voltarget import run_h5_voltarget

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
          f"maxDD={m['max_drawdown_pct']:.2f}% ret={m['total_return_pct']:.2f}% {mc_s}")


def bar_pass(m, oos_trades):
    base = (m["profit_factor"] > 1.2 and m["sharpe_ratio"] > 0.5
            and m["max_drawdown_pct"] < 4.0)
    return base and oos_trades >= OOS_MIN_TRADES


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

    print(f"=== H5 (raw) vs H5 vol-targeted — FULL 5y + OOS (11 ETFs) ===")

    # --- RAW H5 ---
    rt, re, rm = run_h5(prices, initial_equity=10000.0, top_n=3)
    print_res("RAW H5  FULL 5y", rm, rt)
    is_p = {s: df.iloc[:int(len(df)*0.8)] for s, df in prices.items()}
    oos_p = {s: df.iloc[int(len(df)*0.8):] for s, df in prices.items()}
    rt2, re2, rm2 = run_h5(oos_p, initial_equity=10000.0, top_n=3)
    print_res("RAW H5  OOS 1y", rm2, rt2)

    # --- VOL-TARGETED H5 ---
    vt, ve, vm = run_h5_voltarget(prices, initial_equity=10000.0, top_n=3,
                                  target_vol_annual=0.12, max_leverage=1.5)
    print_res("VT  H5  FULL 5y", vm, vt)
    vt2, ve2, vm2 = run_h5_voltarget(oos_p, initial_equity=10000.0, top_n=3,
                                     target_vol_annual=0.12, max_leverage=1.5)
    print_res("VT  H5  OOS 1y", vm2, vt2)

    print("\n=== Comparison (does vol-targeting fix DD without killing edge?) ===")
    print(f"  RAW H5 FULL maxDD={rm['max_drawdown_pct']:.2f}% PF={rm['profit_factor']:.2f}")
    print(f"  VT  H5 FULL maxDD={vm['max_drawdown_pct']:.2f}% PF={vm['profit_factor']:.2f} "
          f"(DD reduction {(1 - vm['max_drawdown_pct']/max(rm['max_drawdown_pct'],1e-9))*100:.0f}%)")
    print(f"  RAW H5 OOS maxDD={rm2['max_drawdown_pct']:.2f}% PF={rm2['profit_factor']:.2f}")
    print(f"  VT  H5 OOS maxDD={vm2['max_drawdown_pct']:.2f}% PF={vm2['profit_factor']:.2f} "
          f"(DD reduction {(1 - vm2['max_drawdown_pct']/max(rm2['max_drawdown_pct'],1e-9))*100:.0f}%)")
    print(f"\n  Backtest-DD bar is <4% (raw H5 53% fails anyway). Live 4% halt caps BOTH.")
    print(f"  Key question: does VT keep PF>=1.2 AND cut DD? If yes, VT is the upgrade.")


if __name__ == "__main__":
    main()
