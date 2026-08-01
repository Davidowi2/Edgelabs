"""Tests for edgelab.execution.gateway (Phase 8, Module 4).

Pure standard library only. Composes SpreadGuard + RetryExecutor +
CircuitBreaker + submission safety against a MockBroker.
"""

import sys, os, tempfile
sys.path.insert(0, r"C:/Users/GTHub/Downloads/EDGELABS/edgelab")

from datetime import datetime, timezone

import pytest

from edgelab.monitoring.logger import TradingLogger
from edgelab.execution.spread_guard import SpreadGuard, SpreadSnapshot, SpreadVerdict
from edgelab.execution.retry_executor import (
    RetryExecutor, RetryConfig, RetryOutcome, MockTradeResult,
)
from edgelab.execution.circuit_breaker import (
    CircuitBreaker, CircuitConfig, CircuitState,
)
from edgelab.execution.gateway import (
    ExecutionGateway, GatewayResult, BrokerInterface, MockBroker,
)


@pytest.fixture
def logger():
    return TradingLogger(name="gw.test",
                         log_file=os.path.join(tempfile.gettempdir(), "gw_test.log"))


def _cfg(**kw):
    base = {
        "max_spread_points": 35.0,
        "shock_multiplier": 2.0,
        "elevated_multiplier": 1.5,
        "baseline_window": 60,
        "cooldown_after_shock_seconds": 900,
    }
    base.update(kw)
    return base


def _utc(hour, minute=0):
    return datetime(2026, 7, 20, hour, minute, tzinfo=timezone.utc)


class TestSubmitOrder:
    def test_submit_order_success(self, logger):
        broker = MockBroker(submit_fn=lambda r: MockTradeResult(0, True, 0.1))
        gw = ExecutionGateway({}, broker, logger)
        res = gw.submit_order({"symbol": "XAUUSD"})
        assert res == GatewayResult.SUCCESS

    def test_submit_order_partial(self, logger):
        broker = MockBroker(submit_fn=lambda r: MockTradeResult(0, False, 0.05))
        gw = ExecutionGateway({}, broker, logger)
        res = gw.submit_order({"symbol": "XAUUSD"})
        assert res == GatewayResult.PARTIAL
    def test_submit_order_spread_blocked(self, logger):
        # configure spread guard to shock: baseline ~10, broker reports 25
        sg = SpreadGuard(_cfg(), logger)
        for v in [10] * 12:
            sg.update_baseline(v)
        broker = MockBroker(submit_fn=lambda r: MockTradeResult(0, True, 0.1),
                            get_spread_fn=lambda: 25.0)
        gw = ExecutionGateway({}, broker, logger, spread_guard=sg)
        res = gw.submit_order({"symbol": "XAUUSD"})
        assert res == GatewayResult.SPREAD_BLOCKED
        assert broker.submit_calls == 0

    def test_submit_order_circuit_open(self, logger):
        clock = {"t": 0.0}
        cb = CircuitBreaker(CircuitConfig(failure_threshold=5, cooldown_ms=30000), logger,
                            time_fn=lambda: clock["t"])
        for _ in range(5):
            cb.record_failure()
        broker = MockBroker(submit_fn=lambda r: MockTradeResult(0, True, 0.1))
        gw = ExecutionGateway({}, broker, logger, circuit_br=cb)
        res = gw.submit_order({"symbol": "XAUUSD"})
        assert res == GatewayResult.CIRCUIT_OPEN
        assert broker.submit_calls == 0

    def test_submit_order_duplicate_blocked(self, logger):
        broker = MockBroker(
            submit_fn=lambda r: MockTradeResult(0, True, 0.1),
            get_positions_fn=lambda: [{"symbol": "XAUUSD", "magic": 0}],
        )
        gw = ExecutionGateway({"magic_number": 0, "max_position_count": 1}, broker, logger)
        res = gw.submit_order({"symbol": "XAUUSD"})
        assert res == GatewayResult.DUPLICATE_BLOCKED
        assert broker.submit_calls == 0

    def test_submit_order_transient_failure_eventually_succeeds(self, logger):
        calls = {"n": 0}
        def submit(r):
            calls["n"] += 1
            if calls["n"] < 3:
                return MockTradeResult(10004, False, 0.0)
            return MockTradeResult(0, True, 0.1)
        broker = MockBroker(submit_fn=submit)
        clock = {"t": 0.0}
        cb = CircuitBreaker(CircuitConfig(failure_threshold=5, cooldown_ms=30000), logger,
                            time_fn=lambda: clock["t"])
        gw = ExecutionGateway({}, broker, logger, circuit_br=cb,
                              retry_exec=RetryExecutor(RetryConfig(max_attempts=4, base_delay_ms=1,
                                                                   max_delay_ms=10), logger,
                                                        sleep_fn=lambda s: None))
        res = gw.submit_order({"symbol": "XAUUSD"})
        assert res == GatewayResult.SUCCESS
        # 2 transient failures count toward circuit; then success resets
        assert cb.get_failure_count() == 0
        assert cb.get_state() == CircuitState.CLOSED

    def test_submit_order_permanent_failure(self, logger):
        broker = MockBroker(submit_fn=lambda r: MockTradeResult(10019, False, 0.0))
        clock = {"t": 0.0}
        cb = CircuitBreaker(CircuitConfig(failure_threshold=5, cooldown_ms=30000), logger,
                            time_fn=lambda: clock["t"])
        gw = ExecutionGateway({}, broker, logger, circuit_br=cb,
                              retry_exec=RetryExecutor(RetryConfig(max_attempts=4, base_delay_ms=1,
                                                                   max_delay_ms=10), logger,
                                                        sleep_fn=lambda s: None))
        res = gw.submit_order({"symbol": "XAUUSD"})
        assert res == GatewayResult.FAILED_PERMANENT
        # permanent failure does NOT increment circuit failure count
        assert cb.get_failure_count() == 0

    def test_submit_order_circuit_opens_after_failures(self, logger):
        broker = MockBroker(submit_fn=lambda r: MockTradeResult(10004, False, 0.0))
        clock = {"t": 0.0}
        cb = CircuitBreaker(CircuitConfig(failure_threshold=5, cooldown_ms=30000), logger,
                            time_fn=lambda: clock["t"])
        gw = ExecutionGateway({}, broker, logger, circuit_br=cb,
                              retry_exec=RetryExecutor(RetryConfig(max_attempts=1, base_delay_ms=1,
                                                                   max_delay_ms=10), logger,
                                                        sleep_fn=lambda s: None))
        for _ in range(5):
            gw.submit_order({"symbol": "XAUUSD"})
        assert cb.get_state() == CircuitState.OPEN
        res = gw.submit_order({"symbol": "XAUUSD"})
        assert res == GatewayResult.CIRCUIT_OPEN

    def test_submit_order_spread_check_happens_before_circuit(self, logger):
        sg = SpreadGuard(_cfg(), logger)
        for v in [10] * 12:
            sg.update_baseline(v)
        broker = MockBroker(submit_fn=lambda r: MockTradeResult(0, True, 0.1),
                            get_spread_fn=lambda: 25.0)  # shock
        cb = CircuitBreaker(CircuitConfig(failure_threshold=5, cooldown_ms=30000), logger,
                            time_fn=lambda: 0.0)
        gw = ExecutionGateway({}, broker, logger, spread_guard=sg, circuit_br=cb)
        res = gw.submit_order({"symbol": "XAUUSD"})
        assert res == GatewayResult.SPREAD_BLOCKED
        # circuit never touched
        assert cb.get_failure_count() == 0

    def test_submit_order_circuit_check_before_broker(self, logger):
        clock = {"t": 0.0}
        cb = CircuitBreaker(CircuitConfig(failure_threshold=5, cooldown_ms=30000), logger,
                            time_fn=lambda: clock["t"])
        for _ in range(5):
            cb.record_failure()
        broker = MockBroker(submit_fn=lambda r: MockTradeResult(0, True, 0.1))
        gw = ExecutionGateway({}, broker, logger, circuit_br=cb)
        res = gw.submit_order({"symbol": "XAUUSD"})
        assert res == GatewayResult.CIRCUIT_OPEN
        assert broker.submit_calls == 0

    def test_submit_order_duplicate_check_before_circuit(self, logger):
        broker = MockBroker(
            submit_fn=lambda r: MockTradeResult(0, True, 0.1),
            get_positions_fn=lambda: [{"symbol": "XAUUSD", "magic": 0}],
        )
        clock = {"t": 0.0}
        cb = CircuitBreaker(CircuitConfig(failure_threshold=5, cooldown_ms=30000), logger,
                            time_fn=lambda: clock["t"])
        gw = ExecutionGateway({"magic_number": 0}, broker, logger, circuit_br=cb)
        res = gw.submit_order({"symbol": "XAUUSD"})
        assert res == GatewayResult.DUPLICATE_BLOCKED
        assert cb.get_failure_count() == 0


class TestIsSubmissionSafe:
    def test_is_submission_safe_no_positions(self, logger):
        broker = MockBroker(get_positions_fn=lambda: [])
        gw = ExecutionGateway({"magic_number": 0}, broker, logger)
        assert gw.is_submission_safe("XAUUSD") is True

    def test_is_submission_safe_with_matching_position(self, logger):
        broker = MockBroker(get_positions_fn=lambda: [{"symbol": "XAUUSD", "magic": 0}])
        gw = ExecutionGateway({"magic_number": 0}, broker, logger)
        assert gw.is_submission_safe("XAUUSD") is False

    def test_is_submission_safe_with_pending_order(self, logger):
        broker = MockBroker(
            get_positions_fn=lambda: [],
            get_pending_fn=lambda: [{"symbol": "XAUUSD", "magic": 0, "position_id": 0}],
        )
        gw = ExecutionGateway({"magic_number": 0}, broker, logger)
        assert gw.is_submission_safe("XAUUSD") is False

    def test_is_submission_safe_ignores_pending_sl_tp(self, logger):
        broker = MockBroker(
            get_positions_fn=lambda: [],
            get_pending_fn=lambda: [{"symbol": "XAUUSD", "magic": 0, "position_id": 123}],
        )
        gw = ExecutionGateway({"magic_number": 0}, broker, logger)
        assert gw.is_submission_safe("XAUUSD") is True

    def test_is_submission_safe_different_symbol(self, logger):
        broker = MockBroker(get_positions_fn=lambda: [{"symbol": "XAUUSD", "magic": 0}])
        gw = ExecutionGateway({"magic_number": 0}, broker, logger)
        assert gw.is_submission_safe("GBPUSD") is True

    def test_is_submission_safe_different_magic(self, logger):
        broker = MockBroker(get_positions_fn=lambda: [{"symbol": "XAUUSD", "magic": 7}])
        gw = ExecutionGateway({"magic_number": 0}, broker, logger)
        assert gw.is_submission_safe("XAUUSD") is True


class TestPassthrough:
    def test_get_spread_snapshot_passthrough(self, logger):
        sg = SpreadGuard(_cfg(), logger)
        for v in [10] * 12:
            sg.update_baseline(v)
        snap = sg.check_spread(12, _utc(10))
        gw = ExecutionGateway({}, MockBroker(), logger, spread_guard=sg)
        assert abs(gw.get_spread_snapshot().baseline_median - snap.baseline_median) < 1e-9

    def test_get_circuit_state_passthrough(self, logger):
        cb = CircuitBreaker(CircuitConfig(), logger, time_fn=lambda: 0.0)
        gw = ExecutionGateway({}, MockBroker(), logger, circuit_br=cb)
        assert gw.get_circuit_state() == CircuitState.CLOSED

    def test_reset_circuit_passthrough(self, logger):
        clock = {"t": 0.0}
        cb = CircuitBreaker(CircuitConfig(failure_threshold=5, cooldown_ms=30000), logger,
                            time_fn=lambda: clock["t"])
        for _ in range(5):
            cb.record_failure()
        gw = ExecutionGateway({}, MockBroker(), logger, circuit_br=cb)
        gw.reset_circuit()
        assert cb.get_state() == CircuitState.CLOSED


class TestLifecycle:
    def test_failure_kept_permanent_skips_circuit_count(self, logger):
        broker = MockBroker(submit_fn=lambda r: MockTradeResult(10019, False, 0.0))
        clock = {"t": 0.0}
        cb = CircuitBreaker(CircuitConfig(failure_threshold=5, cooldown_ms=30000), logger,
                            time_fn=lambda: clock["t"])
        gw = ExecutionGateway({}, broker, logger, circuit_br=cb,
                              retry_exec=RetryExecutor(RetryConfig(max_attempts=4, base_delay_ms=1,
                                                                   max_delay_ms=10), logger,
                                                        sleep_fn=lambda s: None))
        gw.submit_order({"symbol": "XAUUSD"})
        gw.submit_order({"symbol": "XAUUSD"})
        assert cb.get_failure_count() == 0
        assert cb.get_state() == CircuitState.CLOSED

    def test_full_lifecycle(self, logger):
        calls = {"n": 0}
        def submit(r):
            calls["n"] += 1
            seq = calls["n"]
            if seq in (1, 4, 6):
                return MockTradeResult(0, True, 0.1)
            return MockTradeResult(10004, False, 0.0)
        broker = MockBroker(submit_fn=submit)
        clock = {"t": 0.0}
        cb = CircuitBreaker(CircuitConfig(failure_threshold=5, cooldown_ms=30000,
                                          half_open_probe_count=2), logger,
                            time_fn=lambda: clock["t"])
        gw = ExecutionGateway({}, broker, logger, circuit_br=cb,
                              retry_exec=RetryExecutor(RetryConfig(max_attempts=4, base_delay_ms=1,
                                                                   max_delay_ms=10), logger,
                                                        sleep_fn=lambda s: None))
        assert gw.submit_order({"symbol": "XAUUSD"}) == GatewayResult.SUCCESS
        assert gw.submit_order({"symbol": "XAUUSD"}) == GatewayResult.SUCCESS
        assert gw.submit_order({"symbol": "XAUUSD"}) == GatewayResult.SUCCESS
        assert cb.get_state() == CircuitState.CLOSED
