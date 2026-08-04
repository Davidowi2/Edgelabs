"""Position sizing calculation."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from edgelab.config import Config


PIP_VALUES: dict[str, Decimal] = {
    "EURUSD": Decimal("10.0"),
    "GBPUSD": Decimal("10.0"),
    "AUDUSD": Decimal("10.0"),
    "NZDUSD": Decimal("10.0"),
    "USDCHF": Decimal("10.0"),
    "USDCAD": Decimal("10.0"),
    "USDJPY": Decimal("9.09"),  # approx / 0.01 = 100000 / rate, using 110 for simplified calc later if needed
    "EURJPY": Decimal("9.09"),
    "GBPJPY": Decimal("9.09"),
    "XAUUSD": Decimal("1.0"),
    "XAGUSD": Decimal("1.0"),
}


PIP_SIZE_MAP: dict[str, Decimal] = {
    "EURUSD": Decimal("0.0001"),
    "GBPUSD": Decimal("0.0001"),
    "AUDUSD": Decimal("0.0001"),
    "NZDUSD": Decimal("0.0001"),
    "USDCHF": Decimal("0.0001"),
    "USDCAD": Decimal("0.0001"),
    "USDJPY": Decimal("0.01"),
    "EURJPY": Decimal("0.01"),
    "GBPJPY": Decimal("0.01"),
    "XAUUSD": Decimal("0.01"),
    "XAGUSD": Decimal("0.01"),
}

# Asset-class resolution for non-FX instruments (crypto / equities).
# UNIT-class: 1 "lot" = 1 unit of the asset; risk is computed in price terms,
# so pip_size = 1.0 (one price unit) and pip_value_per_lot = entry price.
CRYPTO_SUFFIXES = ("/USDT", "/USD", "/USDC", "USDT", "USD")
EQUITY_LIKE = ("SPY", "QQQ", "XLF", "XLE", "XLK", "XLV", "XLI", "XLP", "XLY",
               "XLB", "XLU", "IWM", "DIA", "VTI", "ARKK")


def _asset_class(symbol: str) -> str:
    s = symbol.upper()
    if s in PIP_SIZE_MAP or s in PIP_VALUES:
        return "FX"
    if any(s.endswith(x) for x in CRYPTO_SUFFIXES) or s in ("BTC", "ETH", "SOL"):
        return "UNIT"
    if s in EQUITY_LIKE or (len(s) <= 5 and s.isalpha()):
        return "UNIT"
    return "UNIT"  # default: treat unknown as unit-priced asset


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


class PositionSizing:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.risk_per_trade_pct = Decimal(str(config.internal_risk.get("risk_per_trade_pct", 0.01)))

    def calculate(
        self,
        equity: Decimal,
        entry_price: Decimal,
        stop_loss: Decimal,
        symbol: str,
        spread_pips: Optional[Decimal] = None,
    ) -> tuple[Decimal, Decimal, float]:
        # Risk amount based on equity, never exceeding account equity
        risk_amount = (equity * self.risk_per_trade_pct).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if risk_amount <= 0:
            return Decimal("0"), Decimal("0"), 0.0

        # UNIT-class assets (crypto/equities): risk is in price terms.
        # pip_size = 1.0 (one price unit), so stop_distance is in price units,
        # and pip_value_per_lot = entry price (1 unit is worth its price).
        if _asset_class(symbol) == "UNIT":
            pip_size = Decimal("1.0")
            pip_value_per_lot = entry_price
        else:
            pip_size = PIP_SIZE_MAP.get(symbol.upper(), Decimal("0.0001"))
            pip_value_per_lot = PIP_VALUES.get(symbol.upper(), Decimal("10.0"))

        stop_distance_pips = float(abs(entry_price - stop_loss) / pip_size)
        if spread_pips is not None:
            stop_distance_pips += float(spread_pips)

        if stop_distance_pips <= 0:
            return Decimal("0"), Decimal("0"), 0.0

        risk_per_lot = pip_value_per_lot * Decimal(str(stop_distance_pips))
        if risk_per_lot <= 0:
            return Decimal("0"), Decimal("0"), 0.0

        lot_size = risk_amount / risk_per_lot
        # UNIT-class (crypto/equities) needs finer precision than FX lots:
        # a $100 risk on a $60k asset with a $5k stop is ~0.00002 units.
        if _asset_class(symbol) == "UNIT":
            lot_size = lot_size.quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)
        else:
            lot_size = _quantize(lot_size)
        if lot_size <= 0:
            return Decimal("0"), Decimal("0"), 0.0
        return lot_size, risk_amount, stop_distance_pips
