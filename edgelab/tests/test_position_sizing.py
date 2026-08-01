"""Tests for position sizing math."""

from __future__ import annotations

from decimal import Decimal

import pytest

from edgelab.risk.sizing import PositionSizing


class TestPositionSizing:
    def test_valid_inputs_produce_positive_lot(self, config):
        calc = PositionSizing(config)
        lot, risk, pips = calc.calculate(Decimal("10000"), Decimal("1.1000"), Decimal("1.0950"), "EURUSD")
        assert lot > 0
        assert risk == Decimal("100.00")
        assert pips > 0

    def test_zero_stop_distance_returns_zero(self, config):
        calc = PositionSizing(config)
        lot, risk, pips = calc.calculate(Decimal("10000"), Decimal("1.1000"), Decimal("1.1000"), "EURUSD")
        assert lot == 0

    def test_lot_scales_linearly_with_equity(self, config):
        calc = PositionSizing(config)
        small = calc.calculate(Decimal("10000"), Decimal("1.1"), Decimal("1.095"), "EURUSD")[0]
        big = calc.calculate(Decimal("20000"), Decimal("1.1"), Decimal("1.095"), "EURUSD")[0]
        assert abs(big - small * 2) < Decimal("0.0002")

    def test_lot_scales_inversely_with_stop_distance(self, config):
        calc = PositionSizing(config)
        tight = calc.calculate(Decimal("10000"), Decimal("1.1000"), Decimal("1.0990"), "EURUSD")[0]
        wide = calc.calculate(Decimal("10000"), Decimal("1.1000"), Decimal("1.0900"), "EURUSD")[0]
        assert tight > wide

    def test_negative_equity_returns_zero(self, config):
        calc = PositionSizing(config)
        lot, _, _ = calc.calculate(Decimal("0"), Decimal("1.1"), Decimal("1.095"), "EURUSD")
        assert lot == 0

    def test_spread_adds_to_stop_distance(self, config):
        calc = PositionSizing(config)
        no_spread = calc.calculate(Decimal("10000"), Decimal("1.1"), Decimal("1.095"), "EURUSD", spread_pips=None)
        with_spread = calc.calculate(Decimal("10000"), Decimal("1.1"), Decimal("1.095"), "EURUSD", spread_pips=Decimal("1.0"))
        assert with_spread[2] == no_spread[2] + 1.0
        assert with_spread[0] < no_spread[0]

    def test_pip_value_used_per_symbol(self, config):
        calc = PositionSizing(config)
        eurusd = calc.calculate(Decimal("10000"), Decimal("1.1"), Decimal("1.095"), "EURUSD")
        xauusd = calc.calculate(Decimal("10000"), Decimal("1.1"), Decimal("1.095"), "XAUUSD")
        # Same 0.005 price move: EURUSD is 50 pips (pip_size 0.0001) at value 10.0;
        # XAUUSD is 0.5 pips (pip_size 0.01) at value 1.0. Risk-per-lot is far smaller
        # for XAUUSD, so it needs a much larger lot to risk the same amount.
        assert xauusd[0] > eurusd[0]

    def test_quantized_to_four_decimals(self, config):
        calc = PositionSizing(config)
        lot, _, _ = calc.calculate(Decimal("12345"), Decimal("1.1234"), Decimal("1.1200"), "EURUSD")
        assert lot == lot.quantize(Decimal("0.0001"))

    def test_jpy_pip_size(self, config):
        calc = PositionSizing(config)
        lot, _, pips = calc.calculate(Decimal("10000"), Decimal("110.00"), Decimal("109.50"), "USDJPY")
        # 50 pip stop on JPY (pip size 0.01) -> 50 pips
        assert abs(pips - 50.0) < 1e-6
        assert lot > 0

    def test_very_tight_stop_returns_tiny_lot(self, config):
        calc = PositionSizing(config)
        lot, _, _ = calc.calculate(Decimal("10000"), Decimal("1.1000"), Decimal("1.0999"), "EURUSD")
        assert lot > 0
