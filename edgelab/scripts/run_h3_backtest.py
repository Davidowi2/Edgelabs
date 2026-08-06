"""Backtest Hypothesis H3 (XAUUSD H4, trend-filter bias redefinition) through the
canonical runner + MC. Honest, no tuning. Mirrors run_h2_backtest.py but uses
StructurePullbackH4H3Strategy. New helper; no module modified."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from edgelab.backtest.canonical import run_canonical_backtest
from edgelab.backtest.monte_carlo import run_monte_carlo
from edgelab.strategy.structure_pullback_h4_h3 import StructurePullbackH4H3Strategy

DATA = ROOT / "data" / "XAUUSD_H4_raw.csv"
SYMBOL = "XAUUSD"
SPREAD = 2.5
SLIPPAGE = 1.0
RISK = 0.01


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
    print(f"Data: {DATA}  Period {df.index[0]}..{df.index[-1]}  Bars {len(df)}  "
          f"Span(y) {(df.index[-1]-df.index[0]).days/365.25:.2f} (wants >=5)")
    if (df.index[-1] - df.index[0]).days / 365.25 < 5:
        print("  !! HONEST FLAG: 2y data only; 5y validation bar NOT met by data.")
    split = int(len(df) * 0.8)
    is_df, oos_df = df.iloc[:split], df.iloc[split:]

    print("\n=== H3: Structure Pullback (XAUUSD H4, trend-filter bias) ===")
    is_res = run_canonical_backtest(is_df, StructurePullbackH4H3Strategy(),
                                     initial_equity=10000.0, symbol=SYMBOL,
                                     risk_per_trade=RISK, spread_pips=SPREAD,
                                     slippage_pips=SLIPPAGE, session_windows=[[8, 0, 11, 0]])
    report(f"In-sample ({is_df.index[0].date()}..{is_df.index[-1].date()})", is_res.metrics, is_res.trades)
    oos_res = run_canonical_backtest(oos_df, StructurePullbackH4H3Strategy(),
                                      initial_equity=10000.0, symbol=SYMBOL,
                                      risk_per_trade=RISK, spread_pips=SPREAD,
                                      slippage_pips=SLIPPAGE, session_windows=[[8, 0, 11, 0]])
    report(f"Out-of-sample ({oos_df.index[0].date()}..{oos_df.index[-1].date()})", oos_res.metrics, oos_res.trades)
    full = run_canonical_backtest(df, StructurePullbackH4H3Strategy(),
                                  initial_equity=10000.0, symbol=SYMBOL,
                                  risk_per_trade=RISK, spread_pips=SPREAD,
                                  slippage_pips=SLIPPAGE, session_windows=[[8, 0, 11, 0]])
    report("Full-sample", full.metrics, full.trades)

    print("\n=== HONEST VERDICT (H3) ===")
    oos_pass = (oos_res.metrics["total_trades"] >= 200 and
                oos_res.metrics["profit_factor"] > 1.2 and
                oos_res.metrics["max_drawdown_pct"] < 5.0 and
                oos_res.metrics["sharpe_ratio"] > 0.5)
    print(f"  OOS validation bar: {'PASS' if oos_pass else 'FAIL'} "
          f"(trades={oos_res.metrics['total_trades']}, PF={oos_res.metrics['profit_factor']:.2f})")
    if not oos_pass:
        print("  => Per RESEARCH_PROTOCOL, H3 is RETIRED (or revisited with new evidence).")
        print("     No in-place tuning. Note 2y data constraint stands.")


if __name__ == "__main__":
    main()
