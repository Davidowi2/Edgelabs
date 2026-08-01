"""Circuit breaker for EdgeLab (Phase 8, Module 3).

Three-state machine (CLOSED, OPEN, HALF_OPEN) tracking consecutive submission
failures. Opens after a threshold of consecutive failures, recovers via probe
successes, and prevents retry storms by cooling down. Uses an injectable time
function for deterministic testing. Pure standard library only.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional


class CircuitState(str, Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


@dataclass
class CircuitConfig:
    failure_threshold: int = 5
    cooldown_ms: int = 30000
    half_open_probe_count: int = 2

    def __post_init__(self):
        self.failure_threshold = int(self.failure_threshold)
        self.cooldown_ms = int(self.cooldown_ms)
        self.half_open_probe_count = int(self.half_open_probe_count)


class CircuitBreaker:
    def __init__(self, config: CircuitConfig, logger,
                 time_fn: Optional[Callable[[], float]] = None) -> None:
        self._cfg = config
        self._logger = logger
        self._time_fn = time_fn or self._default_time
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._open_time: Optional[float] = None

    def _default_time(self) -> float:
        import time
        return time.time() * 1000.0  # milliseconds

    # ---------- queries ----------
    def allow_request(self) -> bool:
        if self._state == CircuitState.CLOSED:
            return True
        if self._state == CircuitState.HALF_OPEN:
            return True
        # OPEN
        if self._elapsed_since_open() >= self._cfg.cooldown_ms:
            self._transition_to(CircuitState.HALF_OPEN)
            return True
        return False

    def get_state(self) -> CircuitState:
        return self._state

    def get_failure_count(self) -> int:
        return self._failure_count

    def get_success_count(self) -> int:
        return self._success_count

    def _elapsed_since_open(self) -> float:
        if self._open_time is None:
            return 0.0
        return self._time_fn() - self._open_time

    # ---------- mutations ----------
    def record_success(self) -> None:
        if self._state == CircuitState.CLOSED:
            # a success in closed state resets any prior failure streak
            self._failure_count = 0
            self._success_count = 0
            return
        if self._state == CircuitState.HALF_OPEN:
            self._success_count += 1
            if self._success_count >= self._cfg.half_open_probe_count:
                self._transition_to(CircuitState.CLOSED)
                self._failure_count = 0
                self._success_count = 0

    def record_failure(self) -> None:
        if self._state == CircuitState.OPEN:
            # already in fault state; no-op
            return
        if self._state == CircuitState.CLOSED:
            self._failure_count += 1
            if self._failure_count >= self._cfg.failure_threshold:
                self._transition_to(CircuitState.OPEN)
                self._open_time = self._time_fn()
        elif self._state == CircuitState.HALF_OPEN:
            # a single failure during half-open trips it open again
            self._transition_to(CircuitState.OPEN)
            self._open_time = self._time_fn()
            self._success_count = 0

    def reset(self) -> None:
        self._transition_to(CircuitState.CLOSED)
        self._failure_count = 0
        self._success_count = 0
        self._open_time = None

    def _transition_to(self, new_state: CircuitState) -> None:
        old = self._state
        self._state = new_state
        self._logger.info("circuit breaker transition",
                         from_state=old.value, to_state=new_state.value)
