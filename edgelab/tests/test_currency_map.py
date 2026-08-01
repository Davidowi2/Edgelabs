"""Tests for edgelab.news.currency_map (Phase 2, Module 2)."""

from __future__ import annotations

import pytest

from edgelab.news.currency_map import get_currencies_for_symbol


class TestMajors:
    def test_eurusd_returns_eur_usd(self):
        assert get_currencies_for_symbol("EURUSD") == ["EUR", "USD"]

    def test_gbpusd_returns_gbp_usd(self):
        assert get_currencies_for_symbol("GBPUSD") == ["GBP", "USD"]

    def test_usdjpy_returns_usd_jpy(self):
        assert get_currencies_for_symbol("USDJPY") == ["USD", "JPY"]

    def test_audusd_returns_aud_usd(self):
        assert get_currencies_for_symbol("AUDUSD") == ["AUD", "USD"]

    def test_usdcad_returns_usd_cad(self):
        assert get_currencies_for_symbol("USDCAD") == ["USD", "CAD"]

    def test_nzdusd_returns_nzd_usd(self):
        assert get_currencies_for_symbol("NZDUSD") == ["NZD", "USD"]

    def test_usdchf_returns_usd_chf(self):
        assert get_currencies_for_symbol("USDCHF") == ["USD", "CHF"]

    def test_xauusd_returns_usd_xau(self):
        assert get_currencies_for_symbol("XAUUSD") == ["USD", "XAU"]

    def test_xagusd_returns_usd_xag(self):
        assert get_currencies_for_symbol("XAGUSD") == ["USD", "XAG"]


class TestSuffixes:
    def test_symbol_with_broker_suffix_m(self):
        assert get_currencies_for_symbol("EURUSDm") == ["EUR", "USD"]

    def test_symbol_with_ecn_suffix(self):
        assert get_currencies_for_symbol("GBPUSD.ecn") == ["GBP", "USD"]

    def test_symbol_with_raw_suffix(self):
        assert get_currencies_for_symbol("USDJPY.raw") == ["USD", "JPY"]


class TestSpecial:
    def test_unknown_symbol_returns_empty_and_logs_warning(self, caplog):
        import logging
        with caplog.at_level(logging.WARNING):
            assert get_currencies_for_symbol("NOTAREALSYMBOL") == []
        assert any("warn" in r.message.lower() or "unknown" in r.message.lower() for r in caplog.records)

    def test_three_letter_symbol_handling(self):
        assert get_currencies_for_symbol("EUR") == ["EUR"]

    def test_btcusd_treated_as_usd(self):
        assert get_currencies_for_symbol("BTCUSD") == ["USD", "BTC"]

    def test_all_seven_majors_handled(self):
        for s in ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "NZDUSD", "USDCHF"]:
            out = get_currencies_for_symbol(s)
            assert len(out) == 2
            assert all(len(c) == 3 and c.isupper() for c in out)


class TestValidation:
    def test_output_always_validated(self):
        for s in ["EURUSD", "XAUUSD", "GBPUSDm", "USDJPY.raw", "AUDUSD"]:
            out = get_currencies_for_symbol(s)
            assert 1 <= len(out) <= 2
            assert all(len(c) == 3 and c.isupper() for c in out)
