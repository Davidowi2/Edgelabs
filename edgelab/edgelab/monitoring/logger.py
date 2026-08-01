"""Structured logging for EdgeLab (Phase 1, Module 2).

Uses only the Python standard library. Two simultaneous sinks:

  * Console  -> human-readable text (for live development / operator eyes).
  * File     -> one JSON object per line (machine-parseable for later analysis).

Trade events get dedicated methods (``trade`` / ``close_trade``) that guarantee
a stable field set plus a UUID4 ``trade_id`` so every fill can be correlated
across the log stream.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

_LEVELS = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class _JsonFileHandler(logging.Handler):
    """Write one JSON object per line to a date-stamped file."""

    def __init__(self, log_file: Path, name: str) -> None:
        super().__init__()
        self.name = name
        log_file.parent.mkdir(parents=True, exist_ok=True)
        self._path = log_file
        self._stream = open(self._path, "a", encoding="utf-8")

    def emit(self, record: logging.LogRecord) -> None:
        entry = {
            "timestamp_utc": _utc_iso(),
            "logger": self.name,
            "level": record.levelname,
            "message": record.getMessage(),
        }
        # Context pairs were stashed on the record by TradingLogger.
        ctx = getattr(record, "context", None)
        if isinstance(ctx, dict):
            entry.update(ctx)
        try:
            self._stream.write(json.dumps(entry, default=str) + "\n")
            self._stream.flush()
        except Exception:
            self.handleError(record)

    def close(self) -> None:
        try:
            self._stream.close()
        finally:
            super().close()


class TradingLogger:
    """Structured logger: JSON to file, text to console, plus trade helpers."""

    def __init__(self, name: str, log_file: str, level: str = "INFO") -> None:
        self.name = name
        self.log_file = Path(log_file)
        # Date-stamped filename: edgelab_2026-07-25.log
        stamped = self.log_file.parent / f"edgelab_{datetime.now(timezone.utc):%Y-%m-%d}.log"
        self.log_file = stamped

        # Unique logger per instance so concurrent/additive TradingLogger
        # objects never share handlers (logging loggers are process-global
        # singletons keyed by name).
        unique = f"edgelab.{name}.{id(self)}"
        self._logger = logging.getLogger(unique)
        for h in list(self._logger.handlers):
            self._logger.removeHandler(h)
            h.close()
        self._logger.setLevel(_LEVELS.get(level.upper(), logging.INFO))
        self._logger.propagate = False

        fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
        console = logging.StreamHandler()
        console.setFormatter(fmt)
        self._logger.addHandler(console)

        self._file_handler = _JsonFileHandler(self.log_file, name)
        self._logger.addHandler(self._file_handler)

    # ----- generic leveled logging -----
    def _log(self, level: str, msg: str, **context) -> None:
        extra = {"context": context}
        self._logger.log(_LEVELS[level], msg, extra=extra)

    def debug(self, msg: str, **context) -> None:
        self._log("DEBUG", msg, **context)

    def info(self, msg: str, **context) -> None:
        self._log("INFO", msg, **context)

    def warning(self, msg: str, **context) -> None:
        self._log("WARNING", msg, **context)

    def error(self, msg: str, **context) -> None:
        self._log("ERROR", msg, **context)

    def critical(self, msg: str, **context) -> None:
        self._log("CRITICAL", msg, **context)

    # ----- trade lifecycle -----
    def trade(self, entry: dict) -> dict:
        record = dict(entry)
        record["trade_id"] = str(uuid4())
        record["event"] = "trade_entry"
        # Preserve a caller-supplied timestamp; otherwise stamp with now.
        if "timestamp_utc" not in record:
            record["timestamp_utc"] = _utc_iso()
        self._log("INFO", "trade entry", **record)
        return record

    def close_trade(self, trade_id: str, exit_price: float, pnl: float, exit_reason: str) -> dict:
        record = {
            "trade_id": trade_id,
            "event": "trade_close",
            "exit_price": exit_price,
            "pnl": pnl,
            "exit_reason": exit_reason,
            "timestamp_utc": _utc_iso(),
        }
        self._log("INFO", "trade close", **record)
        return record

    def close(self) -> None:
        self._file_handler.close()
