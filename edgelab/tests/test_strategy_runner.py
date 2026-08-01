"""Smoke test for the strategy-aware backtest runner (uses synthetic data, fast)."""

from __future__ import annotations

import pandas as pd
import pytest

from edgelab.backtest.strategy_runner import run_strategy_backtest
from edgelab.config import Config
from edgelab.strategy.turtle import TurtleStrategy
from edgelab.strategy.session_expansion import SessionExpansionStrategy


def _make_df(n: int = 400) -> pd.DataFrame:
    idx = pd.date_range("2022-01-03 00:00", periods=n, freq="h")
    prices = [1.1000 + 0.00015 * i for i in range(n)]
    df = pd.DataFrame(
        {
            "open": prices,
            "high": [p + 0.0003 for p in prices],
            "low": [p - 0.0003 for p in prices],
            "close": prices,
            "volume": [0] * n,
        },
        index=idx,
    )
    return df


class TestStrategyRunner:
    def test_runs_turtle_without_error(self):
        df = _make_df(400)
        res = run_strategy_backtest(df, TurtleStrategy(), initial_equity=10000.0)
        assert res.metrics["total_trades"] >= 0
        assert len(res.equity_curve) == len(df) + 1

    def test_capacity_to_open_and_close_positions(self):
        df = _make_df(400)
        # Force a turtle breakout then a reversal so at least one round trip occurs.
        # The RiskEngine gates entries to NY sessions (08-11 / 13:30-16 NY = 13-16 /
        # 18:30-21 UTC). Bar 250 in this synthetic series is 10:00 UTC (outside the
        # window), so we place the breakout at bar 253 (13:00 UTC = 08:00 NY).
        df.loc[df.index[253], "close"] = df["close"].iloc[252] + 0.0120
        df.loc[df.index[253], "high"] = df["close"].iloc[253] + 0.0003
        df.loc[df.index[310], "close"] = df["close"].iloc[309] - 0.0200
        df.loc[df.index[310], "low"] = df["close"].iloc[310] - 0.0003
        res = run_strategy_backtest(df, TurtleStrategy(), initial_equity=10000.0)
        assert res.metrics["total_trades"] >= 1

    def test_session_strategy_runs(self):
        df = _make_df(400)
        res = run_strategy_backtest(
            df, SessionExpansionStrategy(), initial_equity=10000.0, risk_per_trade=0.005
        )
        assert isinstance(res.metrics, dict)
