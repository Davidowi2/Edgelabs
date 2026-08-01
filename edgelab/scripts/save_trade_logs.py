"""Re-run Strategy 1 (Turtle) and Strategy 3 (Session) backtests and save
enriched per-trade logs to data/strategy1_trades.csv and data/strategy3_trades.csv.

ANALYSIS ONLY. Does not modify any source in edgelab/. Reuses the existing
run_strategy_backtest runner and the strategy classes unchanged.

Output columns:
  trade_id, entry_time, exit_time, direction, entry_price, exit_price,
  pnl_pips, pnl_dollars, exit_reason, session, day_of_week,
  prior_4h_direction, atr_at_entry, holding_bars, sample (IS/OOS)
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from edgelab.backtest.strategy_runner import run_strategy_backtest  # noqa: E402
from edgelab.data.loader import load_csv, validate_dataframe  # noqa: E402
from edgelab.strategy.session_expansion import SessionExpansionStrategy, SESSIONS  # noqa: E402
from edgelab.strategy.turtle import TurtleStrategy  # noqa: E402
from edgelab.strategy.indicators import atr, in_window  # noqa: E402

DATA_CSV = ROOT / "data" / "EURUSD_H1_5y.csv"
INITIAL_EQUITY = 10000.0
SYMBOL = "EURUSD"
SPREAD = 0.8
SLIPPAGE = 0.5
PIP_SIZE = 0.0001

OVERLAP_WINDOWS = [[8, 0, 11, 0]]
SESSION_WINDOWS = [[3, 0, 6, 0], [8, 0, 11, 0]]


def _load():
    df = load_csv(DATA_CSV)
    validate_dataframe(df)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.set_index("timestamp").sort_index()
    return df[["open", "high", "low", "close", "volume"]]


def _session_label(ts) -> str:
    for w in SESSIONS:
        if in_window(ts, w):
            return "LONDON" if w[0] == 3 else "NY"
    return "OTHER"


def _prior_4h_direction(df, i) -> str:
    base = i - 4
    if base < 0:
        return "NA"
    o = float(df["open"].iloc[base])
    c = float(df["close"].iloc[i - 1]) if i - 1 >= 0 else float(df["close"].iloc[i])
    return "BULL" if c > o else "BEAR"


def _enrich(res, df, is_mask, name):
    """Build an enriched trade DataFrame from a run result."""
    # Precompute ATR(20) and index map for fast lookup.
    atr20 = atr(df, 20, ema=True)
    rows = []
    for t in res.trades:
        idx_entry = df.index.get_indexer([t.entry_time])[0]
        idx_exit = df.index.get_indexer([t.exit_time])[0]
        direction = t.direction.upper()
        signed = (t.exit_price - t.entry_price) * (1 if direction == "LONG" else -1)
        pnl_pips = signed / PIP_SIZE
        if name == "session":
            sess = _session_label(t.entry_time)
            prior = _prior_4h_direction(df, idx_entry)
        else:
            sess = "NONE"
            prior = "NA"
        rows.append(
            {
                "trade_id": t.trade_id,
                "entry_time": t.entry_time,
                "exit_time": t.exit_time,
                "direction": direction,
                "entry_price": t.entry_price,
                "exit_price": t.exit_price,
                "pnl_pips": pnl_pips,
                "pnl_dollars": t.pnl,
                "exit_reason": t.exit_reason,
                "session": sess,
                "day_of_week": t.entry_time.strftime("%A"),
                "prior_4h_direction": prior,
                "atr_at_entry": float(atr20.iloc[idx_entry]) if idx_entry >= 0 else float("nan"),
                "holding_bars": max(1, int((t.exit_time - t.entry_time).total_seconds() // 3600)),
                "sample": "IS" if is_mask[idx_entry] else "OOS",
            }
        )
    return pd.DataFrame(rows)


def main():
    df = _load()
    n_total = len(df)
    split = int(n_total * 0.8)
    is_df = df.iloc[:split]
    oos_df = df.iloc[split:]
    is_mask_full = df.index < is_df.index[-1]

    for name, strat_cls, session_windows, risk in [
        ("turtle", TurtleStrategy, None, 0.01),
        ("session", SessionExpansionStrategy, SESSION_WINDOWS, 0.005),
    ]:
        # Fresh strategy instances per sample (stateful strategies retain in_position).
        res_is = run_strategy_backtest(
            is_df, strat_cls(), initial_equity=INITIAL_EQUITY, symbol=SYMBOL,
            session_windows=session_windows, risk_per_trade=risk,
            spread_pips=SPREAD, slippage_pips=SLIPPAGE,
        )
        res_oos = run_strategy_backtest(
            oos_df, strat_cls(), initial_equity=INITIAL_EQUITY, symbol=SYMBOL,
            session_windows=session_windows, risk_per_trade=risk,
            spread_pips=SPREAD, slippage_pips=SLIPPAGE,
        )
        is_full = df.loc[is_df.index[0]:is_df.index[-1]]
        enr_is = _enrich(res_is, is_full, is_df.index < is_df.index[-1], name)
        enr_oos = _enrich(res_oos, df.loc[oos_df.index[0]:], df.index >= oos_df.index[0], name)
        out = pd.concat([enr_is, enr_oos], ignore_index=True)
        out_path = ROOT / "data" / f"strategy{1 if name=='turtle' else 3}_trades.csv"
        out.to_csv(out_path, index=False)
        print(f"{name}: saved {len(out)} trades -> {out_path} "
              f"(IS={len(enr_is)}, OOS={len(enr_oos)})")


if __name__ == "__main__":
    main()
