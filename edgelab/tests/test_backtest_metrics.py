"""Tests for backtest metrics calculation."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest

from edgelab.backtest.metrics import calculate_metrics, summarize_trades
from edgelab.state.bus import Position


def make_trade(pnl, entry=datetime(2026, 1, 1, 10), exit=datetime(2026, 1, 1, 12)):
    return Position("EURUSD", "LONG", 1.1, 1.09, 1.12, 0.1, entry, "T1",
                    pnl=pnl, exit_price=1.11, exit_time=exit)


class TestSummarizeTrades:
    def test_empty_trade_list_handled(self):
        s = summarize_trades([])
        assert s["total_trades"] == 0
        assert s["win_rate"] == 0.0
        assert s["profit_factor"] == 0.0

    def test_win_rate_calculated(self):
        trades = [make_trade(10.0), make_trade(-5.0), make_trade(20.0)]
        s = summarize_trades(trades)
        assert s["total_trades"] == 3
        assert s["win_rate"] == pytest.approx(2 / 3)
        assert s["average_win"] == pytest.approx(15.0)
        assert s["average_loss"] == pytest.approx(5.0)

    def test_profit_factor_all_wins(self):
        trades = [make_trade(10.0), make_trade(20.0)]
        s = summarize_trades(trades)
        assert s["profit_factor"] == pytest.approx(30.0)

    def test_holding_time_calculated(self):
        trades = [make_trade(10.0)]
        s = summarize_trades(trades)
        assert s["average_holding_time"] == pytest.approx(120.0)

    def test_zero_pnl_no_zero_division_regression(self):
        # This is the regression for the bug we fixed: zero/equal pnl must not crash.
        trades = [make_trade(0.0), make_trade(0.0)]
        s = summarize_trades(trades)
        assert s["total_trades"] == 2
        assert s["profit_factor"] == 0.0


class TestCalculateMetrics:
    def test_short_equity_curve_returns_zeros(self):
        curve = [(datetime(2026, 1, 1), Decimal("10000"))]
        m = calculate_metrics(curve, [])
        assert m["total_return_pct"] == 0.0
        assert m["max_drawdown_pct"] == 0.0

    def test_total_return_positive(self):
        curve = [
            (datetime(2026, 1, 1), Decimal("10000")),
            (datetime(2026, 1, 2), Decimal("10100")),
            (datetime(2026, 1, 3), Decimal("10050")),
        ]
        m = calculate_metrics(curve, [])
        assert m["total_return_pct"] == pytest.approx(0.5)

    def test_max_drawdown_calculated(self):
        curve = [
            (datetime(2026, 1, 1), Decimal("10000")),
            (datetime(2026, 1, 2), Decimal("11000")),
            (datetime(2026, 1, 3), Decimal("9900")),
        ]
        m = calculate_metrics(curve, [])
        # drawdown from 11000 to 9900 = 1100/11000 = 10%
        assert m["max_drawdown_pct"] == pytest.approx(10.0)

    def test_recovery_factor_present(self):
        curve = [
            (datetime(2026, 1, 1), Decimal("10000")),
            (datetime(2026, 1, 2), Decimal("10500")),
        ]
        m = calculate_metrics(curve, [])
        assert "recovery_factor" in m

    def test_includes_trade_summary(self):
        curve = [
            (datetime(2026, 1, 1), Decimal("10000")),
            (datetime(2026, 1, 2), Decimal("10100")),
        ]
        trades = [make_trade(10.0)]
        m = calculate_metrics(curve, trades)
        assert m["total_trades"] == 1
