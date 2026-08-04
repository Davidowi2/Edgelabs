"""Backtest Strategy 2 (XAUUSD H4) through the canonical runner + Monte Carlo.

Honest, no tuning: runs the DOCUMENTED Strategy 2 rules on the REAL live
candidate instrument (XAUUSD H4). Reports IS/OOS metrics + Monte Carlo
profitability per RESEARCH_PROTOCOL. New helper script; no repo module modified.

NOTE on data: free Yahoo H4 history is capped at ~730 days, so we have ~2y,
not the 5y the validation bar wants. We report the shortfall honestly and do
NOT claim the 5-year bar is met.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from edgelab.backtest.canonical import run_canonical_backtest
from edgelab.backtest.monte_carlo import run_monte_carlo
from edgelab.strategy.structure_pullback_h4 import StructurePullbackH4Strategy
from edgelab.config import Config

DATA = ROOT / "data" / "XAUUSD_H4_raw.csv"
SYMBOL = "XAUUSD"
SPREAD = 2.5      # XAUUSD spread per ARCHITECTURE (2.5 pips)
SLIPPAGE = 1.0
RISK = 0.01
MIN_YEARS = 5


def load():
    df = pd.read_csv(DATA)
    df = df.rename(columns={"Datetime": "timestamp"})
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True).dt.tz_convert("America/New_York")
    df = df.set_index("timestamp").sort_index()
    return df[["open", "high", "low", "close", "volume"]]


def report(name, m, trades):
    print(f"\n--- {name} ---")
    print(f"  trades={m['total_trades']} win={m['win_rate']*100:.1f}% "
          f"PF={m['profit_factor']:.2f} Sharpe={m['sharpe_ratio']:.2f} "
          f"maxDD={m['max_drawdown_pct']:.2f}% ret={m['total_return_pct']:.2f}% "
          f"R:R={m['avg_rr']:.2f} hold={m['avg_holding_bars']:.1f}")
    if trades:
        pnls = [t.pnl for t in trades]
        mc = run_monte_carlo(pnls, initial_equity=10000.0, n_simulations=1000,
                             min_profitable_pct=70.0, seed=7)
        print(f"  [MonteCarlo n=1000] profitable={mc.profitable_pct:.1f}% "
              f"(bar 70%) -> {'PASS' if mc.passed else 'FAIL'} | "
              f"median_ret={mc.median_return_pct:.1f}% p5={mc.p5_return_pct:.1f}% "
              f"p95={mc.p95_return_pct:.1f}% maxDD_med={mc.max_drawdown_pct_median:.1f}%")


def main():
    df = load()
    print(f"Data: {DATA}")
    print(f"Period: {df.index[0]} -> {df.index[-1]}  Bars: {len(df)}  "
          f"Span(y): {(df.index[-1]-df.index[0]).days/365.25:.2f} "
          f"(validation wants >= {MIN_YEARS})")
    if (df.index[-1] - df.index[0]).days / 365.25 < MIN_YEARS:
        print("  !! HONEST FLAG: free H4 history < 5y. 5-year validation bar NOT met by data.")

    split = int(len(df) * 0.8)
    is_df = df.iloc[:split]
    oos_df = df.iloc[split:]

    print("\n=== Strategy 2: Structure Pullback (XAUUSD H4, documented rules) ===")
    is_res = run_canonical_backtest(is_df, StructurePullbackH4Strategy(),
                                    initial_equity=10000.0, symbol=SYMBOL,
                                    risk_per_trade=RISK, spread_pips=SPREAD,
                                    slippage_pips=SLIPPAGE, session_windows=[[8, 0, 11, 0]])
    report(f"In-sample ({is_df.index[0].date()}..{is_df.index[-1].date()})", is_res.metrics, is_res.trades)

    oos_res = run_canonical_backtest(oos_df, StructurePullbackH4Strategy(),
                                     initial_equity=10000.0, symbol=SYMBOL,
                                     risk_per_trade=RISK, spread_pips=SPREAD,
                                     slippage_pips=SLIPPAGE, session_windows=[[8, 0, 11, 0]])
    report(f"Out-of-sample ({oos_df.index[0].date()}..{oos_df.index[-1].date()})", oos_res.metrics, oos_res.trades)

    # full-sample MC for a stability read
    full = run_canonical_backtest(df, StructurePullbackH4Strategy(),
                                  initial_equity=10000.0, symbol=SYMBOL,
                                  risk_per_trade=RISK, spread_pips=SPREAD,
                                  slippage_pips=SLIPPAGE, session_windows=[[8, 0, 11, 0]])
    report("Full-sample", full.metrics, full.trades)

    print("\n=== HONEST VERDICT ===")
    is_pass = (is_res.metrics["total_trades"] >= 200 and
               is_res.metrics["profit_factor"] > 1.2 and
               is_res.metrics["max_drawdown_pct"] < 5.0 and
               is_res.metrics["sharpe_ratio"] > 0.5)
    oos_pass = (oos_res.metrics["total_trades"] >= 200 and
                oos_res.metrics["profit_factor"] > 1.2 and
                oos_res.metrics["max_drawdown_pct"] < 5.0 and
                oos_res.metrics["sharpe_ratio"] > 0.5)
    print(f"  IS validation bar (PF>1.2, DD<5%, Sharpe>0.5, 200 trades): "
          f"{'PASS' if is_pass else 'FAIL'} (trades={is_res.metrics['total_trades']})")
    print(f"  OOS validation bar: {'PASS' if oos_pass else 'FAIL'} "
          f"(trades={oos_res.metrics['total_trades']})")
    if not oos_pass:
        print("  => By the repo's OWN bar, Strategy 2 (XAUUSD H4) does NOT yet qualify")
        print("     for forward testing. Per RESEARCH_PROTOCOL, retire or revisit with")
        print("     new evidence. The data-length shortfall (2y vs 5y) also stands.")


if __name__ == "__main__":
    main()
