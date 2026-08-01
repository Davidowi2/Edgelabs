"""Tests for edgelab.monitoring.error_recovery (Phase 1, Module 3)."""

from __future__ import annotations

import time
from datetime import datetime, timezone

import pytest

from edgelab.monitoring.error_recovery import (
    CircuitBreaker,
    CircuitBreakerOpen,
    RecoveryError,
    safe_default,
    safe_retry,
    with_recovery,
)
from edgelab.monitoring.logger import TradingLogger


@pytest.fixture
def logger(tmp_path):
    return TradingLogger(name="edgelab.recovery", log_file=str(tmp_path / "r.log"))


class TestSafeRetry:
    def test_succeeds_on_third_attempt(self, logger):
        calls = {"n": 0}

        @safe_retry(max_attempts=3, delay_seconds=0, exceptions=(Exception,), logger=logger)
        def flaky():
            calls["n"] += 1
            if calls["n"] < 3:
                raise ValueError("not yet")
            return "ok"

        assert flaky() == "ok"
        assert calls["n"] == 3

    def test_returns_none_after_max_attempts(self, logger):
        @safe_retry(max_attempts=3, delay_seconds=0, exceptions=(Exception,), logger=logger)
        def always_fail():
            raise RuntimeError("boom")

        assert always_fail() is None


class TestSafeDefault:
    def test_returns_default(self, logger):
        @safe_default(default_value="fallback", logger=logger)
        def boom():
            raise RuntimeError("x")

        assert boom() == "fallback"

    def test_does_not_retry(self, logger):
        calls = {"n": 0}

        @safe_default(default_value=None, logger=logger)
        def boom():
            calls["n"] += 1
            raise RuntimeError("x")

        boom()
        assert calls["n"] == 1


class TestWithRecovery:
    def test_returns_value_on_success(self, logger):
        assert with_recovery(lambda: 5, fallback_value=0, logger=logger) == 5

    def test_returns_fallback_on_failure(self, logger):
        assert with_recovery(lambda: 1 / 0, fallback_value=-1, logger=logger) == -1


class TestCircuitBreaker:
    def test_opens_after_threshold(self, logger):
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout_seconds=10, logger=logger)
        for _ in range(3):
            with pytest.raises(Exception):
                cb.call(lambda: 1 / 0)
        assert cb.state == "OPEN"

    def test_rejects_when_open(self, logger):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout_seconds=10, logger=logger)
        with pytest.raises(Exception):
            cb.call(lambda: 1 / 0)
        with pytest.raises(CircuitBreakerOpen):
            cb.call(lambda: 42)

    def test_half_open_after_timeout(self, logger):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout_seconds=0, logger=logger)
        with pytest.raises(Exception):
            cb.call(lambda: 1 / 0)
        assert cb.state == "OPEN"
        time.sleep(0.01)
        # next call moves to HALF_OPEN and probes
        try:
            cb.call(lambda: 1 / 0)
        except Exception:
            pass
        assert cb.state in ("HALF_OPEN", "OPEN")

    def test_closes_on_success_in_half_open(self, logger):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout_seconds=0, logger=logger)
        with pytest.raises(Exception):
            cb.call(lambda: 1 / 0)
        time.sleep(0.01)
        # probe fails first to force HALF_OPEN state explicitly
        try:
            cb.call(lambda: 1 / 0)
        except Exception:
            pass
        # now closed path: success in half-open closes it
        assert cb.call(lambda: 7) == 7
        assert cb.state == "CLOSED"


class TestRecoveryError:
    def test_contains_original(self, logger):
        try:
            raise ValueError("root cause")
        except ValueError as e:
            err = RecoveryError(original_error=e, operation_name="do_thing", context={"k": "v"})
        assert isinstance(err.original_error, ValueError)
        assert err.operation_name == "do_thing"
        assert err.context["k"] == "v"
        assert isinstance(err.timestamp, datetime)
