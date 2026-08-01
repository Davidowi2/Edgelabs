"""Retry executor for EdgeLab (Phase 8, Module 2).

Wraps a single order submission with retry logic. Classifies broker return
codes as transient (retry) or permanent (abort). Exponential backoff between
retries. Pure standard library only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, List, Optional, Set


class RetryOutcome(str, Enum):
    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    FAILED_TRANSIENT = "FAILED_TRANSIENT"
    FAILED_PERMANENT = "FAILED_PERMANENT"


@dataclass
class RetryConfig:
    max_attempts: int = 4
    base_delay_ms: int = 200
    max_delay_ms: int = 5000
    retryable_codes: Set[int] = field(default_factory=lambda: {10004, 10006, 10010, 10020, 10021, 10030})

    def __post_init__(self):
        self.max_attempts = int(self.max_attempts)
        self.base_delay_ms = int(self.base_delay_ms)
        self.max_delay_ms = int(self.max_delay_ms)
        self.retryable_codes = set(int(c) for c in self.retryable_codes)


@dataclass
class MockTradeResult:
    retcode: int
    success: bool = False
    volume_filled: float = 0.0
    outcome: Optional[RetryOutcome] = None


def exponential_backoff_delay(attempt: int, base_ms: int, max_ms: int) -> int:
    """Pure exponential backoff: base_ms * 2^(attempt-1), capped at max_ms.

    attempt=1 -> base_ms; attempt=2 -> base_ms*2; attempt=3 -> base_ms*4 ...
    """
    if attempt < 1:
        attempt = 1
    delay = base_ms * (2 ** (attempt - 1))
    if delay > max_ms:
        return max_ms
    return delay


class RetryExecutor:
    def __init__(self, config: RetryConfig, logger,
                 sleep_fn: Optional[Callable[[float], None]] = None) -> None:
        self._cfg = config
        self._logger = logger
        self._sleep = sleep_fn or self._real_sleep
        self._default_codes = {10004, 10006, 10010, 10020, 10021, 10030}

    def _real_sleep(self, seconds: float) -> None:
        import time
        time.sleep(seconds)

    def execute(self, submit_fn: Callable[[], MockTradeResult]) -> MockTradeResult:
        retryable = self._cfg.retryable_codes or self._default_codes
        max_attempts = self._cfg.max_attempts
        last: Optional[MockTradeResult] = None

        for attempt in range(1, max_attempts + 1):
            result = submit_fn()
            last = result
            self._logger.info("retry attempt", attempt=attempt, retcode=result.retcode)

            if result.success:
                # full fill
                result.outcome = RetryOutcome.SUCCESS
                return result

            # partial fill -> return immediately (no retry on partials)
            if result.volume_filled and result.volume_filled > 0:
                result.outcome = RetryOutcome.PARTIAL
                return result

            # permanent failure -> abort immediately
            if result.retcode not in retryable:
                result.outcome = RetryOutcome.FAILED_PERMANENT
                self._logger.warning("permanent failure, aborting",
                                     retcode=result.retcode, attempt=attempt)
                return result

            # transient failure -> backoff and retry (unless last attempt)
            if attempt < max_attempts:
                delay_ms = exponential_backoff_delay(
                    attempt, self._cfg.base_delay_ms, self._cfg.max_delay_ms)
                self._logger.info("transient failure, backing off",
                                  retcode=result.retcode, delay_ms=delay_ms,
                                  next_attempt=attempt + 1)
                self._sleep(delay_ms / 1000.0)

        # exhausted retries -> failed_transient
        if last is not None:
            last.outcome = RetryOutcome.FAILED_TRANSIENT
        self._logger.error("retry attempts exhausted", max_attempts=max_attempts)
        return last
