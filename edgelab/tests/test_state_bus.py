"""Tests for the shared StateBus."""

from __future__ import annotations

from datetime import datetime

import pytest

from edgelab.state.bus import Position, StateBus


class TestStateBasics:
    def test_initial_equity_set(self):
        s = StateBus(10000.0)
        assert s.equity == 10000.0
        assert s.peak_equity == 10000.0

    def test_add_position_tracks_open(self):
        s = StateBus(10000.0)
        s.add_position(Position("EURUSD", "LONG", 1.1, 1.09, 1.12, 0.1, datetime(2026, 7, 20, 10), "T1"))
        assert len(s.open_positions) == 1

    def test_close_position_removes_from_open(self):
        s = StateBus(10000.0)
        pos = Position("EURUSD", "LONG", 1.1, 1.09, 1.12, 0.1, datetime(2026, 7, 20, 10), "T1")
        s.add_position(pos)
        s.close_position("T1", 1.12, datetime(2026, 7, 20, 11))
        assert len(s.open_positions) == 0
        assert len(s.closed_trades) == 1

    def test_close_unknown_trade_returns_none(self):
        s = StateBus(10000.0)
        assert s.close_position("NOPE", 1.0, datetime(2026, 7, 20)) is None


class TestPnLAndEquity:
    def test_long_profit_increases_equity(self):
        s = StateBus(10000.0)
        s.add_position(Position("EURUSD", "LONG", 1.1000, 1.0900, 1.1200, 1.0, datetime(2026, 7, 20, 10), "T1"))
        s.close_position("T1", 1.1100, datetime(2026, 7, 20, 11))
        # (1.1100 - 1.1000) * 1.0 = 0.01
        assert abs(s.equity - 10000.01) < 1e-9
        assert s.current_pnl == pytest.approx(0.01)

    def test_short_profit_increases_equity(self):
        s = StateBus(10000.0)
        s.add_position(Position("EURUSD", "SHORT", 1.1000, 1.1100, 1.0900, 1.0, datetime(2026, 7, 20, 10), "T1"))
        s.close_position("T1", 1.0950, datetime(2026, 7, 20, 11))
        # SHORT: (1.1000 - 1.0950) * 1.0 = 0.005
        assert abs(s.equity - 10000.005) < 1e-9

    def test_peak_equity_updates(self):
        s = StateBus(10000.0)
        s.add_position(Position("EURUSD", "LONG", 1.1000, 1.0900, 1.1200, 10.0, datetime(2026, 7, 20, 10), "T1"))
        s.close_position("T1", 1.1200, datetime(2026, 7, 20, 11))
        # (1.1200-1.1000)*10 = 0.20
        assert s.peak_equity == 10000.20

    def test_peak_equity_does_not_decrease(self):
        s = StateBus(10000.0)
        s.add_position(Position("EURUSD", "LONG", 1.1000, 1.0900, 1.1200, 10.0, datetime(2026, 7, 20, 10), "T1"))
        s.close_position("T1", 1.0900, datetime(2026, 7, 20, 11))
        # loss, equity drops below initial
        assert s.peak_equity == 10000.0
        assert s.equity < 10000.0


class TestDailyReset:
    def test_reset_clears_daily_pnl_on_new_day(self):
        s = StateBus(10000.0)
        s.daily_pnl = 100.0
        s.daily_start_equity = 10000.0
        s.today = "2026-07-19"
        s.reset_daily(datetime(2026, 7, 20, 0, 0))
        assert s.daily_pnl == 0.0
        assert s.daily_start_equity == 10000.0
        assert s.today == "2026-07-20"

    def test_no_reset_on_same_day(self):
        s = StateBus(10000.0)
        s.daily_pnl = 100.0
        s.today = "2026-07-20"
        s.reset_daily(datetime(2026, 7, 20, 12, 0))
        assert s.daily_pnl == 100.0
