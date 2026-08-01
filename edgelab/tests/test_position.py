"""Tests for edgelab.trade.position (Phase 4, Module 1)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from edgelab.trade.position import Position, TradeDirection, TradeStatus


def _pos(direction=TradeDirection.LONG, entry=1.1000, sl=1.0950, tp=1.1100,
          lot=0.1, current=1.1000, status=TradeStatus.OPEN):
    return Position(
        position_id="pos-1",
        symbol="EURUSD",
        direction=direction,
        entry_price=entry,
        current_sl=sl,
        current_tp=tp,
        lot_size=lot,
        entry_time=datetime(2026, 7, 1, 10, 0, tzinfo=timezone.utc),
        status=status,
        magic_number="idea-1",
        current_price=current,
    )


class TestCreate:
    def test_create_long_position(self):
        p = _pos(direction=TradeDirection.LONG)
        assert p.direction == TradeDirection.LONG
        assert p.entry_price == 1.1000

    def test_create_short_position(self):
        p = _pos(direction=TradeDirection.SHORT, entry=1.1000, sl=1.1050, tp=1.0900)
        assert p.direction == TradeDirection.SHORT
        assert p.entry_price == 1.1000


class TestDerived:
    def test_risk_pips_calculation(self):
        p = _pos(entry=1.1000, sl=1.0950)
        assert p.risk_pips == 50.0

    def test_reward_pips_calculation(self):
        p = _pos(entry=1.1000, tp=1.1100)
        assert p.reward_pips == 100.0

    def test_rr_ratio_calculation(self):
        p = _pos(entry=1.1000, sl=1.0950, tp=1.1150)  # 50 / 150
        assert abs(p.rr_ratio - 3.0) < 1e-9

    def test_rr_ratio_none_when_missing_sl(self):
        p = _pos(sl=None)
        assert p.rr_ratio is None

    def test_rr_ratio_none_when_missing_tp(self):
        p = _pos(tp=None)
        assert p.rr_ratio is None

    def test_is_profitable_long(self):
        p = _pos(direction=TradeDirection.LONG, current=1.1050)
        assert p.is_profitable is True

    def test_is_profitable_short(self):
        p = _pos(direction=TradeDirection.SHORT, entry=1.1000, sl=1.1050, tp=1.0900, current=1.0950)
        assert p.is_profitable is True

    def test_is_not_profitable_when_against_position(self):
        p = _pos(direction=TradeDirection.LONG, current=1.0950)
        assert p.is_profitable is False

    def test_update_price(self):
        p = _pos()
        p.update_price(1.1050)
        assert p.current_price == 1.1050

    def test_profit_pips_long(self):
        p = _pos(direction=TradeDirection.LONG, current=1.1050)
        assert p.profit_pips == 50.0

    def test_profit_pips_short(self):
        p = _pos(direction=TradeDirection.SHORT, entry=1.1000, sl=1.1050, tp=1.0900, current=1.0950)
        assert p.profit_pips == 50.0


class TestPnl:
    def test_calculate_unrealized_pnl_long_profit(self):
        p = _pos(direction=TradeDirection.LONG, entry=1.1000, current=1.1050, lot=0.1)
        assert p.calculate_unrealized_pnl() == 50.0

    def test_calculate_unrealized_pnl_long_loss(self):
        p = _pos(direction=TradeDirection.LONG, entry=1.1000, current=1.0950, lot=0.1)
        assert p.calculate_unrealized_pnl() == -50.0

    def test_calculate_unrealized_pnl_short_profit(self):
        p = _pos(direction=TradeDirection.SHORT, entry=1.1000, sl=1.1050, tp=1.0900, current=1.0950, lot=0.1)
        assert p.calculate_unrealized_pnl() == 50.0

    def test_calculate_unrealized_pnl_uses_pip_value_parameter(self):
        p = _pos(direction=TradeDirection.LONG, entry=1.1000, current=1.1050, lot=0.1)
        assert p.calculate_unrealized_pnl(pip_value=20.0) == 100.0


class TestStatus:
    def test_position_status_transitions(self):
        p = _pos()
        assert p.status == TradeStatus.OPEN
        p.status = TradeStatus.PARTIAL_CLOSED
        assert p.status == TradeStatus.PARTIAL_CLOSED
        p.status = TradeStatus.CLOSED
        assert p.status == TradeStatus.CLOSED
