"""Tests for edgelab.execution.symbol_resolver.SymbolResolver (Phase 9b, Module 1).

Resolves broker-specific symbol names (XAUUSD, XAUUSD.r, XAUUSDm, GOLDm, ...)
to the canonical logical symbol. Pure standard library only.
"""

import sys, os, tempfile
sys.path.insert(0, r"C:/Users/GTHub/Downloads/EDGELABS/edgelab")

import pytest

from edgelab.monitoring.logger import TradingLogger
from edgelab.execution.symbol_resolver import SymbolResolver, SymbolNotFoundError


@pytest.fixture
def logger():
    return TradingLogger(name="sym.test",
                         log_file=os.path.join(tempfile.gettempdir(), "sym_test.log"))


def _resolver(logger, **cfg):
    return SymbolResolver(cfg, logger)


class TestResolve:
    def test_resolve_canonical_returns_canonical(self, logger):
        r = _resolver(logger)
        assert r.resolve("XAUUSD") == "XAUUSD"

    def test_resolve_xauusd_r_returns_canonical(self, logger):
        r = _resolver(logger)
        assert r.resolve("XAUUSD.r") == "XAUUSD"

    def test_resolve_xauusd_m_returns_canonical(self, logger):
        r = _resolver(logger)
        assert r.resolve("XAUUSDm") == "XAUUSD"

    def test_resolve_goldm_returns_canonical(self, logger):
        r = _resolver(logger)
        assert r.resolve("GOLDm") == "XAUUSD"

    def test_resolve_gold_returns_canonical(self, logger):
        r = _resolver(logger)
        assert r.resolve("GOLD") == "XAUUSD"

    def test_resolve_xauusd_i_returns_canonical(self, logger):
        r = _resolver(logger)
        assert r.resolve("XAUUSD.i") == "XAUUSD"

    def test_resolve_unknown_raises(self, logger):
        r = _resolver(logger)
        with pytest.raises(SymbolNotFoundError):
            r.resolve("UNKNOWN")

    def test_resolve_case_insensitive(self, logger):
        r = _resolver(logger)
        assert r.resolve("xauusd.r") == "XAUUSD"

    def test_resolve_eurusd_default_aliases(self, logger):
        r = SymbolResolver({"canonical_name": "EURUSD"}, logger)
        assert r.resolve("EURUSD.r") == "EURUSD"

    def test_list_candidates_returns_all(self, logger):
        r = _resolver(logger)
        cands = r.list_candidates()
        assert len(cands) >= 6
        assert "XAUUSD" in cands
        assert "GOLDm" in cands

    def test_validate_broker_symbol_recognized(self, logger):
        r = _resolver(logger)
        assert r.validate_broker_symbol("XAUUSD.r") is True

    def test_validate_broker_symbol_unrecognized(self, logger):
        r = _resolver(logger)
        assert r.validate_broker_symbol("FOOBAR") is False

    def test_resolve_trims_trailing_dot(self, logger):
        r = _resolver(logger)
        assert r.resolve(".XAUUSD") == "XAUUSD"

    def test_custom_aliases_work(self, logger):
        r = SymbolResolver(
            {"canonical_name": "XAUUSD", "broker_aliases": ["MYGOLD", "MYGOLD.pro"]},
            logger)
        assert r.resolve("MYGOLD") == "XAUUSD"
        assert r.resolve("MYGOLD.pro") == "XAUUSD"
        # default aliases must NOT be recognized when custom config given
        assert r.validate_broker_symbol("XAUUSD.r") is False
