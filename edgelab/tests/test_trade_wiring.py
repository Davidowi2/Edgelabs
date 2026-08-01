"""Tests for edgelab.trade TradeManager wiring (Phase 4, Module 4)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from edgelab.trade import TradeManager
from edgelab.trade.position import Position, TradeDirection, TradeStatus
from edgelab.time.broker_time import BrokerTime


@pytest.fixture
def bt():
    return BrokerTime(offset="+3", dst=False)


@pytest.fixture
def logger(tmp_path):
    from edgelab.monitoring.logger import TradingLogger
    return TradingLogger(name="tm.test", log_file=str(tmp_path / "tm.log"))


def _pos(sl=1.0950, lot=0.1, entry=1.1000, tp=1.1100, current=1.1000, status=TradeStatus.OPEN):
    return Position(
        position_id="pos-1",
        symbol="EURUSD",
        direction=TradeDirection.LONG,
        entry_price=entry,
        current_sl=sl,
        current_tp=tp,
        lot_size=lot,
        entry_time=datetime(2026, 7, 1, 10, 0, tzinfo=timezone.utc),
        status=status,
        magic_number="idea-1",
        current_price=current,
    )


_T = datetime(2026, 7, 1, 10, 0, tzinfo=timezone.utc)


class TestEvaluateAll:
    def test_evaluate_all_returns_complete_dict(self, bt, logger):
        tm = TradeManager({}, logger, bt)
        p = _pos()
        r = tm.evaluate_all(p, 10000.0, 1.1000, _T)
        for k in ("position_id", "current_price", "unrealized_pnl", "sl_watchdog",
                  "trailing_stop", "recommended_action", "timestamp"):
            assert k in r

    def test_evaluate_all_updates_position_price(self, bt, logger):
        tm = TradeManager({}, logger, bt)
        p = _pos()
        tm.evaluate_all(p, 10000.0, 1.1040, _T)
        assert p.current_price == 1.1040

    def test_critical_sl_takes_priority(self, bt, logger):
        tm = TradeManager({}, logger, bt)
        p = _pos(sl=None)  # no SL -> critical
        r = tm.evaluate_all(p, 10000.0, 1.1040, _T)
        assert r["recommended_action"] == "close_position"

    def test_warning_sl_takes_priority_over_trail(self, bt, logger):
        tm = TradeManager({}, logger, bt)
        p = _pos(sl=1.0500)  # too wide -> warning; profit also high
        r = tm.evaluate_all(p, 10000.0, 1.1080, _T)
        assert r["recommended_action"] == "tighten_sl"

    def test_trail_action_when_sl_ok(self, bt, logger):
        tm = TradeManager({}, logger, bt)
        p = _pos(sl=1.0950, current=1.1080)  # ok SL, 80 pips profit
        r = tm.evaluate_all(p, 10000.0, 1.1080, _T)
        assert r["recommended_action"] in ("trail_stop", "partial_close")

    def test_no_action_when_everything_ok(self, bt, logger):
        tm = TradeManager({}, logger, bt)
        p = _pos(sl=1.0950, current=1.1010)  # ok SL, low profit
        r = tm.evaluate_all(p, 10000.0, 1.1010, _T)
        assert r["recommended_action"] == "none"

    def test_unrealized_pnl_in_result(self, bt, logger):
        tm = TradeManager({}, logger, bt)
        p = _pos(sl=1.0950, current=1.1050, lot=0.1)  # 50 pips * 10 * 0.1
        r = tm.evaluate_all(p, 10000.0, 1.1050, _T)
        assert r["unrealized_pnl"] == 50.0

    def test_position_id_in_result(self, bt, logger):
        tm = TradeManager({}, logger, bt)
        p = _pos()
        r = tm.evaluate_all(p, 10000.0, 1.1000, _T)
        assert r["position_id"] == "pos-1"

    def test_timestamp_in_result(self, bt, logger):
        tm = TradeManager({}, logger, bt)
        p = _pos()
        r = tm.evaluate_all(p, 10000.0, 1.1000, _T)
        assert r["timestamp"] == _T

    def test_does_not_modify_position_object(self, bt, logger):
        tm = TradeManager({}, logger, bt)
        p = _pos(sl=1.0950, current=1.1080)
        r1 = tm.evaluate_all(p, 10000.0, 1.1080, _T)
        r2 = tm.evaluate_all(p, 10000.0, 1.1080, _T)
        # position SL unchanged (evaluate returns recommendation only)
        assert p.current_sl == 1.0950
        assert r1 == r2
