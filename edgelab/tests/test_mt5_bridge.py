"""Tests for edgelab.news.mt5_bridge (Phase 2, Module 4 - stub)."""

from __future__ import annotations

import inspect

import pytest

from edgelab.news import mt5_bridge


class TestStandalone:
    def test_fetch_events_from_mt5_returns_empty_in_standalone_mode(self):
        assert mt5_bridge.fetch_events_from_mt5(["USD"]) == []

    def test_is_mt5_environment_returns_false_when_package_missing(self):
        assert mt5_bridge.is_mt5_environment() is False

    def test_is_mt5_environment_does_not_raise_on_import_error(self):
        # Should return False, never raise.
        assert mt5_bridge.is_mt5_environment() in (True, False)

    def test_mt5_bridge_module_documents_integration_path(self):
        doc = mt5_bridge.__doc__ or ""
        assert "MQL5" in doc or "MT5" in doc
        # The fetch function docstring should also explain integration.
        assert "MQL5" in (mt5_bridge.fetch_events_from_mt5.__doc__ or "")
