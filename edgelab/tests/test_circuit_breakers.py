"""Tests for circuit breakers (daily loss + total drawdown locks)."""

from __future__ import annotations

from datetime import datetime

import pytest

from edgelab.risk.engine import CircuitBreakers
from edgelab.state.bus import StateBus


class TestDailyLossLock:
    def test_triggers_at_exactly_two_percent(self, config, state):
        state.today = "2026-07-20"
        state.daily_pnl = -200.0
        state.daily_start_equity = 10000.0
        cb = CircuitBreakers(config, state)
        assert cb.daily_loss_lock_active(datetime(2026, 7, 20, 12, 0)) is True

    def test_does_not_trigger_below_two_percent(self, config, state):
        state.today = "2026-07-20"
        state.daily_pnl = -100.0
        state.daily_start_equity = 10000.0
        cb = CircuitBreakers(config, state)
        assert cb.daily_loss_lock_active(datetime(2026, 7, 20, 12, 0)) is False

    def test_no_lock_when_pnl_positive(self, config, state):
        state.today = "2026-07-20"
        state.daily_pnl = 50.0
        state.daily_start_equity = 10000.0
        cb = CircuitBreakers(config, state)
        assert cb.daily_loss_lock_active(datetime(2026, 7, 20, 12, 0)) is False


class TestTotalDDLock:
    def test_triggers_at_exactly_five_percent(self, config, state):
        state.equity = 9500.0
        state.peak_equity = 10000.0
        cb = CircuitBreakers(config, state)
        assert cb.total_dd_lock_active() is True

    def test_does_not_trigger_below_five_percent(self, config, state):
        state.equity = 9600.0
        state.peak_equity = 10000.0
        cb = CircuitBreakers(config, state)
        assert cb.total_dd_lock_active() is False

    def test_no_lock_when_equity_above_peak(self, config, state):
        state.equity = 10500.0
        state.peak_equity = 10000.0
        cb = CircuitBreakers(config, state)
        assert cb.total_dd_lock_active() is False

    def test_no_lock_when_peak_zero(self, config, state):
        state.equity = 0.0
        state.peak_equity = 0.0
        cb = CircuitBreakers(config, state)
        assert cb.total_dd_lock_active() is False


class TestCircuitBreakerStatus:
    def test_active_when_set(self, config, state):
        cb = CircuitBreakers(config, state)
        cb.circuit_breaker_active_status["s1"] = True
        assert cb.circuit_breaker_active("s1") is True

    def test_inactive_by_default(self, config, state):
        cb = CircuitBreakers(config, state)
        assert cb.circuit_breaker_active("s2") is False
