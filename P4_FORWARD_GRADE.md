# P4 Close-Out — Forward Test Loop Operationalized

_Date: 2026-08-04. Numbers from live runs this session._

## What was added (completes the generate -> accumulate -> grade loop)
- `edgelab/forward/grade.py` — `grade_forward(rows, marks, ...)` reconstructs the
  paper-book equity from journal rows (additive model, matching the canonical
  backtester's `state.equity += pnl`) and grades it vs the backtest profile:
  - `BREACH` if forward maxDD > 4% (repo hard gate),
  - `REVIEW` if forward return sign opposes the backtest profile by >5%,
  - `CONSISTENT` otherwise.
- `scripts/grade_forward.py` — pulls live marks, parses the journal, prints a
  per-sleeve + combined verdict. No orders, no capital.
- `scripts/run_forward.py` — now de-dups same-day appends, so re-running the
  harness (e.g. per cron) does NOT inflate the forward sample with identical
  snapshots.

## Bug fixed getting here
The first grader used a **compounded** equity model (`eq *= weight*(1+pnl)`),
which made an 80%-weight +5% gain drop equity to 0.84 — nonsensical. Fixed to
**additive** (`eq += weight*pnl`), exactly how the canonical backtester books
P&L. Verified by `test_grade_consistent_*` / `test_grade_breach_*`.

## Current journal state (seeded 2026-08-04)
```
  H5_equity  XLE  LONG  signal@58.51  weight=0.802
  H5_equity  XLK  LONG  signal@186.26 weight=0.802
  H5_equity  XLV  LONG  signal@162.16 weight=0.802
  (H6 BTC/USDT 4h: FLAT — trend filter not satisfied)
```
Grader (day-0, no mark movement yet): CONSISTENT, return 0.00%, maxDD 0.00%.
This is expected on the seeding day; the grade becomes meaningful once the
journal accumulates monthly snapshots and live marks diverge from entries.

## How to run the 3-month forward test (operational, for David)
1. Schedule `scripts/run_forward.py` monthly (or on each H5 rebalance / H6 flip).
   It journals the paper book; same-day re-runs are de-duped.
2. Periodically run `scripts/grade_forward.py` to see the verdict.
3. After ~3 months / enough snapshots: if both sleeves grade CONSISTENT and the
   combined book stayed within 4% DD, the edge survived live paper — only then
   consider the Blueberry 1-Step challenge (demo first, then the $200 funded
   challenge). If BREACH/REVIEW, hold and investigate before any capital.

## Test status
Full suite: **686 passed** (+5 grader tests, +5 forward tests; no regressions).

## Roadmap status
P1 data+WF ✅  P2 H5 pass / H6 risk-capped ✅  P3 portfolio layer (4% DD cap) ✅
P4 forward harness + grader ✅ — fully operational; the 3-month live grading is
an ongoing operational step (no further code required from the agent).
