"""Backtest metrics."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Sequence

import numpy as np


def summarize_trades(trades: list) -> dict:
    if not trades:
        return {
            "total_trades": 0,
            "win_rate": 0.0,
            "average_win": 0.0,
            "average_loss": 0.0,
            "profit_factor": 0.0,
            "average_holding_time": 0.0,
        }
    pnls = [float(t.pnl) for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    holding_times = []
    for t in trades:
        if t.entry_time and t.exit_time:
            holding_times.append((t.exit_time - t.entry_time).total_seconds() / 60.0)
    win_sum = sum(wins)
    loss_sum_abs = abs(sum(losses))
    if win_sum > 0 and loss_sum_abs > 0:
        profit_factor = win_sum / loss_sum_abs
    elif win_sum > 0 and loss_sum_abs == 0:
        # only winners, no realized loss
        profit_factor = float(win_sum)
    else:
        profit_factor = 0.0

    return {
        "total_trades": len(trades),
        "win_rate": len(wins) / len(trades) if trades else 0.0,
        "average_win": sum(wins) / len(wins) if wins else 0.0,
        "average_loss": abs(sum(losses) / len(losses)) if losses else 0.0,
        "profit_factor": profit_factor,
        "average_holding_time": sum(holding_times) / len(holding_times) if holding_times else 0.0,
    }


def calculate_metrics(equity_curve: Sequence[tuple[datetime, Decimal]], trades: list) -> dict:
    if len(equity_curve) < 2:
        return {
            "total_return_pct": 0.0,
            "max_drawdown_pct": 0.0,
            "sharpe_ratio": 0.0,
            "recovery_factor": 0.0,
            **summarize_trades(trades),
        }

    equity = np.array([float(e) for _, e in equity_curve])
    returns = np.diff(equity)
    initial = float(equity_curve[0][1]) or 1.0
    total_return_pct = (equity[-1] - initial) / initial * 100

    peak = np.maximum.accumulate(equity)
    drawdown = (peak - equity) / np.where(peak == 0, 1, peak)
    max_drawdown_pct = float(np.max(drawdown)) * 100

    sharpe_ratio = 0.0
    if len(returns) > 1 and np.std(returns) > 0:
        sharpe_ratio = float(np.mean(returns) / np.std(returns)) * np.sqrt(252)

    recovery_factor = 0.0
    max_dd_value = max_drawdown_pct
    if max_dd_value > 0:
        recovery_factor = total_return_pct / max_dd_value

    trade_summary = summarize_trades(trades)
    return {
        "total_return_pct": total_return_pct,
        "max_drawdown_pct": max_drawdown_pct,
        "sharpe_ratio": sharpe_ratio,
        "recovery_factor": recovery_factor,
        **trade_summary,
    }
