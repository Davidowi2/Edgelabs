"""Tests for edgelab.trade.trailing_stop (Phase 4, Module 3)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from edgelab.trade.position import Position, TradeDirection, TradeStatus
from edgelab.trade.trailing_stop import TrailingStopManager
from edgelab.time.broker_time import BrokerTime


@pytest.fixture
def bt():
    return BrokerTime(offset="+3", dst=False)


def _pos(direction=TradeDirection.LONG, entry=1.1000, sl=1.0900, tp=1.1500,
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


class TestNoAction:
    def test_no_action_below_breakeven_trigger(self, bt):
        ts = TrailingStopManager({}, _nl(), bt)
        p = _pos(current=1.1010)  # only 10 pips profit < 20 trigger
        r = ts.evaluate(p, _t())
        assert r["action"] == "none"

    def test_breakeven_not_triggered_if_sl_already_at_breakeven(self, bt):
        ts = TrailingStopManager({}, _nl(), bt)
        # SL already at entry+5 (breakeven buffer); profit 25 -> no action
        p = _pos(current=1.1025, sl=1.1050)
        r = ts.evaluate(p, _t())
        assert r["action"] == "none"


class TestBreakeven:
    def test_breakeven_triggered_at_threshold(self, bt):
        ts = TrailingStopManager({}, _nl(), bt)
        p = _pos(current=1.1025, sl=1.0900)  # 25 pips profit > 20 trigger
        r = ts.evaluate(p, _t())
        assert r["action"] == "move_to_breakeven"
        # LONG: SL = entry + buffer = 1.1000 + 0.0005 = 1.1005
        assert abs(r["new_sl"] - 1.1005) < 1e-9


class TestTrail:
    def test_trail_triggered_after_trail_start(self, bt):
        ts = TrailingStopManager({}, _nl(), bt)
        # tiny lot -> partial (40 pip level) skipped on min-lot, trail reaches
        p = _pos(current=1.1050, sl=1.0900, lot=0.005)
        r = ts.evaluate(p, _t())
        assert r["action"] == "trail_stop"
        # LONG: new SL = current - step = 1.1050 - 0.0020 = 1.1030
        assert abs(r["new_sl"] - 1.1030) < 1e-9

    def test_long_position_trailing_logic(self, bt):
        ts = TrailingStopManager({}, _nl(), bt)
        p = _pos(current=1.1050, sl=1.0900, lot=0.005)
        r = ts.evaluate(p, _t())
        assert r["action"] == "trail_stop"
        assert r["new_sl"] < p.current_price  # SL below price for LONG

    def test_short_position_trailing_logic(self, bt):
        ts = TrailingStopManager({}, _nl(), bt)
        p = _pos(direction=TradeDirection.SHORT, entry=1.1000, sl=1.1100,
                  tp=1.0500, current=1.0950, lot=0.005)  # 50 pips profit
        r = ts.evaluate(p, _t())
        assert r["action"] == "trail_stop"
        assert r["new_sl"] > p.current_price  # SL above price for SHORT

class TestTightenOnly:
    def test_trail_never_moves_sl_further_from_price(self, bt):
        ts = TrailingStopManager({}, _nl(), bt)
        # tiny lot -> partial skipped, trail reaches. current 1.1100, existing SL 1.1070
        p = _pos(current=1.1100, sl=1.1070, lot=0.005)
        r = ts.evaluate(p, _t())
        # proposed trail SL = 1.1100 - 0.0020 = 1.1080 (CLOSER -> accepted)
        assert abs(r["new_sl"] - 1.1080) < 1e-9
        # a genuinely LOOSER proposed SL (1.1060, further from price) is rejected
        kept = ts._tighten(1.1060, 1.1070, p)
        assert kept == 1.1070


class TestPartialClose:
    def test_partial_close_first_level(self, bt):
        ts = TrailingStopManager({}, _nl(), bt)
        p = _pos(current=1.1040, sl=1.0900)  # 40 pips profit -> first level
        r = ts.evaluate(p, _t())
        assert r["action"] == "partial_close"
        assert abs(r["partial_close_pct"] - 0.5) < 1e-9

    def test_partial_close_second_level(self, bt):
        # first close already applied (status PARTIAL_CLOSED), profit now 90 pips
        ts = TrailingStopManager({}, _nl(), bt)
        p = _pos(current=1.1090, sl=1.0900, status=TradeStatus.PARTIAL_CLOSED)
        r = ts.evaluate(p, _t())
        assert r["action"] == "partial_close"
        assert abs(r["partial_close_pct"] - 0.5) < 1e-9

    def test_partial_close_respects_min_lot(self, bt):
        # remaining lot after 50% close would be 0.005 < min_lot 0.01 -> skip partial
        ts = TrailingStopManager({}, _nl(), bt)
        p = _pos(current=1.1040, sl=1.0900, lot=0.01)
        r = ts.evaluate(p, _t())
        assert r["action"] != "partial_close"
        assert r["partial_close_pct"] is None  # min-lot guard prevented partial close

    def test_partial_close_status_updates(self, bt):
        ts = TrailingStopManager({}, _nl(), bt)
        p = _pos(current=1.1040, sl=1.0900)
        r = ts.evaluate(p, _t())
        assert r["action"] == "partial_close"
        # evaluate does NOT mutate; status unchanged after call
        assert p.status == TradeStatus.OPEN

    def test_multiple_partial_closes_in_sequence(self, bt):
        ts = TrailingStopManager({}, _nl(), bt)
        p1 = _pos(current=1.1040, sl=1.0900)          # first level, OPEN
        r1 = ts.evaluate(p1, _t())
        assert r1["action"] == "partial_close"
        p1.status = TradeStatus.PARTIAL_CLOSED
        p2 = _pos(current=1.1080, sl=1.0900, status=TradeStatus.PARTIAL_CLOSED)  # 80 pips
        r2 = ts.evaluate(p2, _t())
        assert r2["action"] == "partial_close"


class TestPurity:
    def test_evaluate_does_not_mutate_position(self, bt):
        ts = TrailingStopManager({}, _nl(), bt)
        p = _pos(current=1.1050, sl=1.0900)
        before_sl = p.current_sl
        r1 = ts.evaluate(p, _t())
        r2 = ts.evaluate(p, _t())
        assert p.current_sl == before_sl
        assert r1 == r2


def _t():
    return datetime(2026, 7, 1, 10, 0, tzinfo=timezone.utc)


def _nl():
    from edgelab.monitoring.logger import TradingLogger
    import tempfile, os
    return TradingLogger(name="ts.test", log_file=os.path.join(tempfile.gettempdir(), "ts.log"))
