"""Tests for edgelab.execution.circuit_breaker (Phase 8, Module 3).

Pure standard library only. Injects a mock time function for deterministic
state-transition testing.
"""

import sys, os, tempfile
sys.path.insert(0, r"C:/Users/GTHub/Downloads/EDGELABS/edgelab")

import pytest

from edgelab.monitoring.logger import TradingLogger
from edgelab.execution.circuit_breaker import (
    CircuitBreaker, CircuitConfig, CircuitState,
)


@pytest.fixture
def logger():
    return TradingLogger(name="cb.test",
                         log_file=os.path.join(tempfile.gettempdir(), "cb_test.log"))


class TestStateMachine:
    def test_initial_state_is_closed(self, logger):
        cb = CircuitBreaker(CircuitConfig(), logger, time_fn=lambda: 1000.0)
        assert cb.get_state() == CircuitState.CLOSED

    def test_record_failure_increments_count(self, logger):
        cb = CircuitBreaker(CircuitConfig(failure_threshold=5), logger, time_fn=lambda: 0.0)
        cb.record_failure()
        assert cb.get_failure_count() == 1
        assert cb.get_state() == CircuitState.CLOSED

    def test_failures_below_threshold_stay_closed(self, logger):
        cb = CircuitBreaker(CircuitConfig(failure_threshold=5), logger, time_fn=lambda: 0.0)
        for _ in range(4):
            cb.record_failure()
        assert cb.get_state() == CircuitState.CLOSED
        assert cb.get_failure_count() == 4

    def test_threshold_reached_opens_circuit(self, logger):
        cb = CircuitBreaker(CircuitConfig(failure_threshold=5), logger, time_fn=lambda: 0.0)
        for _ in range(5):
            cb.record_failure()
        assert cb.get_state() == CircuitState.OPEN

    def test_open_circuit_blocks_requests(self, logger):
        cb = CircuitBreaker(CircuitConfig(failure_threshold=5, cooldown_ms=30000), logger,
                            time_fn=lambda: 0.0)
        for _ in range(5):
            cb.record_failure()
        assert cb.allow_request() is False

    def test_open_circuit_cooldown_elapses(self, logger):
        clock = {"t": 0.0}
        cb = CircuitBreaker(CircuitConfig(failure_threshold=5, cooldown_ms=30000), logger,
                            time_fn=lambda: clock["t"])
        for _ in range(5):
            cb.record_failure()
        # before cooldown
        clock["t"] = 10000.0  # 10s
        assert cb.allow_request() is False
        # after cooldown (30s)
        clock["t"] = 31000.0
        assert cb.allow_request() is True
        assert cb.get_state() == CircuitState.HALF_OPEN

    def test_open_circuit_cooldown_not_elapsed(self, logger):
        cb = CircuitBreaker(CircuitConfig(failure_threshold=5, cooldown_ms=30000), logger,
                            time_fn=lambda: 0.0)
        for _ in range(5):
            cb.record_failure()
        assert cb.allow_request() is False

    def test_half_open_records_success_closes_circuit(self, logger):
        clock = {"t": 0.0}
        cb = CircuitBreaker(CircuitConfig(failure_threshold=5, cooldown_ms=30000,
                                          half_open_probe_count=2), logger,
                            time_fn=lambda: clock["t"])
        for _ in range(5):
            cb.record_failure()
        clock["t"] = 31000.0
        cb.allow_request()  # -> HALF_OPEN
        cb.record_success()
        cb.record_success()
        assert cb.get_state() == CircuitState.CLOSED
        assert cb.get_failure_count() == 0
        assert cb.get_success_count() == 0

    def test_half_open_below_probe_count_stays_half_open(self, logger):
        clock = {"t": 0.0}
        cb = CircuitBreaker(CircuitConfig(failure_threshold=5, cooldown_ms=30000,
                                          half_open_probe_count=2), logger,
                            time_fn=lambda: clock["t"])
        for _ in range(5):
            cb.record_failure()
        clock["t"] = 31000.0
        cb.allow_request()
        cb.record_success()
        assert cb.get_state() == CircuitState.HALF_OPEN
        assert cb.get_success_count() == 1

    def test_half_open_failure_returns_to_open(self, logger):
        clock = {"t": 0.0}
        cb = CircuitBreaker(CircuitConfig(failure_threshold=5, cooldown_ms=30000,
                                          half_open_probe_count=2), logger,
                            time_fn=lambda: clock["t"])
        for _ in range(5):
            cb.record_failure()
        clock["t"] = 31000.0
        cb.allow_request()
        cb.record_failure()
        assert cb.get_state() == CircuitState.OPEN

    def test_success_in_closed_resets_count(self, logger):
        cb = CircuitBreaker(CircuitConfig(failure_threshold=5), logger, time_fn=lambda: 0.0)
        cb.record_failure()
        assert cb.get_failure_count() == 1
        cb.record_success()
        assert cb.get_failure_count() == 0

    def test_open_does_not_change_on_failure(self, logger):
        cb = CircuitBreaker(CircuitConfig(failure_threshold=5, cooldown_ms=30000), logger,
                            time_fn=lambda: 0.0)
        for _ in range(5):
            cb.record_failure()
        assert cb.get_state() == CircuitState.OPEN
        cb.record_failure()  # no-op
        assert cb.get_state() == CircuitState.OPEN

    def test_reset_forces_closed(self, logger):
        cb = CircuitBreaker(CircuitConfig(failure_threshold=5, cooldown_ms=30000), logger,
                            time_fn=lambda: 0.0)
        for _ in range(5):
            cb.record_failure()
        cb.reset()
        assert cb.get_state() == CircuitState.CLOSED
        assert cb.get_failure_count() == 0
        assert cb.get_success_count() == 0

    def test_time_function_is_used_for_cooldown(self, logger):
        clock = {"t": 0.0}
        cb = CircuitBreaker(CircuitConfig(failure_threshold=5, cooldown_ms=30000), logger,
                            time_fn=lambda: clock["t"])
        for _ in range(5):
            cb.record_failure()
        clock["t"] = 31000.0
        assert cb.allow_request() is True  # depends on time_fn returning 31000

    def test_uses_time_function_for_state_transitions(self, logger):
        clock = {"t": 0.0}
        cb = CircuitBreaker(CircuitConfig(failure_threshold=5, cooldown_ms=30000,
                                          half_open_probe_count=2), logger,
                            time_fn=lambda: clock["t"])
        for _ in range(5):
            cb.record_failure()
        clock["t"] = 40000.0
        assert cb.allow_request() is True
        assert cb.get_state() == CircuitState.HALF_OPEN

    def test_state_transitions_log(self, logger):
        # Smoke: transitions should not raise and should log. Advance clock
        # so the cooldown elapses and the half-open probe can close.
        clock = {"t": 0.0}
        cb = CircuitBreaker(CircuitConfig(failure_threshold=2, cooldown_ms=30000,
                                          half_open_probe_count=1), logger,
                            time_fn=lambda: clock["t"])
        cb.record_failure()
        cb.record_failure()       # -> OPEN
        clock["t"] = 40000.0      # past cooldown
        assert cb.allow_request() is True   # -> HALF_OPEN
        cb.record_success()       # -> CLOSED (probe_count=1)
        assert cb.get_state() == CircuitState.CLOSED

    def test_threshold_configurable(self, logger):
        cb = CircuitBreaker(CircuitConfig(failure_threshold=3), logger, time_fn=lambda: 0.0)
        for _ in range(3):
            cb.record_failure()
        assert cb.get_state() == CircuitState.OPEN
