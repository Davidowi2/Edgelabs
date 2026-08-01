"""Broker factory for EdgeLab (Phase 9b, Module 3).

Selects the broker implementation from config and ALWAYS returns a working
BrokerInterface. If MetaTrader5 is unavailable or the real broker fails to
connect, it falls back to MockBroker. The factory never raises. Pure standard
library + optional MetaTrader5.
"""

from __future__ import annotations

from typing import Dict

from edgelab.monitoring.logger import TradingLogger
from edgelab.execution.gateway import BrokerInterface
from edgelab.execution.mock_broker import MockBroker
from edgelab.execution.tradelocker_broker import (
    TradeLockerBroker, MT5NotAvailableError, ConnectionError as BrokerConnectionError,
)


class BrokerFactory:
    @staticmethod
    def create_broker(config: Dict, logger: TradingLogger) -> BrokerInterface:
        cfg = (config or {}).get("broker", {}) or {}
        mode = str(cfg.get("mode", "mock")).lower()

        if mode == "tradelocker":
            try:
                broker = TradeLockerBroker(cfg, logger)
                # connect eagerly so a dead config fails loud here, not mid-trade
                broker.connect()
                logger.info(
                    f"broker selected: mode={mode} class={type(broker).__name__}",
                    server=cfg.get("server"))
                return broker
            except MT5NotAvailableError:
                logger.warning(
                    "broker selected: mode=tradelocker unavailable, falling back to MockBroker")
                return MockBroker(cfg)
            except BrokerConnectionError as exc:
                logger.error(
                    f"broker selected: mode=tradelocker connect failed, "
                    f"falling back to MockBroker (error={exc})")
                return MockBroker(cfg)
            except Exception as exc:  # noqa: BLE001 - safety net: never raise
                logger.error(
                    f"broker selected: mode=tradelocker error, "
                    f"falling back to MockBroker (error={exc})")
                return MockBroker(cfg)

        # default / explicit "mock"
        logger.info(f"broker selected: mode={mode} class={MockBroker.__name__}")
        return MockBroker(cfg)
