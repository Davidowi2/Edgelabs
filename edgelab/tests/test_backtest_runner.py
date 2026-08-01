"""Tests for the backtest runner (bar-by-bar loop + trade lifecycle)."""

from __future__ import annotations

from decimal import Decimal

import pandas as pd
import pytest

from edgelab.backtest.runner import run_backtest
from edgelab.risk.engine import RiskEngine
from edgelab.state.bus import StateBus


def make_long_strategy(entry, sl, tp, on_bar=0):
    def strategy(data, i, state):
        if i == on_bar:
            return {"direction": "LONG", "entry_price": entry, "stop_loss": sl,
                    "take_profit": tp, "strategy_id": "s1"}
        return None
    return strategy


class TestBacktestLifecycle:
    def test_produces_one_trade(self, ohlcv_df):
        strategy = make_long_strategy(1.100, 0.900, 1.115)
        engine = RiskEngine(__import__("edgelab.config", fromlist=["Config"]).Config(), StateBus(10000.0))
        result = run_backtest(ohlcv_df, strategy, engine, Decimal("10000"), "EURUSD")
        assert len(result.trades) == 1

    def test_take_profit_triggered_at_correct_price(self, ohlcv_df):
        strategy = make_long_strategy(1.100, 0.900, 1.115)
        engine = RiskEngine(__import__("edgelab.config", fromlist=["Config"]).Config(), StateBus(10000.0))
        result = run_backtest(ohlcv_df, strategy, engine, Decimal("10000"), "EURUSD")
        trade = result.trades[0]
        # Bar 4 high is 1.115 -> TP hit at 1.115
        assert trade.exit_reason == "take_profit"
        assert float(trade.exit_price) == 1.115

    def test_stop_loss_triggered_at_correct_price(self, ohlcv_df):
        strategy = make_long_strategy(1.100, 0.960, 1.200)
        engine = RiskEngine(__import__("edgelab.config", fromlist=["Config"]).Config(), StateBus(10000.0))
        result = run_backtest(ohlcv_df, strategy, engine, Decimal("10000"), "EURUSD")
        trade = result.trades[0]
        # Bar 4 low is 0.950 -> SL 0.960 hit
        assert trade.exit_reason == "stop_loss"
        assert float(trade.exit_price) == 0.960

    def test_pnl_is_nonzero_regression(self, ohlcv_df):
        strategy = make_long_strategy(1.100, 0.900, 1.115)
        engine = RiskEngine(__import__("edgelab.config", fromlist=["Config"]).Config(), StateBus(10000.0))
        result = run_backtest(ohlcv_df, strategy, engine, Decimal("10000"), "EURUSD")
        assert float(result.trades[0].pnl) != 0.0

    def test_short_trade_pnl(self):
        idx = pd.date_range("2026-01-01 10:00", periods=5, freq="h")
        df = pd.DataFrame({
            "open": [1.100, 1.100, 1.100, 1.100, 1.200],
            "high": [1.101, 1.101, 1.101, 1.101, 1.205],
            "low": [1.099, 1.099, 1.099, 1.099, 1.050],
            "close": [1.100, 1.100, 1.100, 1.100, 1.060],
            "volume": [100] * 5,
        }, index=idx)

        def strategy(data, i, state):
            if i == 0:
                return {"direction": "SHORT", "entry_price": 1.100,
                        "stop_loss": 1.200, "take_profit": 1.050, "strategy_id": "s1"}
            return None

        engine = RiskEngine(__import__("edgelab.config", fromlist=["Config"]).Config(), StateBus(10000.0))
        result = run_backtest(df, strategy, engine, Decimal("10000"), "EURUSD")
        trade = result.trades[0]
        # Bar 4: low 1.050 hits TP (1.050) but high 1.205 also hits SL (1.200).
        # Runner applies conservative stop-first rule -> closes at stop, a loss.
        assert trade.direction == "SHORT"
        assert trade.exit_reason == "stop_loss"
        assert float(trade.pnl) < 0

    def test_equity_curve_length(self, ohlcv_df):
        strategy = make_long_strategy(1.100, 0.900, 1.115)
        engine = RiskEngine(__import__("edgelab.config", fromlist=["Config"]).Config(), StateBus(10000.0))
        result = run_backtest(ohlcv_df, strategy, engine, Decimal("10000"), "EURUSD")
        # one entry point per bar + initial point
        assert len(result.equity_curve) == len(ohlcv_df) + 1

    def test_multiple_sequential_trades(self):
        idx = pd.date_range("2026-01-01 10:00", periods=10, freq="h")
        df = pd.DataFrame({
            "open": [1.100, 1.100, 1.100, 1.100, 1.115, 1.115, 1.115, 1.115, 1.090, 1.090],
            "high": [1.101, 1.101, 1.101, 1.101, 1.200, 1.116, 1.116, 1.116, 1.091, 1.091],
            "low": [1.099, 1.099, 1.099, 1.099, 1.050, 1.114, 1.114, 1.114, 1.000, 1.000],
            "close": [1.100, 1.100, 1.100, 1.100, 1.118, 1.115, 1.115, 1.115, 1.005, 1.005],
            "volume": [100] * 10,
        }, index=idx)

        def strategy(data, i, state):
            # open a LONG on bar 0, after it closes open another on bar 5
            if i == 0:
                return {"direction": "LONG", "entry_price": 1.100,
                        "stop_loss": 1.050, "take_profit": 1.118, "strategy_id": "s1"}
            if i == 5 and not state.open_positions:
                return {"direction": "LONG", "entry_price": 1.115,
                        "stop_loss": 1.000, "take_profit": 1.118, "strategy_id": "s1"}
            return None

        engine = RiskEngine(__import__("edgelab.config", fromlist=["Config"]).Config(), StateBus(10000.0))
        result = run_backtest(df, strategy, engine, Decimal("10000"), "EURUSD")
        assert len(result.trades) >= 1

    def test_no_trade_when_outside_session(self):
        idx = pd.date_range("2026-07-20 03:00", periods=3, freq="h")
        df = pd.DataFrame({
            "open": [1.100, 1.100, 1.100],
            "high": [1.101, 1.101, 1.101],
            "low": [1.099, 1.099, 1.099],
            "close": [1.100, 1.100, 1.100],
            "volume": [100, 100, 100],
        }, index=idx)

        def strategy(data, i, state):
            if i == 0:
                return {"direction": "LONG", "entry_price": 1.100,
                        "stop_loss": 0.900, "take_profit": 1.200, "strategy_id": "s1"}
            return None

        engine = RiskEngine(__import__("edgelab.config", fromlist=["Config"]).Config(), StateBus(10000.0))
        result = run_backtest(df, strategy, engine, Decimal("10000"), "EURUSD")
        # 03:00 is outside NY session -> no approved trade
        assert len(result.trades) == 0
