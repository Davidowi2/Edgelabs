"""Deep trade analysis for Strategy 3 (Session) and Strategy 1 (Turtle).

Reads data/strategy3_trades.csv and data/strategy1_trades.csv (produced by
save_trade_logs.py). Pure analysis: no strategy/backtester/source is touched.

Reports (per strategy): session/day/volatility breakdowns, asymmetry, holding
time, pnl distribution, filtered equity curves, best-subset search, and
cross-strategy overlap.

Outputs both printed report and analysis/STRATEGY_ANALYSIS.md.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from edgelab.strategy.indicators import atr, in_window, ny_minutes  # noqa: E402

DATA = ROOT / "data"
OUT_MD = ROOT / "analysis" / "STRATEGY_ANALYSIS.md"


def pf_of(sub: pd.DataFrame) -> float:
    if len(sub) == 0:
        return float("nan")
    gross_win = sub.loc[sub.pnl_pips > 0, "pnl_pips"].sum()
    gross_loss = -sub.loc[sub.pnl_pips <= 0, "pnl_pips"].sum()
    if gross_loss <= 0:
        return float("inf") if gross_win > 0 else 0.0
    return gross_win / gross_loss


def wr_of(sub: pd.DataFrame) -> float:
    if len(sub) == 0:
        return float("nan")
    return (sub.pnl_pips > 0).mean() * 100


def summarize(sub: pd.DataFrame) -> dict:
    return {
        "n": len(sub),
        "win_pct": wr_of(sub),
        "pf": pf_of(sub),
        "avg_pips": sub.pnl_pips.mean() if len(sub) else float("nan"),
        "avg_win": sub.loc[sub.pnl_pips > 0, "pnl_pips"].mean() if (sub.pnl_pips > 0).any() else 0.0,
        "avg_loss": -sub.loc[sub.pnl_pips <= 0, "pnl_pips"].mean() if (sub.pnl_pips <= 0).any() else 0.0,
    }


def max_dd_pips(sub: pd.DataFrame) -> float:
    eq = sub.sort_values("entry_time").pnl_pips.cumsum().values
    if len(eq) == 0:
        return 0.0
    peak = np.maximum.accumulate(eq)
    dd = peak - eq
    return float(dd.max())


def best_subset(sub: pd.DataFrame, lines: list[str]):
    """Search single + two-way filters; report those with >=50 OOS trades."""
    candidates = []
    if "session" in sub.columns and sub.session.nunique() > 1:
        for s in sorted(sub.session.unique()):
            candidates.append((f"session={s}", sub.session == s))
    for p4 in sorted(sub.prior_4h_direction.unique()):
        candidates.append((f"prior4h={p4}", sub.prior_4h_direction == p4))
    if "atr_at_entry" in sub.columns and sub.atr_at_entry.notna().all():
        med = sub.atr_at_entry.median()
        candidates.append((f"atr>=median", sub.atr_at_entry >= med))
        candidates.append((f"atr<median", sub.atr_at_entry < med))
    for d in ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]:
        candidates.append((f"dow={d}", sub.day_of_week == d))

    results = []
    for desc, mask in candidates:
        oos = sub[mask & (sub["sample"] == "OOS")]
        if len(oos) >= 50:
            results.append((desc, len(oos), wr_of(oos), pf_of(oos), max_dd_pips(oos)))
    if "session" in sub.columns and sub.session.nunique() > 1:
        for s in sorted(sub.session.unique()):
            for p4 in sorted(sub.prior_4h_direction.unique()):
                m = (sub.session == s) & (sub.prior_4h_direction == p4)
                oos = sub[m & (sub["sample"] == "OOS")]
                if len(oos) >= 50:
                    results.append((f"session={s} & prior4h={p4}", len(oos), wr_of(oos), pf_of(oos), max_dd_pips(oos)))

    lines.append(f"\n  Subset search (OOS, min 50 trades): {len(results)} qualifying subsets")
    passed = [r for r in results if r[3] > 1.2]
    if passed:
        for desc, n, wr, pf, dd in sorted(passed, key=lambda x: -x[3]):
            lines.append(f"    PASS  {desc}: N={n} win={wr:.1f}% PF={pf:.2f} maxDD={dd:.1f}p")
    else:
        lines.append("    NONE passed PF>1.2 on 50+ OOS trades.")
        top = sorted(results, key=lambda x: -x[3])[:6]
        for desc, n, wr, pf, dd in top:
            lines.append(f"    best  {desc}: N={n} win={wr:.1f}% PF={pf:.2f} maxDD={dd:.1f}p")


def analyze_strategy(path: Path, name: str, lines: list[str], is_session: bool):
    df = pd.read_csv(path, parse_dates=["entry_time", "exit_time"])
    oos = df[df["sample"] == "OOS"]
    is_ = df[df["sample"] == "IS"]
    lines.append(f"\n=== {name} DEEP ANALYSIS ===")
    lines.append(f"Total trades: {len(df)} (IS={len(is_)}, OOS={len(oos)})")

    if is_session:
        lines.append("\nSession breakdown:")
        for s in ["LONDON", "NY", "OTHER"]:
            sub = df[df.session == s]
            if len(sub):
                m = summarize(sub)
                lines.append(f"  {s}: N={m['n']} PF={m['pf']:.2f} win={m['win_pct']:.1f}% avg_pips={m['avg_pips']:.2f}")
            else:
                lines.append(f"  {s}: N=0")
        lines.append("  OOS only:")
        for s in ["LONDON", "NY"]:
            sub = oos[oos.session == s]
            if len(sub):
                m = summarize(sub)
                lines.append(f"    {s}: N={m['n']} PF={m['pf']:.2f} win={m['win_pct']:.1f}%")

    if is_session:
        lines.append("\nTime-of-day (30-min buckets, NY time):")
        df["bucket"] = df.entry_time.map(lambda ts: _bucket(ts))
        for b in sorted(df.bucket.unique()):
            sub = df[df.bucket == b]
            if len(sub) >= 20:
                m = summarize(sub)
                lines.append(f"  {b}: N={m['n']} PF={m['pf']:.2f} win={m['win_pct']:.1f}%")

    lines.append("\nDay-of-week breakdown:")
    for d in ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]:
        sub = df[df.day_of_week == d]
        if len(sub) >= 20:
            m = summarize(sub)
            lines.append(f"  {d}: N={m['n']} PF={m['pf']:.2f} win={m['win_pct']:.1f}%")
        else:
            lines.append(f"  {d}: N={len(sub)} (<20)")

    lines.append("\nPrior-4h / trend filter:")
    for p4 in sorted(df.prior_4h_direction.unique()):
        sub = df[df.prior_4h_direction == p4]
        m = summarize(sub)
        lines.append(f"  {p4}: N={m['n']} PF={m['pf']:.2f} win={m['win_pct']:.1f}%")

    wins = df[df.pnl_pips > 0]
    losses = df[df.pnl_pips <= 0]
    aw = wins.pnl_pips.mean() if len(wins) else 0.0
    al = -losses.pnl_pips.mean() if len(losses) else 0.0
    ratio = aw / al if al > 0 else float("inf")
    lines.append(f"\nAsymmetry: Avg win={aw:.2f} pips Avg loss={al:.2f} pips Win/loss ratio={ratio:.2f}")
    aw_o = oos[oos.pnl_pips > 0].pnl_pips.mean() if (oos.pnl_pips > 0).any() else 0.0
    al_o = -oos[oos.pnl_pips <= 0].pnl_pips.mean() if (oos.pnl_pips <= 0).any() else 0.0
    lines.append(f"  OOS avg win={aw_o:.2f} avg loss={al_o:.2f}")

    wh = df[df.pnl_pips > 0].holding_bars.mean()
    lh = df[df.pnl_pips <= 0].holding_bars.mean()
    lines.append(f"\nHolding time: Avg winner={wh:.1f} bars Avg loser={lh:.1f} bars")

    lines.append("\nPnL distribution (pips):")
    lines.append(f"  min={df.pnl_pips.min():.1f} p25={df.pnl_pips.quantile(.25):.1f} "
                 f"median={df.pnl_pips.median():.1f} p75={df.pnl_pips.quantile(.75):.1f} "
                 f"max={df.pnl_pips.max():.1f} std={df.pnl_pips.std():.1f}")
    lines.append(f"  % winners={(df.pnl_pips>0).mean()*100:.1f}  biggest win={df.pnl_pips.max():.1f} "
                 f"biggest loss={df.pnl_pips.min():.1f}")

    lines.append("\nFiltered equity (OOS cumulative pips):")
    for desc, mask in [("London only", df.session == "LONDON"),
                       ("NY only", df.session == "NY"),
                       ("ATR>=median", df.atr_at_entry >= df.atr_at_entry.median()),
                       ("prior4h=BULL only", df.prior_4h_direction == "BULL")]:
        sub = oos[mask]
        lines.append(f"  {desc}: N={len(sub)} OOS net pips={sub.pnl_pips.sum():.1f} PF={pf_of(sub):.2f}")

    lines.append("\n--- BEST SUBSET SEARCH ---")
    best_subset(df, lines)
    return df


def _bucket(ts):
    m = ny_minutes(ts)
    if 180 <= m < 360:
        return f"L{(m-180)//30:02d}"
    if 480 <= m < 660:
        return f"N{(m-480)//30:02d}"
    return "X"


def cross_overlap(s1: pd.DataFrame, s3: pd.DataFrame, lines: list[str]):
    lines.append("\n=== CROSS-STRATEGY OVERLAP ===")
    a = set((t.round(freq="h"), d) for t, d in zip(s1.entry_time, s1.direction))
    b = set((t.round(freq="h"), d) for t, d in zip(s3.entry_time, s3.direction))
    common = a & b
    lines.append(f"Strategy1 trades: {len(a)}  Strategy3 trades: {len(b)}  Overlapping (bar+dir): {len(common)}")
    s3 = s3.copy()
    s3["overlap"] = [(t.round(freq="h"), d) in common for t, d in zip(s3.entry_time, s3.direction)]
    ov = s3[s3.overlap]
    nov = s3[~s3.overlap]
    lines.append(f"  S3 overlapping win%={wr_of(ov):.1f} (N={len(ov)})  non-overlap win%={wr_of(nov):.1f} (N={len(nov)})")
    lines.append(f"  Overlap PF={pf_of(ov):.2f}  non-overlap PF={pf_of(nov):.2f}")


def main():
    lines = []
    lines.append("# EdgeLab Strategy Deep-Dive Analysis (S1 Turtle + S3 Session)")
    lines.append("Data: EURUSD H1 5.4y. OOS = last 20%. PF = gross win pips / gross loss pips.")
    s3 = analyze_strategy(DATA / "strategy3_trades.csv", "Strategy 3 (Session Volatility Expansion)", lines, is_session=True)
    s1 = analyze_strategy(DATA / "strategy1_trades.csv", "Strategy 1 (Modernized Turtle)", lines, is_session=False)
    cross_overlap(s1, s3, lines)

    lines.append("\n=== RECOMMENDATION ===")
    lines.append("See narrative report in chat. Analysis-only; no source modified.")

    OUT_MD.parent.mkdir(exist_ok=True)
    OUT_MD.write_text("\n".join(lines))
    print("\n".join(lines))
    print(f"\n[written] {OUT_MD}")


if __name__ == "__main__":
    main()
