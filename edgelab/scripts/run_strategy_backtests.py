"""Run the three documented strategies (and optional combination) through the
strategy-aware backtester and apply the validation bar.

- In-sample: first 80% of data. Out-of-sample: last 20%.
- Walk-forward: 1y train / 3m test, rolled 3m forward (~16 windows).
- Validation bar (from brief / constitution validation_bar):
    200+ trades, profit factor > 1.2, max DD < 5%, Sharpe > 0.5, OOS required.
- If all three fail -> run combination strategy and apply the same bar.

Outputs a printed report. No strategy source modified.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from edgelab.backtest.strategy_runner import run_strategy_backtest  # noqa: E402
from edgelab.config import Config  # noqa: E402
from edgelab.data.loader import load_csv, validate_dataframe  # noqa: E402
from edgelab.strategy.combination import CombinationStrategy  # noqa: E402
from edgelab.strategy.session_expansion import SessionExpansionStrategy  # noqa: E402
from edgelab.strategy.structure_pullback import StructurePullbackStrategy  # noqa: E402
from edgelab.strategy.turtle import TurtleStrategy  # noqa: E402

DATA_CSV = ROOT / "data" / "EURUSD_H1_5y.csv"
INITIAL_EQUITY = 10000.0
SYMBOL = "EURUSD"
SPREAD = 0.8
SLIPPAGE = 0.5

# NY session windows: Turtle/structure use the overlap; session-expansion has its own.
OVERLAP_WINDOWS = [[8, 0, 11, 0]]
SESSION_WINDOWS = [[3, 0, 6, 0], [8, 0, 11, 0]]


def _load() -> pd.DataFrame:
    df = load_csv(DATA_CSV)
    validate_dataframe(df)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.set_index("timestamp").sort_index()
    return df[["open", "high", "low", "close", "volume"]]


def _new_strategy(name: str):
    if name == "turtle":
        return TurtleStrategy()
    if name == "structure":
        return StructurePullbackStrategy()
    if name == "session":
        return SessionExpansionStrategy()
    if name == "combination":
        return CombinationStrategy()
    raise ValueError(name)


def _session_windows(name: str):
    # Turtle (Strategy 1) has NO session filter per spec -> None disables the
    # RiskEngine session gate entirely. Structure uses the London/NY overlap.
    # Session-expansion defines its own windows internally. Combination uses overlap.
    if name == "turtle":
        return None
    if name == "structure":
        return OVERLAP_WINDOWS
    if name == "session":
        return SESSION_WINDOWS
    if name == "combination":
        return OVERLAP_WINDOWS
    return None


def _risk(name: str) -> float:
    return 0.01 if name in ("turtle", "structure") else 0.005 if name == "session" else 0.005


def _validate(metrics: dict, n_trades: int) -> bool:
    return (
        n_trades >= 200
        and metrics["profit_factor"] is not None
        and metrics["profit_factor"] > 1.2
        and metrics["max_drawdown_pct"] < 5.0
        and metrics["sharpe_ratio"] > 0.5
    )


def _run_one(name: str, df: pd.DataFrame) -> dict:
    strat = _new_strategy(name)
    res = run_strategy_backtest(
        df,
        strat,
        initial_equity=INITIAL_EQUITY,
        symbol=SYMBOL,
        session_windows=_session_windows(name),
        risk_per_trade=_risk(name),
        spread_pips=SPREAD,
        slippage_pips=SLIPPAGE,
    )
    m = dict(res.metrics)
    m["_trades"] = len(res.trades)
    return m


def _walk_forward(name: str, df: pd.DataFrame) -> dict:
    """1y train / 3m test, rolled 3m. Returns profitable-window fraction + avg return."""
    start = df.index[0]
    # monthly chunks
    months = df.resample("MS").first().index
    windows = []
    train_months = 12
    test_months = 3
    step_months = 3
    i = 0
    while i + train_months + test_months <= len(months):
        train_start = months[i]
        train_end = months[i + train_months]
        test_start = train_end
        test_end = months[i + train_months + test_months]
        train = df.loc[train_start:train_end]
        test = df.loc[test_start:test_end]
        if len(train) > 250 and len(test) > 50:
            try:
                m = _run_one(name, test)
                windows.append(m["total_return_pct"])
            except Exception:
                windows.append(0.0)
        i += step_months
    if not windows:
        return {"wf_profitable_pct": 0.0, "wf_avg_return": 0.0, "wf_windows": 0}
    prof = sum(1 for r in windows if r > 0) / len(windows)
    return {
        "wf_profitable_pct": prof * 100,
        "wf_avg_return": sum(windows) / len(windows),
        "wf_windows": len(windows),
    }


def main() -> None:
    df = _load()
    n_total = len(df)
    split = int(n_total * 0.8)
    is_df = df.iloc[:split]
    oos_df = df.iloc[split:]

    print("=== STRATEGY BACKTEST RESULTS ===")
    print(f"Data: {DATA_CSV}")
    print(f"Period: {df.index[0]} to {df.index[-1]}  Total bars: {n_total}")
    print(f"In-sample period: {is_df.index[0]} to {is_df.index[-1]}")
    print(f"Out-of-sample period: {oos_df.index[0]} to {oos_df.index[-1]}")

    results = {}
    for name in ("turtle", "structure", "session"):
        label = {
            "turtle": "Strategy 1: Modernized Turtle",
            "structure": "Strategy 2: HTF Structure + LTF Trigger",
            "session": "Strategy 3: Session Volatility Expansion",
        }[name]
        is_m = _run_one(name, is_df)
        oos_m = _run_one(name, oos_df)
        wf = _walk_forward(name, df)
        is_pass = _validate(is_m, is_m["_trades"])
        oos_pass = _validate(oos_m, oos_m["_trades"])
        passed = is_pass and oos_pass
        results[name] = {
            "label": label,
            "is": is_m,
            "oos": oos_m,
            "wf": wf,
            "passed": passed,
        }
        print(f"\n--- {label} ---")
        print(f"  [In-sample]  trades={is_m['_trades']} win={is_m['win_rate']*100:.1f}% "
              f"PF={is_m['profit_factor']:.2f} Sharpe={is_m['sharpe_ratio']:.2f} "
              f"maxDD={is_m['max_drawdown_pct']:.2f}% ret={is_m['total_return_pct']:.2f}% "
              f"R:R={is_m['avg_rr']:.2f} hold={is_m['avg_holding_bars']:.1f}")
        print(f"  [Out-of-sample] trades={oos_m['_trades']} win={oos_m['win_rate']*100:.1f}% "
              f"PF={oos_m['profit_factor']:.2f} Sharpe={oos_m['sharpe_ratio']:.2f} "
              f"maxDD={oos_m['max_drawdown_pct']:.2f}% ret={oos_m['total_return_pct']:.2f}%")
        print(f"  [Walk-forward] profitable windows={wf['wf_profitable_pct']:.1f}% "
              f"avg return/window={wf['wf_avg_return']:.2f}% windows={wf['wf_windows']}")
        print(f"  Validation (IS & OOS): {'PASS' if passed else 'FAIL'} "
              f"(IS={'PASS' if is_pass else 'FAIL'}, OOS={'PASS' if oos_pass else 'FAIL'})")

    any_passed = any(r["passed"] for r in results.values())
    print("\n=== FINAL DECISION ===")
    if any_passed:
        winners = [r["label"] for r in results.values() if r["passed"]]
        print(f"PASS: {', '.join(winners)}")
        print("Recommendation: proceed to forward testing on demo per constitution.")
        return

    print("ALL THREE DOCUMENTED STRATEGIES FAILED VALIDATION.")
    print("Proceeding to Phase H: combination strategy (mandatory fallback).")
    name = "combination"
    label = "Combination Strategy (Phase H fallback)"
    is_m = _run_one(name, is_df)
    oos_m = _run_one(name, oos_df)
    wf = _walk_forward(name, df)
    is_pass = _validate(is_m, is_m["_trades"])
    oos_pass = _validate(oos_m, oos_m["_trades"])
    passed = is_pass and oos_pass
    print(f"\n--- {label} ---")
    print(f"  [In-sample]  trades={is_m['_trades']} win={is_m['win_rate']*100:.1f}% "
          f"PF={is_m['profit_factor']:.2f} Sharpe={is_m['sharpe_ratio']:.2f} "
          f"maxDD={is_m['max_drawdown_pct']:.2f}% ret={is_m['total_return_pct']:.2f}%")
    print(f"  [Out-of-sample] trades={oos_m['_trades']} win={oos_m['win_rate']*100:.1f}% "
          f"PF={oos_m['profit_factor']:.2f} Sharpe={oos_m['sharpe_ratio']:.2f} "
          f"maxDD={oos_m['max_drawdown_pct']:.2f}% ret={oos_m['total_return_pct']:.2f}%")
    print(f"  [Walk-forward] profitable windows={wf['wf_profitable_pct']:.1f}% "
          f"avg return/window={wf['wf_avg_return']:.2f}% windows={wf['wf_windows']}")
    print(f"  Validation (IS & OOS): {'PASS' if passed else 'FAIL'}")
    if passed:
        print("Recommendation: combination strategy is the fallback winner. Proceed to demo.")
    else:
        print("NO STRATEGY from the documented-trader library has an edge on this EURUSD data.")
        print("Project should be killed or restarted with different parameters.")


if __name__ == "__main__":
    main()
