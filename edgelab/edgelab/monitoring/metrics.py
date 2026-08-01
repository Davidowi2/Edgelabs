"""Operational/system-health metrics for EdgeLab (Phase 1, Module 4).

These are NOT trade-performance metrics (those come later). They answer the
question "is the bot alive and healthy?": tick throughput, API latency/success,
error counts, news-block time, trades executed, uptime.

Every record is also emitted to the TradingLogger so anomalies are visible in
the log stream. Only the standard library is used.
"""

from __future__ import annotations

import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional

from edgelab.monitoring.logger import TradingLogger


class SystemMetrics:
    def __init__(self, logger: TradingLogger) -> None:
        self._logger = logger
        self._start_time = time.time()

        self._total_ticks = 0
        self._tick_timestamps: list[float] = []  # for rolling ticks/sec
        self._last_tick_ts: Optional[str] = None

        self._api_calls_total = 0
        self._api_calls_success = 0
        self._api_latency_sum_ms = 0.0

        self._errors_total = 0
        self._errors_by_component: dict[str, int] = defaultdict(int)
        self._errors_by_type: dict[str, int] = defaultdict(int)
        self._last_error_ts: Optional[str] = None

        self._news_blocks_total = 0
        self._news_blocked_minutes_total = 0

        self._trades_executed = 0

    # ----- recorders -----
    def record_tick(self) -> None:
        now = time.time()
        self._total_ticks += 1
        self._tick_timestamps.append(now)
        self._last_tick_ts = datetime.now(timezone.utc).isoformat()
        self._logger.debug("tick recorded", total_ticks=self._total_ticks)

    def record_api_call(self, endpoint: str, latency_ms: float, success: bool) -> None:
        self._api_calls_total += 1
        if success:
            self._api_calls_success += 1
        self._api_latency_sum_ms += latency_ms
        self._logger.debug(
            "api call", endpoint=endpoint, latency_ms=latency_ms, success=success
        )

    def record_error(self, component: str, error_type: str) -> None:
        self._errors_total += 1
        self._errors_by_component[component] += 1
        self._errors_by_type[error_type] += 1
        self._last_error_ts = datetime.now(timezone.utc).isoformat()
        self._logger.warning(
            "component error", component=component, error_type=error_type, total_errors=self._errors_total
        )

    def record_news_block(self, symbol: str, event_name: str, duration_minutes: int) -> None:
        self._news_blocks_total += 1
        self._news_blocked_minutes_total += duration_minutes
        self._logger.info(
            "news block", symbol=symbol, event=event_name, duration_minutes=duration_minutes
        )

    def record_trade_execution(self) -> None:
        self._trades_executed += 1
        self._logger.info("trade executed", total_trades=self._trades_executed)

    # ----- readers -----
    def _ticks_per_second(self) -> float:
        now = time.time()
        # keep ticks within the last 60 seconds
        cutoff = now - 60.0
        while self._tick_timestamps and self._tick_timestamps[0] < cutoff:
            self._tick_timestamps.pop(0)
        if not self._tick_timestamps:
            return 0.0
        span = max(now - self._tick_timestamps[0], 1e-9)
        return len(self._tick_timestamps) / span

    def get_uptime_seconds(self) -> int:
        return int(time.time() - self._start_time)

    def get_summary(self) -> dict:
        api_success_rate = (self._api_calls_success / self._api_calls_total) if self._api_calls_total else 0.0
        api_avg_latency = (self._api_latency_sum_ms / self._api_calls_total) if self._api_calls_total else 0.0
        return {
            "total_ticks": self._total_ticks,
            "ticks_per_second": round(self._ticks_per_second(), 4),
            "api_calls_total": self._api_calls_total,
            "api_success_rate": round(api_success_rate, 4),
            "api_avg_latency_ms": round(api_avg_latency, 4),
            "errors_total": self._errors_total,
            "errors_by_component": dict(self._errors_by_component),
            "errors_by_type": dict(self._errors_by_type),
            "news_blocks_total": self._news_blocks_total,
            "news_blocked_minutes_total": self._news_blocked_minutes_total,
            "trades_executed": self._trades_executed,
            "uptime_seconds": self.get_uptime_seconds(),
            "last_tick_ts": self._last_tick_ts,
            "last_error_ts": self._last_error_ts,
        }
