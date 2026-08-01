"""Tests for configuration loading from the constitution YAML."""

from __future__ import annotations

from edgelab.config import Config


class TestConfig:
    def test_loads_without_path(self):
        cfg = Config()
        assert isinstance(cfg._data, dict)

    def test_account_section_present(self):
        cfg = Config()
        assert "account" in cfg._data

    def test_internal_risk_exposes_risk_per_trade_pct(self):
        cfg = Config()
        assert cfg.internal_risk.get("risk_per_trade_pct") == 0.01

    def test_get_dotted_path(self):
        cfg = Config()
        assert cfg.get("internal_risk.daily_loss_lock_pct") == 0.02

    def test_get_missing_returns_default(self):
        cfg = Config()
        assert cfg.get("does.not.exist", "fallback") == "fallback"

    def test_session_filter_ny_present(self):
        cfg = Config()
        windows = cfg.internal_risk.get("session_filter_ny")
        assert windows == [[8, 0, 11, 0], [13, 30, 16, 0]]

    def test_correlation_groups_present(self):
        cfg = Config()
        groups = cfg.internal_risk.get("correlation_groups")
        assert "USD_EXPOSURE" in groups

    def test_max_open_positions_is_two(self):
        cfg = Config()
        assert cfg.internal_risk.get("max_open_positions") == 2

    def test_spread_pips_per_symbol_present(self):
        cfg = Config()
        spreads = cfg.internal_risk.get("spread_pips_per_symbol")
        assert spreads.get("EURUSD") == 0.8

    def test_validation_bar_present(self):
        cfg = Config()
        assert isinstance(cfg.validation_bar, dict)

    def test_strategy_and_environment_sections(self):
        cfg = Config()
        assert isinstance(cfg.strategy, dict)
        assert isinstance(cfg.environment, dict)
