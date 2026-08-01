"""Tests for the Risk Engine (hard risk governor)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest

from edgelab.risk.engine import Approval, RiskEngine, TradeProposal
from edgelab.state.bus import Position, StateBus


def make_proposal(timestamp, symbol="EURUSD", direction="LONG",
                  entry="1.1000", sl="1.0950", tp="1.1100", sid="s1"):
    return TradeProposal(
        symbol=symbol, direction=direction,
        entry_price=Decimal(entry), stop_loss=Decimal(sl),
        take_profit=Decimal(tp), timestamp=timestamp, strategy_id=sid,
    )


class TestRiskEngineApproval:
    def test_approves_valid_trade(self, config, state, ny_session_time):
        engine = RiskEngine(config, state)
        approval = engine.evaluate(make_proposal(ny_session_time))
        assert approval.approved is True
        assert approval.reason == "Approved"
        assert approval.lot_size > 0

    def test_returns_approval_dataclass(self, config, state, ny_session_time):
        engine = RiskEngine(config, state)
        approval = engine.evaluate(make_proposal(ny_session_time))
        assert isinstance(approval, Approval)
        assert approval.risk_amount > 0
        assert approval.risk_pips > 0


class TestRiskEngineRejections:
    def test_rejects_circuit_breaker(self, config, state, ny_session_time):
        engine = RiskEngine(config, state)
        engine.circuit_breakers.circuit_breaker_active_status["s1"] = True
        approval = engine.evaluate(make_proposal(ny_session_time))
        assert approval.approved is False
        assert "Circuit breaker" in approval.reason

    def test_rejects_daily_loss_lock(self, config, state, ny_session_time):
        state.today = ny_session_time.date().isoformat()
        state.daily_pnl = -250.0
        state.daily_start_equity = 10000.0
        engine = RiskEngine(config, state)
        approval = engine.evaluate(make_proposal(ny_session_time))
        assert approval.approved is False
        assert "Daily loss lock" in approval.reason

    def test_rejects_outside_session(self, config, state, outside_session_time):
        engine = RiskEngine(config, state)
        approval = engine.evaluate(make_proposal(outside_session_time))
        assert approval.approved is False
        assert "Outside session" in approval.reason

    def test_approves_inside_session_window(self, config, state, ny_session_time):
        engine = RiskEngine(config, state)
        approval = engine.evaluate(make_proposal(ny_session_time))
        assert approval.approved is True

    def test_rejects_total_dd_lock(self, config, state, ny_session_time):
        state.equity = 9000.0
        state.peak_equity = 10000.0
        engine = RiskEngine(config, state)
        approval = engine.evaluate(make_proposal(ny_session_time))
        assert approval.approved is False
        assert "Total drawdown" in approval.reason

    def test_rejects_max_positions(self, config, state, ny_session_time):
        state.open_positions = [
            Position("EURUSD", "LONG", 1.1, 1.09, 1.12, 0.1, ny_session_time, "T1"),
            Position("EURUSD", "LONG", 1.1, 1.09, 1.12, 0.1, ny_session_time, "T2"),
        ]
        engine = RiskEngine(config, state)
        approval = engine.evaluate(make_proposal(ny_session_time, symbol="GBPUSD"))
        assert approval.approved is False
        assert "Max positions" in approval.reason

    def test_rejects_correlated_position(self, config, state, ny_session_time):
        state.open_positions = [
            Position("EURUSD", "LONG", 1.1, 1.09, 1.12, 0.1, ny_session_time, "T1"),
        ]
        engine = RiskEngine(config, state)
        # GBPUSD is in the USD_EXPOSURE correlation group with EURUSD
        approval = engine.evaluate(make_proposal(ny_session_time, symbol="GBPUSD"))
        assert approval.approved is False
        assert "Correlated" in approval.reason

    def test_rejects_zero_stop_distance(self, config, state, ny_session_time):
        engine = RiskEngine(config, state)
        approval = engine.evaluate(make_proposal(ny_session_time, sl="1.1000"))
        assert approval.approved is False
        assert "Stop loss distance is zero" in approval.reason

    def test_rejects_when_would_breach_daily_loss(self, config, state, ny_session_time):
        # daily_start 10000, daily_loss_lock 2% = 200 limit
        state.today = ny_session_time.date().isoformat()
        state.daily_pnl = -150.0
        state.daily_start_equity = 10000.0
        # risk_per_trade 1% of equity ~ 100, projected 250 >= 200
        engine = RiskEngine(config, state)
        approval = engine.evaluate(make_proposal(ny_session_time))
        assert approval.approved is False
        assert "daily loss" in approval.reason.lower()

    def test_rejects_when_would_breach_total_dd(self, config, state, ny_session_time):
        state.equity = 9600.0
        state.peak_equity = 10000.0
        # risk_per_trade 1% ~ 96; projected dd (10000-(9600-96))/10000 = 0.0496 < 0.05
        # push equity lower so projected breaches 5%
        state.equity = 9550.0
        engine = RiskEngine(config, state)
        approval = engine.evaluate(make_proposal(ny_session_time))
        assert approval.approved is False
        assert "drawdown" in approval.reason.lower()


class TestRiskEngineSizing:
    def test_lot_size_scales_with_equity(self, config, state, ny_session_time):
        engine = RiskEngine(config, state)
        a = engine.evaluate(make_proposal(ny_session_time))
        big = StateBus(20000.0)
        engine2 = RiskEngine(config, big)
        b = engine2.evaluate(make_proposal(ny_session_time))
        assert b.lot_size > a.lot_size

    def test_spread_reduces_lot_size(self, config, state, ny_session_time):
        # Without spread
        engine = RiskEngine(config, state)
        base = engine.evaluate(make_proposal(ny_session_time))
        # With spread, risk_pips is larger -> lot smaller
        from edgelab.risk.sizing import PositionSizing
        calc = PositionSizing(config)
        no_spread = calc.calculate(Decimal("10000"), Decimal("1.1"), Decimal("1.095"), "EURUSD", spread_pips=None)
        with_spread = calc.calculate(Decimal("10000"), Decimal("1.1"), Decimal("1.095"), "EURUSD", spread_pips=Decimal("0.8"))
        assert with_spread[0] < no_spread[0]
        assert base.lot_size > 0
