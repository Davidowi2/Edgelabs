"""Tests for edgelab.execution.broker_factory.BrokerFactory (Phase 9b, Module 3).

The factory selects the broker implementation from config and ALWAYS returns a
working BrokerInterface (real or MockBroker). Pure standard library only.
"""

import sys, os, tempfile
sys.path.insert(0, r"C:/Users/GTHub/Downloads/EDGELABS/edgelab")

import pytest

from edgelab.monitoring.logger import TradingLogger
from edgelab.execution.broker_factory import BrokerFactory
from edgelab.execution.mock_broker import MockBroker
from edgelab.execution.tradelocker_broker import (
    TradeLockerBroker, MT5NotAvailableError,
    ConnectionError as BrokerConnectionError,
)


@pytest.fixture
def logger():
    return TradingLogger(name="fact.test",
                         log_file=os.path.join(tempfile.gettempdir(), "fact_test.log"))


@pytest.fixture
def fake_mt5(monkeypatch):
    """Force MT5 to appear available with a connectable fake."""
    import edgelab.execution.tradelocker_broker as tlb

    class _FakeMT5:
        TRADE_ACTION_DEAL = "DEAL"
        TRADE_ACTION_SLTP = "SLTP"
        ORDER_TYPE_BUY = "BUY"
        ORDER_TYPE_SELL = "SELL"
        ORDER_FILLING_RETURN = "FILLING_RETURN"
        ORDER_TIME_GTC = "GTC"
        TRADE_RETCODE_DONE = 10009

        def initialize(self, **kw):
            return True

        def shutdown(self):
            pass

        def last_error(self):
            return 0

        def order_send(self, r):
            class R:
                retcode = 10009
                volume = r.get("volume", 0.1)
                deal = 1
            return R()

        def positions_get(self, symbol=None):
            return []

        def orders_get(self, symbol=None):
            return []

        def symbol_info_tick(self, symbol):
            class T:
                ask = 2001.0
                bid = 2000.0
            return T()

    monkeypatch.setattr(tlb, "mt5", _FakeMT5())
    monkeypatch.setattr(tlb, "MT5_AVAILABLE", True)
    return _FakeMT5


def test_create_broker_default_returns_mock(logger):
    b = BrokerFactory.create_broker({}, logger)
    assert isinstance(b, MockBroker)


def test_create_broker_explicit_mock(logger):
    b = BrokerFactory.create_broker({"broker": {"mode": "mock"}}, logger)
    assert isinstance(b, MockBroker)


def test_create_broker_tradelocker_when_mt5_available(logger, fake_mt5):
    cfg = {"broker": {"mode": "tradelocker", "login": 1, "password": "x",
                      "server": "S", "symbol_canonical": "XAUUSD"}}
    b = BrokerFactory.create_broker(cfg, logger)
    assert isinstance(b, TradeLockerBroker)


def test_create_broker_falls_back_to_mock_when_mt5_missing(logger, monkeypatch):
    import edgelab.execution.tradelocker_broker as tlb
    monkeypatch.setattr(tlb, "MT5_AVAILABLE", False)
    monkeypatch.setattr(tlb, "mt5", None)
    cfg = {"broker": {"mode": "tradelocker", "login": 1, "password": "x", "server": "S"}}
    b = BrokerFactory.create_broker(cfg, logger)
    assert isinstance(b, MockBroker)


def test_create_broker_falls_back_on_connection_error(logger, fake_mt5, monkeypatch):
    import edgelab.execution.tradelocker_broker as tlb

    def _bad_connect(self):
        raise BrokerConnectionError("init failed")

    monkeypatch.setattr(TradeLockerBroker, "connect", _bad_connect)
    cfg = {"broker": {"mode": "tradelocker", "login": 1, "password": "x", "server": "S"}}
    b = BrokerFactory.create_broker(cfg, logger)
    assert isinstance(b, MockBroker)


def test_create_broker_never_raises(logger):
    b = BrokerFactory.create_broker({"broker": {"mode": "bogus"}}, logger)
    assert isinstance(b, MockBroker)
    b2 = BrokerFactory.create_broker({"broker": {}}, logger)
    assert isinstance(b2, MockBroker)


def test_create_broker_logs_mode(logger, caplog):
    import logging
    with caplog.at_level(logging.INFO):
        BrokerFactory.create_broker({"broker": {"mode": "mock"}}, logger)
    assert any("mock" in r.message.lower() for r in caplog.records)


def test_create_broker_passes_config_to_tradelocker(logger, fake_mt5):
    cfg = {"broker": {"mode": "tradelocker", "login": 555, "password": "pw",
                      "server": "TradeLocker-Demo", "symbol_canonical": "XAUUSD",
                      "magic_number": 9001}}
    b = BrokerFactory.create_broker(cfg, logger)
    assert isinstance(b, TradeLockerBroker)
    assert b._login == 555
    assert b._server == "TradeLocker-Demo"


def test_create_broker_passes_config_to_mock(logger):
    cfg = {"broker": {"mode": "mock", "magic_number": 42, "symbol": "XAUUSD"}}
    b = BrokerFactory.create_broker(cfg, logger)
    assert isinstance(b, MockBroker)
    assert b.get_symbol() == "XAUUSD"
