"""Tests for edgelab.execution.tradelocker_broker.TradeLockerBroker (Phase 9b, Module 2).

The MetaTrader5 package is NOT installed in CI. These tests inject a fake
`mt5` module and force MT5_AVAILABLE=True so the real mapping logic is
exercised without a broker. Pure standard library only.
"""

import sys, os, tempfile
sys.path.insert(0, r"C:/Users/GTHub/Downloads/EDGELABS/edgelab")

import pytest

from edgelab.monitoring.logger import TradingLogger
from edgelab.execution.mock_broker import MockBroker
from edgelab.execution.tradelocker_broker import (
    TradeLockerBroker, MT5NotAvailableError, ConnectionError as BrokerConnectionError,
)
from edgelab.execution.retry_executor import MockTradeResult


@pytest.fixture
def logger():
    return TradingLogger(name="tl.test",
                         log_file=os.path.join(tempfile.gettempdir(), "tl_test.log"))


# ---- a fake MT5 module ----
class _FakeResult:
    def __init__(self, retcode, volume=0.0, deal=0):
        self.retcode = retcode
        self.volume = volume
        self.deal = deal


class _FakeTick:
    def __init__(self, ask, bid):
        self.ask = ask
        self.bid = bid


class _FakePos:
    def __init__(self, symbol, magic, ticket=1, volume=0.1):
        self.symbol = symbol
        self.magic = magic
        self.ticket = ticket
        self.volume = volume


class _FakeOrder:
    def __init__(self, symbol, magic, order_type, position_id=0, ticket=1, volume=0.1):
        self.symbol = symbol
        self.magic = magic
        self.type = order_type
        self.position_id = position_id
        self.ticket = ticket
        self.volume = volume


class _FakeMT5:
    TRADE_ACTION_DEAL = "DEAL"
    TRADE_ACTION_SLTP = "SLTP"
    TRADE_ACTION_PENDING = "PENDING"
    ORDER_TYPE_BUY = "BUY"
    ORDER_TYPE_SELL = "SELL"
    ORDER_TYPE_BUY_LIMIT = "BUY_LIMIT"
    ORDER_FILLING_RETURN = "FILLING_RETURN"
    ORDER_TIME_GTC = "GTC"
    TRADE_RETCODE_DONE = 10009
    TRADE_RETCODE_DONE_PARTIAL = 10010
    TRADE_RETCODE_REQUOTE = 10004
    TRADE_RETCODE_CONNECTION = 10006
    TRADE_RETCODE_NO_MONEY = 10019
    TRADE_RETCODE_INVALID_STOPS = 10016
    TRADE_RETCODE_INVALID_PRICE = 10018
    ORDER_PROP_POSITION_ID = "position_id"

    def __init__(self):
        self._connected = False
        self.last_err = 0
        self.sent = []
        self.positions = []
        self.orders = []
        self.tick = _FakeTick(2001.0, 2000.0)
        self.init_ok = True

    def initialize(self, login=None, password=None, server=None, timeout=None):
        if self.init_ok:
            self._connected = True
            return True
        self.last_err = 10006
        return False

    def shutdown(self):
        self._connected = False

    def last_error(self):
        return self.last_err

    def order_send(self, request):
        self.sent.append(request)
        return _FakeResult(10009, volume=request.get("volume", 0.1))

    def positions_get(self, symbol=None):
        return [p for p in self.positions if symbol is None or p.symbol == symbol]

    def orders_get(self, symbol=None):
        return [o for o in self.orders if symbol is None or o.symbol == symbol]

    def symbol_info_tick(self, symbol):
        return self.tick


@pytest.fixture
def fake_mt5(monkeypatch):
    fake = _FakeMT5()
    import edgelab.execution.tradelocker_broker as tlb
    monkeypatch.setattr(tlb, "mt5", fake)
    monkeypatch.setattr(tlb, "MT5_AVAILABLE", True)
    return fake


def _config(**kw):
    base = {
        "login": 123456, "password": "secret", "server": "TradeLocker-Demo",
        "symbol_canonical": "XAUUSD", "magic_number": 9001,
        "timeout_ms": 5000, "retry_on_error": True,
    }
    base.update(kw)
    return base


# ---- availability ----
def test_mt5_not_available_raises(logger, monkeypatch):
    import edgelab.execution.tradelocker_broker as tlb
    monkeypatch.setattr(tlb, "MT5_AVAILABLE", False)
    monkeypatch.setattr(tlb, "mt5", None)
    with pytest.raises(MT5NotAvailableError):
        TradeLockerBroker(_config(), logger)


# ---- connection ----
def test_connect_success(logger, fake_mt5):
    b = TradeLockerBroker(_config(), logger)
    assert b.connect() is True
    assert b._connected is True


def test_connect_failure_raises(logger, fake_mt5):
    fake_mt5.init_ok = False
    b = TradeLockerBroker(_config(), logger)
    with pytest.raises(BrokerConnectionError):
        b.connect()


def test_disconnect_calls_shutdown(logger, fake_mt5):
    b = TradeLockerBroker(_config(), logger)
    b.connect()
    b.disconnect()
    assert b._connected is False


# ---- submit mapping ----
def test_submit_market_buy_maps_correctly(logger, fake_mt5):
    b = TradeLockerBroker(_config(), logger)
    b.connect()
    b.submit({"action": "DEAL", "symbol": "XAUUSD", "type": "BUY", "volume": 0.2,
              "price": 2000.0, "sl": 1990.0, "tp": 2020.0, "magic": 9001})
    req = fake_mt5.sent[-1]
    assert req["action"] == _FakeMT5.TRADE_ACTION_DEAL
    assert req["type"] == _FakeMT5.ORDER_TYPE_BUY
    assert req["symbol"] == "XAUUSD"  # resolved canonical
    assert req["volume"] == 0.2
    assert req["magic"] == 9001


def test_submit_market_sell_maps_correctly(logger, fake_mt5):
    b = TradeLockerBroker(_config(), logger)
    b.connect()
    b.submit({"action": "DEAL", "symbol": "XAUUSD", "type": "SELL", "volume": 0.15,
              "price": 2000.0, "sl": 2010.0, "tp": 1980.0, "magic": 9001})
    req = fake_mt5.sent[-1]
    assert req["type"] == _FakeMT5.ORDER_TYPE_SELL


def test_submit_returns_success_on_retcode_10009(logger, fake_mt5):
    fake_mt5.order_send = lambda r: _FakeResult(10009, volume=0.1)
    b = TradeLockerBroker(_config(), logger)
    b.connect()
    res = b.submit({"action": "DEAL", "symbol": "XAUUSD", "type": "BUY", "volume": 0.1})
    assert res.success is True
    assert res.retcode == 10009


def test_submit_returns_partial_on_retcode_10010(logger, fake_mt5):
    fake_mt5.order_send = lambda r: _FakeResult(10010, volume=0.05)
    b = TradeLockerBroker(_config(), logger)
    b.connect()
    res = b.submit({"action": "DEAL", "symbol": "XAUUSD", "type": "BUY", "volume": 0.1})
    assert res.success is False
    assert res.volume_filled == 0.05


def test_submit_returns_transient_on_retcode_10004(logger, fake_mt5):
    fake_mt5.order_send = lambda r: _FakeResult(10004)
    b = TradeLockerBroker(_config(), logger)
    b.connect()
    res = b.submit({"action": "DEAL", "symbol": "XAUUSD", "type": "BUY", "volume": 0.1})
    assert res.success is False
    assert res.retcode == 10004


def test_submit_returns_permanent_on_retcode_10019(logger, fake_mt5):
    fake_mt5.order_send = lambda r: _FakeResult(10019)
    b = TradeLockerBroker(_config(), logger)
    b.connect()
    res = b.submit({"action": "DEAL", "symbol": "XAUUSD", "type": "BUY", "volume": 0.1})
    assert res.success is False
    assert res.retcode == 10019


# ---- positions / orders ----
def test_get_open_positions_filters_by_magic(logger, fake_mt5):
    fake_mt5.positions = [
        _FakePos("XAUUSD", 9001, ticket=1),
        _FakePos("XAUUSD", 9999, ticket=2),
    ]
    b = TradeLockerBroker(_config(), logger)
    b.connect()
    pos = b.get_open_positions()
    assert len(pos) == 1
    assert pos[0]["magic"] == 9001


def test_get_pending_orders_excludes_sl_tp(logger, fake_mt5):
    fake_mt5.orders = [
        _FakeOrder("XAUUSD", 9001, _FakeMT5.ORDER_TYPE_BUY, position_id=0),   # pending market
        _FakeOrder("XAUUSD", 9001, _FakeMT5.ORDER_TYPE_BUY, position_id=55),  # SL/TP mod
    ]
    b = TradeLockerBroker(_config(), logger)
    b.connect()
    orders = b.get_pending_market_orders()
    assert len(orders) == 1
    assert orders[0]["position_id"] == 0


# ---- spread ----
def test_get_current_spread_returns_ask_minus_bid(logger, fake_mt5):
    fake_mt5.tick = _FakeTick(2001.5, 2000.0)
    b = TradeLockerBroker(_config(), logger)
    b.connect()
    # XAUUSD spread in points: (ask-bid)/point. point for gold = 0.01
    spread = b.get_current_spread()
    assert spread == pytest.approx((2001.5 - 2000.0) / 0.01)


def test_get_current_spread_returns_zero_on_error(logger, fake_mt5):
    fake_mt5.tick = None
    b = TradeLockerBroker(_config(), logger)
    b.connect()
    assert b.get_current_spread() == 0.0


# ---- resolution ----
def test_symbol_resolution_uses_resolver(logger, fake_mt5):
    b = TradeLockerBroker(_config(), logger)
    b.connect()
    assert b.get_symbol() == "XAUUSD"


# ---- reconnect ----
def test_ensure_connected_retries_once(logger, fake_mt5):
    b = TradeLockerBroker(_config(), logger)
    # not connected -> ensure_connected attempts one reconnect
    assert b._ensure_connected() is True
    assert b._connected is True


# ---- retcode mapping ----
def test_map_retcode_known_transient(logger, fake_mt5):
    b = TradeLockerBroker(_config(), logger)
    for rc in (10004, 10006, 10010, 10020, 10021, 10030):
        assert b._map_retcode(rc) == "FAILED_TRANSIENT"


def test_map_retcode_known_permanent(logger, fake_mt5):
    b = TradeLockerBroker(_config(), logger)
    for rc in (10016, 10018, 10019):
        assert b._map_retcode(rc) == "FAILED_PERMANENT"


def test_map_retcode_unknown_defaults_to_transient(logger, fake_mt5):
    b = TradeLockerBroker(_config(), logger)
    assert b._map_retcode(12345) == "FAILED_TRANSIENT"
