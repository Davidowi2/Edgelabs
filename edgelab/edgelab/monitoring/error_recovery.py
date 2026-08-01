"""Error recovery for EdgeLab (Phase 1, Module 3).

Standard library only. Two layers:

  * Decorators (``safe_retry``, ``safe_default``) and the ``with_recovery``
    helper wrap any callable so a failure degrades gracefully instead of
    crashing the process.
  * ``CircuitBreaker`` stops hammering a dependency that is clearly down,
    then probes it again after a cool-off period.

Every failure is logged with a full traceback so the system "teaches" us what
broke (per the project's failing-is-a-teaching-method principle).
"""

from __future__ import annotations

import logging
import time
import traceback
from datetime import datetime, timezone
from typing import Any, Callable, Optional, Tuple, Type

logger = logging.getLogger(__name__)


class RecoveryError(Exception):
    """Raised/returned when recovery fails and the caller wants detail."""

    def __init__(self, original_error: Exception, operation_name: str, context: Optional[dict] = None) -> None:
        self.original_error = original_error
        self.operation_name = operation_name
        self.timestamp = datetime.now(timezone.utc)
        self.context = context or {}
        super().__init__(
            f"Recovery failed for '{operation_name}': {type(original_error).__name__}: {original_error}"
        )


class CircuitBreakerOpen(Exception):
    """Raised when the circuit breaker is OPEN and rejects a call."""


def safe_retry(
    max_attempts: int = 3,
    delay_seconds: float = 5,
    exceptions: Tuple[Type[BaseException], ...] = (Exception,),
    logger: Optional[logging.Logger] = None,
) -> Callable:
    log = logger or logging.getLogger("edgelab.recovery")

    def decorator(func: Callable) -> Callable:
        def wrapper(*args, **kwargs):
            last_exc: Optional[BaseException] = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as exc:  # type: ignore[misc]
                    last_exc = exc
                    log.error(
                        "safe_retry attempt failed",
                        extra={
                            "function": func.__name__,
                            "attempt": attempt,
                            "max_attempts": max_attempts,
                            "error": repr(exc),
                            "traceback": traceback.format_exc(),
                        },
                    )
                    if attempt < max_attempts:
                        time.sleep(delay_seconds)
            log.critical(
                "safe_retry exhausted",
                extra={"function": func.__name__, "max_attempts": max_attempts},
            )
            return None

        return wrapper

    return decorator


def safe_default(default_value: Any = None, logger: Optional[logging.Logger] = None) -> Callable:
    log = logger or logging.getLogger("edgelab.recovery")

    def decorator(func: Callable) -> Callable:
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as exc:  # noqa: BLE001 - intentional catch-all
                log.error(
                    "safe_default caught exception, returning default",
                    extra={
                        "function": func.__name__,
                        "default": repr(default_value),
                        "error": repr(exc),
                        "traceback": traceback.format_exc(),
                    },
                )
                return default_value

        return wrapper

    return decorator


def with_recovery(operation: Callable, fallback_value: Any, logger: Optional[logging.Logger] = None) -> Any:
    log = logger or logging.getLogger("edgelab.recovery")
    try:
        return operation()
    except Exception as exc:  # noqa: BLE001 - generic degradation
        log.error(
            "with_recovery caught exception, returning fallback",
            extra={"error": repr(exc), "fallback": repr(fallback_value), "traceback": traceback.format_exc()},
        )
        return fallback_value


class CircuitBreaker:
    """Classic circuit breaker: CLOSED -> OPEN -> HALF_OPEN -> CLOSED."""

    def __init__(self, failure_threshold: int, recovery_timeout_seconds: int, logger: Optional[logging.Logger] = None) -> None:
        self.failure_threshold = failure_threshold
        self.recovery_timeout_seconds = recovery_timeout_seconds
        self._logger = logger or logging.getLogger("edgelab.recovery")
        self.state = "CLOSED"
        self._failure_count = 0
        self._opened_at: Optional[float] = None

    def _transition(self, new_state: str) -> None:
        old = self.state
        self.state = new_state
        self._logger.info(
            "circuit_breaker_state_change",
            extra={"from": old, "to": new_state, "failure_count": self._failure_count},
        )

    def _maybe_recover(self) -> None:
        if self.state == "OPEN" and self._opened_at is not None:
            if (time.monotonic() - self._opened_at) >= self.recovery_timeout_seconds:
                self._transition("HALF_OPEN")

    def call(self, func: Callable, *args, **kwargs):
        self._maybe_recover()
        if self.state == "OPEN":
            self._logger.warning("circuit_breaker_rejected", extra={"state": self.state})
            raise CircuitBreakerOpen(f"Circuit breaker OPEN (failures={self._failure_count})")
        try:
            result = func(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001
            self._failure_count += 1
            self._logger.error(
                "circuit_breaker_call_failed",
                extra={"state": self.state, "failure_count": self._failure_count, "error": repr(exc)},
            )
            if self.state == "HALF_OPEN":
                self._transition("OPEN")
                self._opened_at = time.monotonic()
            elif self._failure_count >= self.failure_threshold:
                self._transition("OPEN")
                self._opened_at = time.monotonic()
            raise
        # success
        if self.state == "HALF_OPEN":
            self._failure_count = 0
            self._opened_at = None
            self._transition("CLOSED")
        return result
