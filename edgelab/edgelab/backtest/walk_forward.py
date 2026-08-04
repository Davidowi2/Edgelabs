"""Proper walk-forward validation (replaces the mislabeled rolling-OOS in the
original run_strategy_backtests.py).

A real walk-forward:
  1. Split history into folds of (train_window, test_window).
  2. On the TRAIN window, pick the best parameter set by in-sample metric
     (e.g. profit factor). This is the ONLY place parameters are chosen.
  3. Apply those parameters to the TEST window (out-of-sample) and record the
     trades/returns. No parameter from the test window leaks into selection.
  4. Step forward and repeat. Concatenate the OOS test windows into one OOS
     equity curve + trade list, then evaluate against the validation bar.

This is honest: the test window is never used to choose parameters. It also
solves the "OOS = 0 trades" problem for short data — instead of one 80/20 split,
we get several OOS folds, each contributing trades.

Currently implemented for the single-instrument interface used by the canonical
backtester (signal/exit_signal/on_fill/on_exit). A parameter grid is supplied by
the caller (e.g. {"trend_ema": [50, 100, 200], "breakout_n": [10, 20]}).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import product
from typing import Any, Callable, Optional

import pandas as pd

from edgelab.backtest.canonical import run_canonical_backtest
from edgelab.backtest.monte_carlo import run_monte_carlo


@dataclass
class WalkForwardResult:
    oos_trades: list = field(default_factory=list)
    oos_equity_curve: list = field(default_factory=list)
    folds: list = field(default_factory=list)  # per-fold summary
    metrics: dict = field(default_factory=dict)
    monte_carlo: Optional[Any] = None


def _build_strategy(base_factory, params: dict):
    return base_factory(**params)


def run_walk_forward(
    data: pd.DataFrame,
    base_strategy_factory: Callable[..., Any],
    param_grid: dict[str, list],
    initial_equity: float = 10_000.0,
    symbol: str = "EURUSD",
    risk_per_trade: float = 0.01,
    spread_pips: float = 0.8,
    slippage_pips: float = 0.5,
    session_windows=None,
    train_bars: int = 250,
    test_bars: int = 60,
    selection_metric: str = "profit_factor",
    min_train_trades: int = 10,
) -> WalkForwardResult:
    """Walk-forward over `data` using a rolling (train, test) window.

    base_strategy_factory(**params) must return a strategy object exposing the
    canonical interface. param_grid is a dict param_name -> list of values.
    """
    n = len(data)
    keys = list(param_grid.keys())
    combos = [dict(zip(keys, v)) for v in product(*param_grid.values())]

    oos_trades: list = []
    oos_equity = [(data.index[0], float(initial_equity))]
    fold_summaries: list = []
    start = train_bars
    fold_idx = 0
    while start + test_bars <= n:
        train = data.iloc[start - train_bars:start]
        test = data.iloc[start:start + test_bars]
        # ---- select best params on TRAIN only ----
        # If the grid is empty, there is nothing to select: validate the single
        # (default) config directly on the TEST window (true OOS).
        if not combos:
            best_params = {}
        else:
            best_params = None
            best_score = -float("inf")
            for combo in combos:
                strat = _build_strategy(base_strategy_factory, combo)
                res = run_canonical_backtest(train, strat, initial_equity=initial_equity,
                                             symbol=symbol, risk_per_trade=risk_per_trade,
                                             spread_pips=spread_pips, slippage_pips=slippage_pips,
                                             session_windows=session_windows)
                m = res.metrics
                if m["total_trades"] < min_train_trades:
                    continue
                score = m.get(selection_metric, 0.0)
                if score is not None and score > 0 and score > best_score:
                    best_score = score
                    best_params = combo
        if best_params is None:
            # no trainable combo; skip this fold (no OOS trades)
            fold_summaries.append({"fold": fold_idx, "best_params": None,
                                    "train_trades": 0, "oos_trades": 0})
            start += test_bars
            fold_idx += 1
            continue
        # ---- validate on TEST (OOS) with the chosen params ----
        # Prepend a warm-up window so indicators with long lookbacks (e.g. EMA200)
        # are seeded before the true OOS region begins. Only trades whose entry
        # falls inside the TEST region are attributed as OOS (warm-up trades are
        # discarded to avoid look-ahead / in-sample contamination).
        warmup_bars = 250
        test_start = start
        warm_start = max(0, test_start - warmup_bars)
        warm_test = data.iloc[warm_start:start + test_bars]
        strat = _build_strategy(base_strategy_factory, best_params)
        res = run_canonical_backtest(warm_test, strat, initial_equity=initial_equity,
                                     symbol=symbol, risk_per_trade=risk_per_trade,
                                     spread_pips=spread_pips, slippage_pips=slippage_pips,
                                     session_windows=session_windows)
        test_start_ts = data.index[test_start]
        oos_in_fold = 0
        for t in res.trades:
            if t.entry_time >= test_start_ts:
                oos_trades.append(t)
                oos_in_fold += 1
        # Do NOT extend the raw per-fold equity curves (they each reset to
        # initial_equity, which corrupts the aggregated diff). Instead the
        # final equity curve is rebuilt from cumulative OOS P&L at the end.
        fold_summaries.append({
            "fold": fold_idx, "best_params": best_params,
            "train_trades": res.metrics["total_trades"],
            "oos_trades": oos_in_fold,
            "oos_pf": res.metrics["profit_factor"],
        })
        start += test_bars
        fold_idx += 1

    # aggregate OOS metrics from the raw trade P&Ls (honest, no curve corruption)
    pnls = [t.pnl for t in oos_trades]
    eq = [float(initial_equity)]
    for p in pnls:
        eq.append(eq[-1] + p)
    # pair each equity point with the trade's exit time for a proper curve
    times = [t.exit_time for t in oos_trades]
    oos_equity = list(zip([data.index[0]] + times, eq))
    metrics = _agg_metrics(oos_equity, oos_trades, initial_equity)
    mc = run_monte_carlo(pnls, initial_equity=initial_equity, n_simulations=1000,
                         min_profitable_pct=70.0, seed=7) if pnls else None
    return WalkForwardResult(oos_trades=oos_trades, oos_equity_curve=oos_equity,
                             folds=fold_summaries, metrics=metrics, monte_carlo=mc)


def _agg_metrics(equity_curve, trades, initial_equity):
    import numpy as np
    eq = np.array([e for _, e in equity_curve])
    if len(eq) < 2 or not trades:
        return {"total_trades": len(trades), "win_rate": 0.0, "profit_factor": 0.0,
                "sharpe_ratio": 0.0, "max_drawdown_pct": 0.0, "total_return_pct": 0.0,
                "avg_rr": 0.0, "avg_holding_bars": 0.0}
    ret = np.diff(eq)
    total_return_pct = (eq[-1] - initial_equity) / initial_equity * 100
    peak = np.maximum.accumulate(eq)
    dd = (peak - eq) / np.where(peak == 0, 1, peak)
    max_dd = float(np.max(dd)) * 100
    sharpe = 0.0
    if len(ret) > 1 and np.std(ret) > 0:
        sharpe = float(np.mean(ret) / np.std(ret)) * np.sqrt(252)
    pnls = [t.pnl for t in trades]
    wins = [p for p in pnls if p > 0]; losses = [p for p in pnls if p <= 0]
    win_rate = len(wins) / len(pnls)
    gw = sum(wins); gl = abs(sum(losses))
    pf = gw / gl if gl > 0 else (float("inf") if gw > 0 else 0.0)
    aw = gw / len(wins) if wins else 0.0
    al = gl / len(losses) if losses else 0.0
    avg_rr = aw / al if al > 0 else (float("inf") if aw > 0 else 0.0)
    return {"total_trades": len(trades), "win_rate": win_rate, "profit_factor": pf,
            "sharpe_ratio": sharpe, "max_drawdown_pct": max_dd,
            "total_return_pct": total_return_pct, "avg_rr": avg_rr,
            "avg_holding_bars": 0.0}
