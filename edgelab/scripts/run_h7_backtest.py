"""Run hypothesis H7 (G10 FX carry) through the honest basket simulator + Monte
Carlo, with the SAME validation bar as H5 (PF>1.2, Sharpe>0.5, MC>=70% profitable,
<4% DD budget at portfolio level). Reports the carry-proxy caveat and the
correlation to H5 equity momentum so the diversification claim is checkable.

No tuning. Hypothesis written before running (H7_HYPOTHESIS.md).
New helper; no repo module modified.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from edgelab.backtest.monte_carlo import run_monte_carlo
from edgelab.data.market_feed import MarketDataFeed
from edgelab.strategy.fx_carry import run_h7, UNIVERSE
from edgelab.strategy.equity_xsmom import run_h5, UNIVERSE as EQ_UNIVERSE


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


def monthly_returns_from_trades(trades, equity_curve):
    """Reconstruct a monthly return series from the equity curve for correlation."""
    eq = pd.Series({d: e for d, e in equity_curve})
    eq = eq.sort_index()
    m = eq.resample("ME").last().ffill()
    return m.pct_change().dropna()


def main():
    feed = MarketDataFeed()

    # ---------- H7: G10 FX carry ----------
    print("=== H7: G10 FX Carry (monthly, 12M carry proxy) ===")
    prices = {}
    for s in UNIVERSE:
        try:
            prices[s] = feed.get(s, source="yfinance", interval="1d", years=2)
        except Exception as e:  # noqa: BLE001
            print(f"  skip {s}: {e}")
    if not prices:
        print("  No FX data fetched; H7 not run.")
        return
    min_len = min(len(v) for v in prices.values())
    print(f"  universe: {len(prices)} pairs, min bars={min_len}")
    trades, eq, m = run_h7(prices, initial_equity=10000.0, top_n=3)
    print_res("FULL", m, trades)
    h7_pass = (m["profit_factor"] > 1.2 and m["sharpe_ratio"] > 0.5
               and m["max_drawdown_pct"] < 4.0)
    mc = mc_block([t.pnl for t in trades])
    mc_pass = bool(mc and mc.passed)
    print(f"  H7 bar: {'PASS' if (h7_pass and mc_pass) else 'FAIL'} "
          f"(PF={m['profit_factor']:.2f} Sharpe={m['sharpe_ratio']:.2f} "
          f"DD={m['max_drawdown_pct']:.2f}% MC={'PASS' if mc_pass else 'FAIL'})")
    if not (h7_pass and mc_pass):
        print("  => H7 RETIRED per RESEARCH_PROTOCOL if it fails the bar. Draft H8.")
        print("     NOTE: signal is a 12M price-return carry PROXY; a policy-rate")
        print("           time series (FRED/Datastream) is the honest upgrade path.")
        return

    # ---------- diversification check vs H5 equity momentum ----------
    print("\n=== Diversification vs H5 (equity cross-sectional momentum) ===")
    eq_prices = {}
    for s in EQ_UNIVERSE:
        try:
            eq_prices[s] = feed.get(s, source="yfinance", interval="1d", years=2)
        except Exception:
            pass
    if eq_prices:
        _, eq_eq, _ = run_h5(eq_prices, initial_equity=10000.0, top_n=3)
        h7_ret = monthly_returns_from_trades(trades, eq)
        h5_ret = monthly_returns_from_trades([], eq_eq)
        joined = pd.concat([h7_ret.rename("H7"), h5_ret.rename("H5")], axis=1).dropna()
        if len(joined) > 5:
            rho = joined["H7"].corr(joined["H5"])
            print(f"  monthly return corr(H7, H5) = {rho:.3f} "
                  f"({'UNCORRELATED' if abs(rho) < 0.5 else 'CORRELATED'})")
        else:
            print("  insufficient overlap to compute correlation")


if __name__ == "__main__":
    main()
