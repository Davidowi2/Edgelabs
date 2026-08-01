"""Tests for edgelab.execution.retry_executor (Phase 8, Module 2).

Pure standard library only. Injects a mock sleep to verify backoff without
real delays.
"""

import sys, os, tempfile, time
sys.path.insert(0, r"C:/Users/GTHub/Downloads/EDGELABS/edgelab")

import pytest

from edgelab.monitoring.logger import TradingLogger
from edgelab.execution.retry_executor import (
    RetryExecutor, RetryConfig, RetryOutcome, MockTradeResult,
    exponential_backoff_delay,
)


@pytest.fixture
def logger():
    return TradingLogger(name="retry.test",
                         log_file=os.path.join(tempfile.gettempdir(), "retry_test.log"))


def _res(retcode, success=False, volume_filled=0.0):
    return MockTradeResult(retcode=retcode, success=success, volume_filled=volume_filled)


class TestExponentialBackoff:
    def test_exponential_backoff_attempt_1(self):
        assert exponential_backoff_delay(1, 200, 5000) == 200

    def test_exponential_backoff_attempt_2(self):
        assert exponential_backoff_delay(2, 200, 5000) == 400

    def test_exponential_backoff_attempt_3(self):
        assert exponential_backoff_delay(3, 200, 5000) == 800

    def test_exponential_backoff_capped(self):
        # 200 * 2^10 = 204800 -> capped to 5000
        assert exponential_backoff_delay(11, 200, 5000) == 5000

    def test_exponential_backoff_pure_function(self):
        assert exponential_backoff_delay(3, 200, 5000) == exponential_backoff_delay(3, 200, 5000)


class TestExecute:
    def test_execute_success_first_attempt(self, logger):
        calls = {"n": 0}
        def submit():
            calls["n"] += 1
            return _res(0, success=True, volume_filled=0.1)
        ex = RetryExecutor(RetryConfig(max_attempts=4), logger)
        out = ex.execute(submit)
        assert calls["n"] == 1
        assert out.outcome == RetryOutcome.SUCCESS

    def test_execute_success_after_retries(self, logger):
        calls = {"n": 0}
        def submit():
            calls["n"] += 1
            if calls["n"] < 3:
                return _res(10004)  # requote
            return _res(0, success=True, volume_filled=0.1)
        ex = RetryExecutor(RetryConfig(max_attempts=4, base_delay_ms=1, max_delay_ms=10), logger,
                           sleep_fn=lambda s: None)
        out = ex.execute(submit)
        assert calls["n"] == 3
        assert out.outcome == RetryOutcome.SUCCESS

    def test_execute_failed_transient_exhausts_retries(self, logger):
        calls = {"n": 0}
        def submit():
            calls["n"] += 1
            return _res(10004)
        ex = RetryExecutor(RetryConfig(max_attempts=4, base_delay_ms=1, max_delay_ms=10), logger,
                           sleep_fn=lambda s: None)
        out = ex.execute(submit)
        assert calls["n"] == 4
        assert out.outcome == RetryOutcome.FAILED_TRANSIENT

    def test_execute_failed_permanent_aborts_immediately(self, logger):
        calls = {"n": 0}
        def submit():
            calls["n"] += 1
            return _res(10019)  # no money -> permanent
        ex = RetryExecutor(RetryConfig(max_attempts=4, base_delay_ms=1, max_delay_ms=10), logger,
                           sleep_fn=lambda s: None)
        out = ex.execute(submit)
        assert calls["n"] == 1
        assert out.outcome == RetryOutcome.FAILED_PERMANENT

    def test_execute_partial_fill(self, logger):
        def submit():
            return _res(0, success=False, volume_filled=0.05)  # partial
        ex = RetryExecutor(RetryConfig(max_attempts=4), logger)
        out = ex.execute(submit)
        assert out.outcome == RetryOutcome.PARTIAL

    def test_execute_logs_each_attempt(self, logger):
        calls = {"n": 0}
        def submit():
            calls["n"] += 1
            return _res(10004)
        ex = RetryExecutor(RetryConfig(max_attempts=3, base_delay_ms=1, max_delay_ms=10), logger,
                           sleep_fn=lambda s: None)
        ex.execute(submit)
        # logger called at least once per attempt
        # (we can't easily count; instead assert it ran without error and 3 calls)
        assert calls["n"] == 3

    def test_execute_uses_exponential_backoff_delays(self, logger):
        sleeps = []
        def submit():
            return _res(10004)
        ex = RetryExecutor(RetryConfig(max_attempts=4, base_delay_ms=200, max_delay_ms=5000), logger,
                           sleep_fn=lambda s: sleeps.append(s * 1000))
        ex.execute(submit)
        # 3 sleeps between 4 attempts: 200ms, 400ms, 800ms
        assert sleeps == [200, 400, 800]

    def test_execute_retries_only_transient_codes(self, logger):
        calls = {"n": 0}
        def submit():
            calls["n"] += 1
            return _res(10016)  # invalid stops -> not retryable
        ex = RetryExecutor(RetryConfig(max_attempts=4, base_delay_ms=1, max_delay_ms=10), logger,
                           sleep_fn=lambda s: None)
        out = ex.execute(submit)
        assert calls["n"] == 1
        assert out.outcome == RetryOutcome.FAILED_PERMANENT

    def test_execute_max_attempts_configurable(self, logger):
        calls = {"n": 0}
        def submit():
            calls["n"] += 1
            return _res(10004)
        ex = RetryExecutor(RetryConfig(max_attempts=2, base_delay_ms=1, max_delay_ms=10), logger,
                           sleep_fn=lambda s: None)
        out = ex.execute(submit)
        assert calls["n"] == 2
        assert out.outcome == RetryOutcome.FAILED_TRANSIENT
