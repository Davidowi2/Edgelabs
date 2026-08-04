"""Unit tests for the monitoring dashboard (offline, no network).

Covers: /api/state shape, the TradeLocker DEMO gate (refuses PRD/unknown/bare
CLRTYFX), the read-only connector behaviour against a MOCKED TradeLocker REST
(no real network; no real credentials), and that the connector never returns an
order-placement field. The dashboard is read-only by construction.
"""
from __future__ import annotations
import os, sys, types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from edgelab.dashboard import server as srv


class _FakeResp:
    def __init__(self, status, payload):
        self.status_code = status
        self._payload = payload
        self.text = str(payload)
    def json(self):
        return self._payload


class _FakeRequests:
    """Replays scripted REST responses; records that only GET is used after auth."""
    def __init__(self, script):
        self._script = list(script)
        self.calls = []  # (method, url)
    def post(self, url, **kw):
        self.calls.append(("POST", url))
        return self._next(url)
    def get(self, url, **kw):
        self.calls.append(("GET", url))
        return self._next(url)
    def _next(self, url):
        for i, (u, resp) in enumerate(self._script):
            if u in url:
                self._script.pop(i)
                return resp
        return _FakeResp(404, {})


def _install(requests_obj):
    srv.requests = requests_obj


def test_state_shape():
    s = srv.build_state()
    assert "updated" in s and "dd_budget_pct" in s
    assert "grader" in s and "verdict" in s["grader"]
    assert "sleeves" in s and "H5_equity" in s["sleeves"] and "H6_crypto" in s["sleeves"]
    assert isinstance(s["journal_rows"], int)


def test_demo_gated_no_creds(monkeypatch):
    for k in ("TL_EMAIL", "TL_PASSWORD", "TL_SERVER", "TL_ACCOUNT_ID"):
        monkeypatch.delenv(k, raising=False)
    d = srv.tradelocker_demo_snapshot()
    assert d["connected"] is False
    assert "no TL_EMAIL" in d["reason"]


def test_demo_gated_production_server(monkeypatch):
    monkeypatch.setenv("TL_EMAIL", "x@y.z")
    monkeypatch.setenv("TL_PASSWORD", "secret")
    monkeypatch.setenv("TL_SERVER", "CLRTYFX")
    d = srv.tradelocker_demo_snapshot()
    assert d["connected"] is False
    assert "PRODUCTION" in d["reason"] or "refusing" in d["reason"]


def test_demo_refuses_bare_clrtyfx(monkeypatch):
    monkeypatch.setenv("TL_EMAIL", "x@y.z")
    monkeypatch.setenv("TL_PASSWORD", "secret")
    monkeypatch.setenv("TL_SERVER", "CLRTYFX")
    d = srv.tradelocker_demo_snapshot()
    assert d["connected"] is False
    assert "not confirmed DEMO" in d["reason"]


def test_demo_readonly_happy_path(monkeypatch):
    """Verified DEMO id + mocked REST -> connected, read-only, no POST after auth."""
    monkeypatch.setenv("TL_EMAIL", "x@y.z")
    monkeypatch.setenv("TL_PASSWORD", "secret")
    monkeypatch.setenv("TL_SERVER", "Clarity FX")
    monkeypatch.setenv("TL_ACCOUNT_ID", "CLRTYFX#D#2329061")
    fake = _FakeRequests([
        ("/auth/jwt/token", _FakeResp(201, {"accessToken": "TOK", "refreshToken": "R"})),
        ("/auth/jwt/all-accounts", _FakeResp(200, {"accounts": [{"id": "2329061", "accNum": "1",
                                                                  "accountBalance": "9980.00", "name": "CLRTYFX#x#1#1"}]})),
        ("/positions", _FakeResp(200, {"positions": [
            {"symbol": "XAUUSD", "side": 1, "qty": 0.5},
            {"symbol": "BTCUSD", "side": 0, "qty": 0.01},
        ]})),
        ("/state", _FakeResp(200, {"equity": "10020.00"})),
    ])
    _install(fake)
    try:
        d = srv.tradelocker_demo_snapshot()
    finally:
        _install(None)
    assert d["connected"] is True
    assert d["host"] == "https://demo.tradelocker.com"
    assert d["read_only"] is True
    assert d["orders_placed"] == 0
    assert d["balance"] == "9980.00" and d["equity"] == "10020.00"
    assert {p["symbol"] for p in d["positions"]} == {"XAUUSD", "BTCUSD"}
    assert d["positions"][0]["side"] == "LONG" and d["positions"][1]["side"] == "SHORT"
    # after auth, connector must only GET (positions/state/accounts), never POST again
    posts = [c for c in fake.calls if c[0] == "POST"]
    gets = [c for c in fake.calls if c[0] == "GET"]
    assert len(posts) == 1 and "/auth/jwt/token" in posts[0][1]
    assert len(gets) >= 3  # all-accounts, positions, state
    assert all(u.startswith("https://demo.tradelocker.com/backend-api") for _, u in gets)


def test_demo_auth_failure(monkeypatch):
    monkeypatch.setenv("TL_EMAIL", "x@y.z")
    monkeypatch.setenv("TL_PASSWORD", "bad")
    monkeypatch.setenv("TL_SERVER", "Clarity FX")
    monkeypatch.setenv("TL_ACCOUNT_ID", "CLRTYFX#D#2329061")
    fake = _FakeRequests([("/auth/jwt/token", _FakeResp(401, {"error": "bad"}))])
    _install(fake)
    try:
        d = srv.tradelocker_demo_snapshot()
    finally:
        _install(None)
    assert d["connected"] is False
    assert "auth failed" in d["reason"]


def test_no_order_fields_in_response(monkeypatch):
    monkeypatch.setenv("TL_EMAIL", "x@y.z")
    monkeypatch.setenv("TL_PASSWORD", "secret")
    monkeypatch.setenv("TL_SERVER", "Clarity FX")
    monkeypatch.setenv("TL_ACCOUNT_ID", "CLRTYFX#D#2329061")
    fake = _FakeRequests([
        ("/auth/jwt/token", _FakeResp(200, {"accessToken": "T", "refreshToken": "R"})),
        ("/auth/jwt/all-accounts", _FakeResp(200, {"accounts": [{"id": "A1"}]})),
        ("/positions", _FakeResp(200, {"positions": []})),
        ("/state", _FakeResp(200, {"accountBalance": 1, "equity": 1})),
    ])
    _install(fake)
    try:
        d = srv.tradelocker_demo_snapshot()
    finally:
        _install(None)
    EXEC = {"order", "orders", "execute", "place", "trade", "submit", "fill"}
    assert not (EXEC & set(d.keys()))
    assert d.get("orders_placed") == 0


def test_place_demo_order_refuses_without_flag(monkeypatch):
    monkeypatch.setenv("TL_EMAIL", "x@y.z")
    monkeypatch.setenv("TL_PASSWORD", "secret")
    monkeypatch.setenv("TL_SERVER", "CLRTYFX")
    monkeypatch.setenv("TL_ACCOUNT_ID", "CLRTYFX#D#2329061")
    monkeypatch.delenv("EDGELAB_DEMO_FILL", raising=False)
    out = srv.place_demo_order("EURUSD", "BUY", 0.01)
    assert out["ok"] is False
    assert "EDGELAB_DEMO_FILL" in out["reason"]


def test_place_demo_order_refuses_live(monkeypatch):
    monkeypatch.setenv("TL_EMAIL", "x@y.z")
    monkeypatch.setenv("TL_PASSWORD", "secret")
    monkeypatch.setenv("TL_SERVER", "CLRTYFX")
    monkeypatch.setenv("TL_ACCOUNT_ID", "PRDTL#O#1785871804162702300")  # looks PROD
    monkeypatch.setenv("EDGELAB_DEMO_FILL", "1")
    out = srv.place_demo_order("EURUSD", "BUY", 0.01)
    assert out["ok"] is False
    assert "DEMO" in out["reason"] or "live" in out["reason"].lower()


def test_place_demo_order_happy_path(monkeypatch):
    monkeypatch.setenv("TL_EMAIL", "x@y.z")
    monkeypatch.setenv("TL_PASSWORD", "secret")
    monkeypatch.setenv("TL_SERVER", "CLRTYFX")
    monkeypatch.setenv("TL_ACCOUNT_ID", "CLRTYFX#D#2329061")
    monkeypatch.setenv("EDGELAB_DEMO_FILL", "1")
    fake = _FakeRequests([
        ("/auth/jwt/token", _FakeResp(201, {"accessToken": "T", "refreshToken": "R"})),
        ("/auth/jwt/all-accounts", _FakeResp(200, {"accounts": [{"id": "A1", "accNum": "1"}]})),
        ("/instruments", _FakeResp(200, {"d": {"instruments": [
            {"tradableInstrumentId": 14339, "id": 15364, "name": "EURUSD", "type": "FOREX",
             "routes": [{"id": 1168398, "type": "TRADE"}, {"id": 1168392, "type": "INFO"}]}]}})),
        ("/orders", _FakeResp(200, {"s": "ok", "d": {"orderId": "999"}})),
    ])
    _install(fake)
    try:
        out = srv.place_demo_order("EURUSD", "BUY", 0.01)
    finally:
        _install(None)
    assert out["ok"] is True
    assert out["demo"] is True
    assert out["symbol"] == "EURUSD" and out["side"] == "BUY"
    # the mock proves POST hit the orders endpoint after auth
    posts = [c for c in fake.calls if c[0] == "POST"]
    assert posts[-1][1].endswith("/orders")
