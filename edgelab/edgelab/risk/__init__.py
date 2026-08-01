"""EdgeLab risk package (Phase 3, Module 4).

Single import point + factory + unified check. The rest of the system calls
``check_all_risk_limits()`` — never the individual modules. Fail-open: malformed
config returns ``{}`` and logs the error, never raising.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from edgelab.risk.account_state import AccountState
from edgelab.risk.drawdown_protector import (
    DrawdownProtector,
    ProtectionAction,
    ProtectionLevel,
)
from edgelab.risk.firm_presets import FIRM_PRESETS, get_firm_preset, list_firm_presets
from edgelab.risk.inactivity_tracker import InactivityTracker
from edgelab.monitoring.logger import TradingLogger
from edgelab.time.broker_time import BrokerTime

__all__ = [
    "AccountState",
    "DrawdownProtector",
    "InactivityTracker",
    "ProtectionLevel",
    "ProtectionAction",
    "create_risk_system",
    "check_all_risk_limits",
    "get_firm_preset",
    "list_firm_presets",
]


def create_risk_system(config: dict, logger: TradingLogger, broker_time: BrokerTime) -> dict:
    """Build the account-level risk system. Returns {} on any failure."""
    try:
        cfg = config or {}
        risk = cfg.get("risk")
        if not isinstance(risk, dict):
            logger.error("risk config missing or malformed; risk system disabled")
            return {}
        initial_balance = risk.get("initial_balance")
        if not isinstance(initial_balance, (int, float)) or initial_balance <= 0:
            logger.error("risk.initial_balance missing or invalid; risk system disabled")
            return {}
        preset_name = risk.get("firm_preset")
        if preset_name not in FIRM_PRESETS:
            logger.error(f"unknown firm_preset {preset_name!r}; risk system disabled",
                         available=list_firm_presets())
            return {}

        # merge preset + overrides (flat keys)
        merged = dict(get_firm_preset(preset_name))
        merged.update({k: v for k, v in risk.items() if k != "firm_preset"})

        account_state = AccountState(initial_balance=float(initial_balance),
                                     broker_time=broker_time, logger=logger)
        drawdown_protector = DrawdownProtector(merged, account_state, logger)
        inactivity_tracker = InactivityTracker(account_state, merged, logger, broker_time)

        logger.info("risk system initialized", initial_balance=initial_balance,
                    firm_preset=preset_name, daily_kill=merged.get("daily_dd_kill_pct"),
                    total_kill=merged.get("total_dd_kill_pct"))
        return {
            "account_state": account_state,
            "drawdown_protector": drawdown_protector,
            "inactivity_tracker": inactivity_tracker,
            "config": merged,
        }
    except Exception as exc:  # noqa: BLE001 - never crash startup
        logger.error("risk system construction failed", error=repr(exc))
        return {}


def check_all_risk_limits(risk_system: dict, current_equity: float, current_time: datetime) -> dict:
    """THE single entry point. Returns a complete status dict for this moment."""
    if not risk_system:
        return {
            "protection_level": "UNKNOWN",
            "action": "BLOCK_NEW_TRADES",
            "reason": "risk system not initialized",
            "daily_pnl": 0.0,
            "daily_dd_pct": 0.0,
            "total_dd_pct": 0.0,
            "inactivity_level": "critical",
            "days_until_kill": 0,
        }
    as_ = risk_system["account_state"]
    as_.update(current_equity, current_time)
    level, action, reason = risk_system["drawdown_protector"].check_protection()
    inact_level, days_until_kill, _ = risk_system["inactivity_tracker"].check_inactivity(current_time)
    return {
        "protection_level": level.value,
        "action": action.value,
        "reason": reason,
        "daily_pnl": as_.get_daily_pnl(),
        "daily_dd_pct": as_.get_daily_drawdown_pct(),
        "total_dd_pct": as_.get_total_drawdown_pct(),
        "inactivity_level": inact_level,
        "days_until_kill": days_until_kill,
    }
