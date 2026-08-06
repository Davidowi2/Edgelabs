"""Narrative layer (Dashboard v2): turn bot state into plain-English meaning.

The bot was a black box of metrics. This module answers the questions a human
actually has:
  - What is the bot holding RIGHT NOW, and WHY?
  - What would make it change? (the signal rule)
  - When is the next time it would act? (monthly rebalance date)
  - How is each strategy doing against its honest test bar?

Pure functions; no I/O except reading the existing overwatch state file + alpaca
snapshot. Safe read-only.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[2]
STATE_FILE = ROOT / "logs" / "overwatch_state.json"


def _next_month_end() -> str:
    """Approximate next monthly rebalance date (last calendar day context)."""
    now = datetime.now(timezone.utc)
    if now.month == 12:
        y, m = now.year + 1, 1
    else:
        y, m = now.year, now.month + 1
    # last day of next month
    if m == 12:
        nxt = datetime(y + 1, 1, 1)
    else:
        nxt = datetime(y, m + 1, 1)
    last = nxt.replace(day=1) - __import__("datetime").timedelta(days=1)
    return last.strftime("%Y-%m-%d")


def h5_narrative(live: Optional[dict] = None) -> dict:
    """Plain-English story of the live H5 equity sleeve."""
    state = {}
    if STATE_FILE.exists():
        try:
            state = json.loads(STATE_FILE.read_text())
        except Exception:
            state = {}
    held = state.get("held") or []
    signal = state.get("signal") or []
    pv = state.get("portfolio_value") or (live or {}).get("portfolio_value")
    dd = state.get("dd_pct") or 0.0
    dd_cap = state.get("dd_cap") or 4.0
    status = state.get("status") or "idle"
    as_of = state.get("updated_at")

    if not held:
        story = ("H5 is not holding anything right now. The equity sleeve is flat — "
                 "either the bot hasn't started, the market is closed, or the signal "
                 "came back empty. Nothing to explain until it holds a basket.")
    else:
        # Why these names? H5 = top-3 of 12-1 momentum across 11 sector ETFs.
        story = (
            f"H5 is holding {len(held)} ETFs — {', '.join(held)}. "
            f"These are the 3 sector ETFs with the strongest 12-month momentum "
            f"(price trend over the past year). The bot buys them on a monthly "
            f"signal and sits. It will NOT trade again until the next monthly "
            f"rebalance — it only changes the basket when the momentum ranking "
            f"changes. So today it is 'set and forget' until {_next_month_end()}."
        )
    return {
        "strategy": "H5 — Equity Cross-Sectional Momentum",
        "holds": held,
        "signal": signal,
        "why": ("Top-3 of 12-1 momentum across 11 sector ETFs (SPY/QQQ + 9 sector "
                "ETFs). Monthly rebalance only."),
        "next_rebalance": _next_month_end(),
        "portfolio_value": pv,
        "dd_pct": dd,
        "dd_cap": dd_cap,
        "dd_headroom": round(dd_cap - abs(dd), 2),
        "status": status,
        "story": story,
        "as_of": as_of,
        "verdict": "PROVEN — passes the research bar (PF 1.39 OOS). Live on Alpaca paper.",
    }


def h8_narrative() -> dict:
    """Honest scoreboard for the H8 FX carry candidate (RETIRED, no capital)."""
    return {
        "strategy": "H8 — G10 FX Carry (real rate-differential)",
        "status": "RETIRED (failed the bar, no capital)",
        "verdict": ("Retired honestly per RESEARCH_PROTOCOL_v1. v0 was a marginal fail "
                    "(PF 1.11, MC 69.6%); v1 (time-varying rates + vol-scaled) was a "
                    "CLEAR fail and worse (PF 1.03, Sharpe 0.06, DD 5.08%, MC 54.2%). "
                    "No FX carry edge in the 2024-2026 rate-cutting regime. Only H5 "
                    "(equity momentum) remains proven."),
        "backtest": {"v0": {"trades": 138, "profit_factor": 1.11, "sharpe": 0.34,
                            "max_dd_pct": 2.91, "mc_profitable_pct": 69.6},
                     "v1": {"trades": 138, "profit_factor": 1.03, "sharpe": 0.06,
                            "max_dd_pct": 5.08, "mc_profitable_pct": 54.2}},
        "note": ("TradeLocker FX demo stays read-only — no passing FX hypothesis to "
                 "run on it. Retest only with new evidence / different rate regime."),
        "live": False,
    }


def roadmap_scoreboard() -> dict:
    """One-screen honest state of every strategy."""
    return {
        "H5_equity_momentum": "PROVEN · LIVE (Alpaca paper)",
        "H8_fx_carry": "RETIRED (failed bar v0+v1)",
        "H7_fx_carry_proxy": "RETIRED (failed bar)",
        "H4_H6_crypto": "FAILED bar (not promoted)",
        "H2_gold": "RETIRED (no edge)",
        "capital_deployed": "paper only · no live capital",
    }


def narrative_payload(live_alpaca: Optional[dict] = None) -> dict:
    return {
        "h5": h5_narrative(live_alpaca),
        "h8": h8_narrative(),
        "roadmap": roadmap_scoreboard(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
