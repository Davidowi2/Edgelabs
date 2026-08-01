"""Tests for edgelab.monitoring.logger.TradingLogger (Phase 1, Module 2)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from edgelab.monitoring.logger import TradingLogger


@pytest.fixture
def log_file(tmp_path):
    return tmp_path / "logs" / "edgelab_2026-07-15.log"


def _last_json_line(logger) -> dict:
    lines = Path(logger.log_file).read_text(encoding="utf-8").strip().splitlines()
    return json.loads(lines[-1])


class TestCreation:
    def test_logger_creates_file(self, log_file):
        logger = TradingLogger(name="edgelab.test", log_file=str(log_file))
        logger.info("hello")
        assert Path(logger.log_file).exists()

    def test_log_directory_created(self, tmp_path):
        nested = tmp_path / "a" / "b" / "c" / "edgelab.log"
        logger = TradingLogger(name="edgelab.test", log_file=str(nested))
        logger.info("creating dirs")
        assert Path(logger.log_file).exists()
        assert Path(logger.log_file).parent.is_dir()


class TestJsonOutput:
    def test_logger_writes_json(self, log_file):
        logger = TradingLogger(name="edgelab.test", log_file=str(log_file))
        logger.info("a message")
        data = _last_json_line(logger)
        assert data["message"] == "a message"
        assert data["level"] == "INFO"

    def test_context_dict_becomes_fields(self, log_file):
        logger = TradingLogger(name="edgelab.test", log_file=str(log_file))
        logger.warning("anomaly", symbol="EURUSD", code=42)
        data = _last_json_line(logger)
        assert data["symbol"] == "EURUSD"
        assert data["code"] == 42

    def test_trade_entry_includes_all_fields(self, log_file):
        logger = TradingLogger(name="edgelab.test", log_file=str(log_file))
        entry = {
            "timestamp_broker": "2026-07-15T10:00:00",
            "timestamp_utc": "2026-07-15T07:00:00Z",
            "symbol": "EURUSD",
            "direction": "LONG",
            "entry_price": 1.1234,
            "stop_loss": 1.1200,
            "take_profit": 1.1300,
            "lot_size": 0.1,
            "risk_pct": 1.0,
            "strategy_id": "turtle",
            "reason": "breakout",
        }
        record = logger.trade(entry)
        data = _last_json_line(logger)
        for k in entry:
            assert data[k] == entry[k]
        assert "trade_id" in data
        assert record["trade_id"] == data["trade_id"]

    def test_close_trade_record(self, log_file):
        logger = TradingLogger(name="edgelab.test", log_file=str(log_file))
        logger.close_trade("abc-123", 1.1250, 12.5, "tp_hit")
        data = _last_json_line(logger)
        assert data["trade_id"] == "abc-123"
        assert data["exit_price"] == 1.1250
        assert data["pnl"] == 12.5
        assert data["exit_reason"] == "tp_hit"
        assert data["event"] == "trade_close"


class TestLevels:
    def test_level_filtering(self, log_file):
        logger = TradingLogger(name="edgelab.test", log_file=str(log_file), level="WARNING")
        logger.debug("dbg")  # filtered
        logger.info("inf")   # filtered
        logger.warning("war")
        logger.error("err")
        lines = Path(logger.log_file).read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 2
        levels = [json.loads(l)["level"] for l in lines]
        assert levels == ["WARNING", "ERROR"]
