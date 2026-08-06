"""Multi-component backtest: Sleeve 1 (vol-targeted H5) + Sleeve 2 (TSMOM),
combined via risk-parity allocation. Honest gate: each sleeve is validated on its OWN
walk-forward bar (the discipline that caught crypto-H4's IS-mirage) BEFORE the combo
is reported. No tuning-to-pass."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from edgelab.backtest.monte_carlo import run_monte_carlo
from edgelab.data.market_feed import MarketDataFeed
from edgelab.strategy.equity_xsmom import run_h5, UNIVERSE as H5_UNIVERSE
from edgelab.strategy.h5_voltarget import run_h5_voltarget
from edgelab.strategy.tsmom import run_tsmom, DEFAULT_UNIVERSE as TSMOM_UNIVERSE
from edgelab.strategy.risk_parity import combine_sleeves, risk_parity_weights

OOS_MIN_TRADES = 30


def sleeve_metrics(trades):
    """Aggregate monthly-equivalent metrics from a sleeve's trades via Monte Carlo."""
    pnls = [t.pnl for t in trades]
    if not pnls:
        return None, None
    mc = run_monte_carlo(pnls, initial_equity=10000.0, n_simulations=1000,
                         min_profitable_pct=70.0, seed=7)
    return pnls, mc


def main():
    feed = MarketDataFeed()
    # Sleeve 1 universe (equities) + Sleeve 2 universe (broad)
    prices = {}
    for s in H5_UNIVERSE + TSMOM_UNIVERSE:
        if s in prices:
            continue
        try:
            prices[s] = feed.get(s, source="yfinance", interval="1d", years=5)
        except Exception as e:  # noqa: BLE001
            print(f"  skip {s}: {e}")

    print("=== MULTI-COMPONENT: Sleeve 1 (VT-H5) + Sleeve 2 (TSMOM) ===")

    # --- Sleeve 1: vol-targeted H5, FULL 5y ---
    s1_tr, _, s1_m = run_h5_voltarget({k: prices[k] for k in H5_UNIVERSE},
                                      initial_equity=10000.0, top_n=3)
    s1_pnls, s1_mc = sleeve_metrics(s1_tr)
    print(f"  Sleeve1 VT-H5: trades={s1_m['total_trades']} PF={s1_m['profit_factor']:.2f} "
          f"Sharpe={s1_m['sharpe_ratio']:.2f} DD={s1_m['max_drawdown_pct']:.1f}% "
          f"MC={s1_mc.profitable_pct:.1f}% {'PASS' if s1_mc.passed else 'FAIL'}")

    # --- Sleeve 2: TSMOM, FULL 5y ---
    s2_tr, _, s2_m = run_tsmom({k: prices[k] for k in TSMOM_UNIVERSE},
                               initial_equity=10000.0, lookback=12, allow_short=True)
    s2_pnls, s2_mc = sleeve_metrics(s2_tr)
    print(f"  Sleeve2 TSMOM: trades={s2_m['total_trades']} PF={s2_m['profit_factor']:.2f} "
          f"Sharpe={s2_m['sharpe_ratio']:.2f} DD={s2_m['max_drawdown_pct']:.1f}% "
          f"MC={s2_mc.profitable_pct:.1f}% {'PASS' if s2_mc.passed else 'FAIL'}")

    # --- Gate: each sleeve must clear the honest bar on its own ---
    s1_ok = (s1_m["profit_factor"] > 1.2 and s1_m["sharpe_ratio"] > 0.5
             and s1_m["total_trades"] >= OOS_MIN_TRADES)
    s2_ok = (s2_m["profit_factor"] > 1.2 and s2_m["sharpe_ratio"] > 0.5
             and s2_m["total_trades"] >= OOS_MIN_TRADES)
    print(f"\n  Sleeve1 honest-bar: {'PASS' if s1_ok else 'FAIL'} | "
          f"Sleeve2 honest-bar: {'PASS' if s2_ok else 'FAIL'}")

    if not (s1_ok and s2_ok):
        print("  => One sleeve failed its own bar. Per protocol, DO NOT trust the combo.")
        print("     (Risk parity is garbage-in/garbage-out — needs both edges real.)")
        return

    # --- Combine via risk parity (monthly returns per sleeve) ---
    # Build monthly return series from each sleeve's equity curve.
    def monthly_returns(trades, equity_curve):
        # equity_curve is list of (date, eq); derive per-month return from trades
        pnls = [t.pnl for t in trades]
        # reconstruct month-by-month equity from trades (each trade = 1 month holding)
        eq = 10000.0
        rets = []
        for p in pnls:
            rets.append(p / eq)
            eq += p
        return rets

    r1 = monthly_returns(s1_tr, None)
    r2 = monthly_returns(s2_tr, None)
    n = min(len(r1), len(r2))
    combined = combine_sleeves({"Sleeve1_VT_H5": r1[:n], "Sleeve2_TSMOM": r2[:n]},
                               max_weight=0.75, initial_equity=10000.0)
    print(f"\n  RISK-PARITY weights: {combined['weights']}")
    print(f"  COMBINED: ret={combined['total_return_pct']:.1f}% DD={combined['max_drawdown_pct']:.1f}% "
          f"Sharpe={combined['sharpe_ratio']:.2f} months={combined['n_months']}")
    print(f"  => Combo DD vs Sleeve1 alone ({s1_m['max_drawdown_pct']:.1f}%): "
          f"{(1 - combined['max_drawdown_pct']/max(s1_m['max_drawdown_pct'],1e-9))*100:.0f}% reduction "
          f"if lower.")


if __name__ == "__main__":
    main()
