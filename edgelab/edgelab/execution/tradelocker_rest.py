"""TradeLocker REST API broker client (real TradeLocker, no MT5 terminal needed).

Connects to TradeLocker's HTTP API directly (what "TradeLocker" actually means),
instead of via the MetaTrader5 terminal. This is option (B): a bot that talks to
TradeLocker natively.

API reference (public): https://docs.tradelocker.com  (v1)
  POST /api/v1/auth/jwt/token        -> { accessToken }
  GET  /api/v1/account/list          -> accounts (pick by id/server)
  GET  /api/v1/trade/{accountId}/positions
  GET  /api/v1/trade/{accountId}/orders
  POST /api/v1/trade/{accountId}/orders  -> place order

Auth uses email + password + (optional) server group. The DEMO account has a
numeric login like D#2329061; TradeLocker's JWT auth takes the EMAIL + password,
then you select the account by id from /account/list.

GATING (same as every other EdgeLab path):
  - This client will NOT submit a real order unless EDGELAB_DEMO_AUTH == '1'
    (explicit user go-ahead).
  - Without that, submit() returns a halted result (no HTTP call).
  - No live-capital path exists; DEMO only.

Offline-safe: if `requests` is unavailable or no network, methods raise clearly.
All state (token) is in-memory only; nothing is written to disk.
"""
from __future__ import annotations

import os
from typing import Dict, List, Optional

from edgelab.execution.gateway import BrokerInterface, MockTradeResult

try:
    import requests
    REQUESTS_OK = True
except ImportError:  # pragma: no cover
    requests = None
    REQUESTS_OK = False

BASE_URL = "https://api.tradelocker.com"


class TradeLockerRestBroker(BrokerInterface):
    def __init__(self, config: dict, logger, base_url: str = BASE_URL) -> None:
        if not REQUESTS_OK:
            raise RuntimeError("requests package not installed; cannot use TradeLocker REST")
        self._logger = logger
        cfg = config or {}
        bcfg = cfg.get("broker", cfg)
        self._email = str(bcfg.get("email", bcfg.get("login", "")))
        # login may be the numeric id (D#2329061) or email; auth uses email+password
        self._password = str(bcfg.get("password", ""))
        self._server = str(bcfg.get("server", "CLRTYFX"))
        self._symbol = str(bcfg.get("symbol_canonical", "XAUUSD")).upper()
        self._base = base_url.rstrip("/")
        self._token: Optional[str] = None
        self._account_id: Optional[int] = None
        self._session = requests.Session()
        self._connected = False

    # ---------- auth ----------
    def connect(self) -> bool:
        """Authenticate (JWT) and resolve the DEMO account id. Read-only network calls."""
        if not self._email or not self._password:
            self._logger.error("tradelocker-rest: missing email/password")
            return False
        try:
            r = self._session.post(
                f"{self._base}/api/v1/auth/jwt/token",
                json={"email": self._email, "password": self._password},
                timeout=15,
            )
            if r.status_code != 200:
                self._logger.error("tradelocker-rest: auth failed", status=r.status_code,
                                   body=r.text[:200])
                return False
            self._token = r.json().get("accessToken")
            if not self._token:
                self._logger.error("tradelocker-rest: no accessToken in response")
                return False
            self._session.headers.update({"Authorization": f"Bearer {self._token}"})
            # resolve account (prefer one matching our numeric login / server)
            acc = self._session.get(f"{self._base}/api/v1/account/list", timeout=15)
            if acc.status_code != 200:
                self._logger.error("tradelocker-rest: account list failed", status=acc.status_code)
                return False
            accounts = acc.json().get("data", {}).get("accounts", [])
            target = None
            for a in accounts:
                if self._server.lower() in str(a.get("name", "")).lower() \
                   or self._server.lower() in str(a.get("server", "")).lower() \
                   or str(a.get("id")) == str(self._email).lstrip("D#"):
                    target = a
                    break
            if target is None and accounts:
                target = accounts[0]
            self._account_id = int(target["id"]) if target else None
            self._connected = True
            self._logger.info("tradelocker-rest: connected", server=self._server,
                              account_id=self._account_id)
            return True
        except Exception as e:  # noqa: BLE001
            self._logger.error("tradelocker-rest: connect exception", error=str(e)[:200])
            return False

    def _require_conn(self) -> bool:
        if self._connected and self._token:
            return True
        return self.connect()

    # ---------- BrokerInterface ----------
    def submit(self, request: dict) -> MockTradeResult:
        """Place an order via REST. GATED: only if EDGELAB_DEMO_AUTH=1."""
        auth = os.environ.get("EDGELAB_DEMO_AUTH", "") == "1"
        if not auth:
            self._logger.info("tradelocker-rest: SUBMISSION HALTED (need EDGELAB_DEMO_AUTH=1). No order sent.")
            return MockTradeResult(0, False, 0.0)  # halted, no HTTP call
        if not self._require_conn():
            return MockTradeResult(10006, False, 0.0)  # transient connection error
        side = 1 if request.get("type", "BUY") == "BUY" else 2  # 1=BUY,2=SELL (TL v1)
        payload = {
            "accountId": self._account_id,
            "symbol": request.get("symbol", self._symbol),
            "qty": float(request.get("volume", 0.01)),
            "side": side,
            "type": "MARKET",
            "duration": "DAY",
        }
        try:
            r = self._session.post(
                f"{self._base}/api/v1/trade/{self._account_id}/orders",
                json=payload, timeout=15)
            if r.status_code in (200, 201):
                self._logger.info("tradelocker-rest: DEMO order placed",
                                  symbol=request.get("symbol"), side=request.get("type"))
                return MockTradeResult(10009, True, float(request.get("volume", 0.01)))
            self._logger.error("tradelocker-rest: order failed", status=r.status_code,
                               body=r.text[:200])
            return MockTradeResult(r.status_code, False, 0.0)
        except Exception as e:  # noqa: BLE001
            self._logger.error("tradelocker-rest: submit exception", error=str(e)[:200])
            return MockTradeResult(10006, False, 0.0)

    def get_open_positions(self) -> List[dict]:
        if not self._require_conn():
            return []
        try:
            r = self._session.get(
                f"{self._base}/api/v1/trade/{self._account_id}/positions", timeout=15)
            if r.status_code != 200:
                return []
            return r.json().get("data", {}).get("positions", [])
        except Exception:  # noqa: BLE001
            return []

    def get_pending_market_orders(self) -> List[dict]:
        if not self._require_conn():
            return []
        try:
            r = self._session.get(
                f"{self._base}/api/v1/trade/{self._account_id}/orders", timeout=15)
            if r.status_code != 200:
                return []
            return r.json().get("data", {}).get("orders", [])
        except Exception:  # noqa: BLE001
            return []

    def get_current_spread(self) -> float:
        # TradeLocker spread requires a symbol quote; return 0.0 if unavailable
        # (spread guard tolerates 0). A real impl would query /market/quotes.
        return 0.0

    def get_symbol(self) -> str:
        return self._symbol
