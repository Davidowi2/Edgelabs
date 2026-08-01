"""Account-level drawdown protection for EdgeLab (Phase 3, Module 2).

The 3-layer defense (caution / danger / kill) over daily and total drawdown.
Reads from AccountState, returns a (level, action, reason) recommendation. Every
check is logged; a KILL is logged at CRITICAL. Only the standard library.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, Tuple

from edgelab.risk.account_state import AccountState
from edgelab.risk.firm_presets import FIRM_PRESETS, get_firm_preset
from edgelab.monitoring.logger import TradingLogger


class ProtectionLevel(str, Enum):
    SAFE = "SAFE"
    CAUTION = "CAUTION"
    DANGER = "DANGER"
    KILL = "KILL"


class ProtectionAction(str, Enum):
    NONE = "NONE"
    REDUCE_SIZE = "REDUCE_SIZE"
    BLOCK_NEW_TRADES = "BLOCK_NEW_TRADES"
    CLOSE_ALL_POSITIONS = "CLOSE_ALL_POSITIONS"
    LOCK_ACCOUNT = "LOCK_ACCOUNT"


class DrawdownProtector:
    def __init__(self, config: dict, account_state: AccountState, logger: TradingLogger) -> None:
        self._state = account_state
        self._logger = logger

        # Start from preset if referenced, then apply flat overrides.
        cfg = dict(config or {})
        preset_name = cfg.get("firm_preset")
        merged = dict(get_firm_preset(preset_name)) if preset_name in FIRM_PRESETS else {}
        merged.update({k: v for k, v in cfg.items() if k not in ("firm_preset",)})

        self.daily_warn = float(merged.get("daily_dd_warn_pct", 0.014))
        self.daily_danger = float(merged.get("daily_dd_danger_pct", 0.017))
        self.daily_kill = float(merged.get("daily_dd_kill_pct", 0.02))
        self.total_warn = float(merged.get("total_dd_warn_pct", 0.023))
        self.total_danger = float(merged.get("total_dd_danger_pct", 0.028))
        self.total_kill = float(merged.get("total_dd_kill_pct", 0.03))

        buffer = float(merged.get("recovery_buffer_pct", 0.0))
        if buffer:
            self.daily_warn *= (1 - buffer)
            self.daily_danger *= (1 - buffer)
            self.daily_kill *= (1 - buffer)
            self.total_warn *= (1 - buffer)
            self.total_danger *= (1 - buffer)
            self.total_kill *= (1 - buffer)

    def check_protection(self) -> Tuple[ProtectionLevel, ProtectionAction, str]:
        daily = self._state.get_daily_drawdown_pct()
        total = self._state.get_total_drawdown_pct()
        _EPS = 1e-9  # guard against float noise (e.g. 0.02*0.9 vs 0.018)

        if daily >= self.daily_kill - _EPS or total >= self.total_kill - _EPS:
            level, action = ProtectionLevel.KILL, ProtectionAction.CLOSE_ALL_POSITIONS
            reason = f"kill switch triggered: daily={daily*100:.2f}%, total={total*100:.2f}%"
            self._logger.critical("risk protection KILL", daily_dd_pct=daily, total_dd_pct=total)
        elif daily >= self.daily_danger - _EPS or total >= self.total_danger - _EPS:
            level, action = ProtectionLevel.DANGER, ProtectionAction.BLOCK_NEW_TRADES
            reason = f"danger zone: daily={daily*100:.2f}%, total={total*100:.2f}%"
            self._logger.info("risk protection DANGER", daily_dd_pct=daily, total_dd_pct=total)
        elif daily >= self.daily_warn - _EPS or total >= self.total_warn - _EPS:
            level, action = ProtectionLevel.CAUTION, ProtectionAction.REDUCE_SIZE
            reason = f"caution zone: daily={daily*100:.2f}%, total={total*100:.2f}%"
            self._logger.info("risk protection CAUTION", daily_dd_pct=daily, total_dd_pct=total)
        else:
            level, action = ProtectionLevel.SAFE, ProtectionAction.NONE
            reason = "within limits"
            self._logger.info("risk protection SAFE", daily_dd_pct=daily, total_dd_pct=total)

        return level, action, reason

    def get_status(self) -> Dict:
        level, action, reason = self.check_protection()
        return {
            "level": level.value,
            "action": action.value,
            "reason": reason,
            "daily_dd_pct": self._state.get_daily_drawdown_pct(),
            "total_dd_pct": self._state.get_total_drawdown_pct(),
        }
