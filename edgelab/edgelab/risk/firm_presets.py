"""Firm risk presets for EdgeLab (Phase 3, Module 2b).

Each preset encodes the account-level drawdown limits we enforce INTERNALLY,
set to 50% of the prop-firm hard limits so our kill switch fires before the
firm terminates the account. Only the standard library is used.
"""

from __future__ import annotations

from typing import Dict, List

FIRM_PRESETS: Dict[str, Dict[str, float]] = {
    "blueberry_1step": {
        "daily_dd_warn_pct": 0.014,    # 1.4% (1.6% of 4% limit with 10% buffer)
        "daily_dd_danger_pct": 0.017,   # 1.7%
        "daily_dd_kill_pct": 0.02,      # 2.0% (half of 4% limit, hard stop)
        "total_dd_warn_pct": 0.023,     # 2.3% (2.7% of 6% with buffer)
        "total_dd_danger_pct": 0.028,   # 2.8%
        "total_dd_kill_pct": 0.03,      # 3.0% (half of 6% limit, hard stop)
        "daily_reset_hour_est": 17,     # 5 PM EST
        "inactivity_limit_days": 30,
    },
}


def get_firm_preset(name: str) -> Dict[str, float]:
    if name not in FIRM_PRESETS:
        raise ValueError(
            f"Unknown firm preset {name!r}. Available: {list_firm_presets()}"
        )
    return dict(FIRM_PRESETS[name])


def list_firm_presets() -> List[str]:
    return list(FIRM_PRESETS.keys())
