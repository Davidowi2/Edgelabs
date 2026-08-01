"""TradeLocker MT5 broker connector for EdgeLab (Phase 9b, Module 2).

Concrete BrokerInterface implementation backed by the MetaTrader5 Python
package. The package is imported CONDITIONALLY: if it is not installed the
module sets MT5_AVAILABLE=False and TradeLockerBroker raises
MT5NotAvailableError at construction. The factory (Module 3) catches that and
falls back to MockBroker. Pure standard library + optional MetaTrader5.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from edgelab.monitoring.logger import TradingLogger
from edgelab.execution.gateway import BrokerInterface
from edgelab.execution.retry_executor import MockTradeResult
from edgelab.execution.symbol_resolver import SymbolResolver, SymbolNotFoundError


try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised only when MT5 is absent
    mt5 = None
    MT5_AVAILABLE = False


class MT5NotAvailableError(Exception):
    """Raised when TradeLockerBroker is built but MetaTrader5 is not installed."""


# Local alias so we do not shadow the builtin ConnectionError elsewhere.
class ConnectionError(Exception):
    """Raised when MT5 initialize() fails (login/server/network)."""


class TradeLockerBroker(BrokerInterface):
    def __init__(self, config: dict, logger: TradingLogger) -> None:
        if not MT5_AVAILABLE or mt5 is None:
            raise MT5NotAvailableError(
                "MetaTrader5 package is not installed; cannot build TradeLockerBroker. "
                "Falling back to MockBroker is the factory's job."
            )
        cfg = config or {}
        self._logger = logger
        self._login = int(cfg.get("login", 0))
        self._password = str(cfg.get("password", ""))
        self._server = str(cfg.get("server", ""))
        self._magic = int(cfg.get("magic_number", 9001))
        self._timeout_ms = int(cfg.get("timeout_ms", 5000))
        self._retry_on_error = bool(cfg.get("retry_on_error", True))
        self._point_size = float(cfg.get("point_size", 0.01))  # gold point size

        self._symbol_resolver = SymbolResolver(
            {"canonical_name": str(cfg.get("symbol_canonical", "XAUUSD")).upper()},
            logger)
        self._symbol_resolved = str(cfg.get("symbol_canonical", "XAUUSD")).upper()
        self._connected = False
        self._last_error = 0

    # ----- connection -----
    def connect(self) -> bool:
        if not MT5_AVAILABLE or mt5 is None:
            raise MT5NotAvailableError("MetaTrader5 is not available")
        ok = mt5.initialize(
            login=self._login, password=self._password,
            server=self._server, timeout=self._timeout_ms)
        if not ok:
            self._last_error = mt5.last_error()
            self._logger.error("mt5 initialize failed", error=self._last_error)
            raise ConnectionError(
                f"MT5 initialize failed (last_error={self._last_error})")
        # resolve the broker symbol eagerly so submit()/spread() use it
        try:
            self._symbol_resolved = self._symbol_resolver.resolve(self._symbol_resolved)
        except SymbolNotFoundError:
            # canonical is already the resolved name; keep it
            pass
        self._connected = True
        self._logger.info("mt5 connected", server=self._server, symbol=self._symbol_resolved)
        return True

    def disconnect(self) -> None:
        if MT5_AVAILABLE and mt5 is not None and self._connected:
            mt5.shutdown()
        self._connected = False

    def _ensure_connected(self) -> bool:
        if self._connected:
            return True
        if not self._retry_on_error:
            return False
        try:
            return self.connect()
        except (ConnectionError, MT5NotAvailableError):
            self._logger.warning("mt5 reconnect failed")
            return False

    # ----- submission -----
    def submit(self, request: dict) -> MockTradeResult:
        if not self._ensure_connected():
            return MockTradeResult(10006, False, 0.0)  # connection error -> transient

        action = request.get("action", "DEAL")
        order_type = request.get("type", "BUY")
        mt5_request = {
            "action": mt5.TRADE_ACTION_DEAL if action == "DEAL"
            else mt5.TRADE_ACTION_SLTP,
            "symbol": self._symbol_resolved,
            "volume": float(request.get("volume", 0.0)),
            "type": mt5.ORDER_TYPE_BUY if order_type == "BUY"
            else mt5.ORDER_TYPE_SELL,
            "price": float(request.get("price", 0.0)),
            "sl": float(request.get("sl", 0.0)),
            "tp": float(request.get("tp", 0.0)),
            "deviation": int(request.get("deviation", 10)),
            "magic": int(request.get("magic", self._magic)),
            "type_filling": mt5.ORDER_FILLING_RETURN,
            "type_time": mt5.ORDER_TIME_GTC,
            "comment": request.get("comment", "EdgeLab"),
        }
        result = mt5.order_send(mt5_request)
        self._last_error = result.retcode

        if result.retcode == 10009:  # TRADE_RETCODE_DONE
            return MockTradeResult(10009, True, float(result.volume))
        if result.retcode == 10010:  # DONE_PARTIAL -> partial fill
            return MockTradeResult(10010, False, float(result.volume))
        # everything else: classify via _map_retcode for the retry layer
        return MockTradeResult(result.retcode, False, float(result.volume))

    # ----- state reads -----
    def get_open_positions(self) -> List[dict]:
        if not self._ensure_connected():
            return []
        positions = mt5.positions_get(symbol=self._symbol_resolved) or []
        out = []
        for p in positions:
            if int(getattr(p, "magic", -1)) != self._magic:
                continue
            out.append({
                "symbol": getattr(p, "symbol", self._symbol_resolved),
                "magic": int(getattr(p, "magic", -1)),
                "ticket": int(getattr(p, "ticket", 0)),
                "position_id": int(getattr(p, "ticket", 0)),
                "volume": float(getattr(p, "volume", 0.0)),
            })
        return out

    def get_pending_market_orders(self) -> List[dict]:
        if not self._ensure_connected():
            return []
        orders = mt5.orders_get(symbol=self._symbol_resolved) or []
        market_types = (mt5.ORDER_TYPE_BUY, mt5.ORDER_TYPE_SELL)
        out = []
        for o in orders:
            if int(getattr(o, "magic", -1)) != self._magic:
                continue
            # a pending SL/TP modification carries a set position_id; a fresh
            # market order has position_id == 0
            pos_id = int(getattr(o, "position_id", 0))
            if getattr(o, "type", None) not in market_types:
                continue
            if pos_id != 0:
                continue
            out.append({
                "symbol": getattr(o, "symbol", self._symbol_resolved),
                "magic": int(getattr(o, "magic", -1)),
                "ticket": int(getattr(o, "ticket", 0)),
                "position_id": pos_id,
            })
        return out

    def get_current_spread(self) -> float:
        if not self._connected:
            return 0.0
        tick = mt5.symbol_info_tick(self._symbol_resolved)
        if tick is None:
            return 0.0
        return (float(tick.ask) - float(tick.bid)) / self._point_size

    def get_symbol(self) -> str:
        return self._symbol_resolved

    # ----- error classification -----
    def _map_retcode(self, mt5_retcode: int) -> str:
        permanent = {10016, 10018, 10019, 1, 2, 5}
        transient = {10004, 10006, 10010, 10020, 10021, 10030}
        if mt5_retcode in permanent:
            return "FAILED_PERMANENT"
        # 10009 (SUCCESS) and 10010 (PARTIAL) are handled by submit() directly;
        # if reached here via an explicit map call, transient is the safe bucket.
        if mt5_retcode in transient or mt5_retcode in (10009, 10010):
            return "FAILED_TRANSIENT"
        return "FAILED_TRANSIENT"
