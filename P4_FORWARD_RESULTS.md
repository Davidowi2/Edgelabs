# P4 Milestone — Demo Forward Test (No Live Capital)

_Date: 2026-08-04. All numbers from live runs this session._

## What was built
- `edgelab/forward/__init__.py` — broker-agnostic forward engine:
  - `current_h5_positions(prices)`: infers H5's live monthly basket from the
    latest 12-1 momentum ranking (replicates `run_h5`'s logic at the latest month).
  - `current_h6_position(btc4h)`: infers H6's live 4h position from
    `CryptoTrendStrategy.signal` on the last completed bar.
  - `build_forward_book(...)`: assembles the combined paper book using the P3
    vol-parity weights (H5 80.2% / H6 19.8%) and naive $10k unit sizing.
  - `JournalEntry` / `ForwardBook`: paper journal rows (status=PAPER, no fills).
- `scripts/run_forward.py` — generates today's paper book, prints it, and
  **appends** to `data/forward_journal.csv`. The TradeLocker executor is a STUB:
  it raises if `EDGELAB_LIVE_EXEC=1` is set, so it can NEVER place an order by
  accident. No keys are read; no network order API is called.
- `tests/test_forward.py` — 5 unit tests (weights/units, H5 ranking, H6 list
  shape, paper defaults, live-flag-off-by-default). All green.

## Live paper book generated (as_of 2026-08-04)
```
  H5_equity  XLE   LONG  signal@58.51   weight=0.802  units=137.08
  H5_equity  XLK   LONG  signal@186.26  weight=0.802  units=43.06
  H5_equity  XLV   LONG  signal@162.16  weight=0.802  units=49.46
  note: paper signals; no live capital deployed
  LIVE_EXEC=False -> paper only, no orders sent
```
H6 (BTC/USDT 4h) is currently FLAT — its EMA200/trend filter is not satisfied
at the latest bar, so no crypto signal is on. That is a legitimate "no trade"
state, not a bug. (The journal records whatever the combined book says each run;
running it monthly will accumulate the 3-month forward sample.)

## How the 3-month forward test works (per protocol)
1. Run `scripts/run_forward.py` monthly (or on each H5 rebalance + each H6 signal
   flip). It appends the paper book to `data/forward_journal.csv`.
2. After ~3 months, grade the forward sample against the backtest assumptions:
   - Did H5's monthly rotations hit the expected PF/win-rate envelope?
   - Did H6's breakout entries fill near signal_price (slippage check)?
   - Did the combined book stay within 4% DD in live paper?
3. Only if the forward sample is consistent with backtest do we consider the
   Blueberry 1-Step challenge — and even then, demo first.

## Safety
- No live capital. The executor stub refuses to run without an explicit
  `EDGELAB_LIVE_EXEC=1` env flag, and even then only raises (not places orders).
- No broker credentials are stored, read, or required for anything built here.

## Test status
Full suite: **681 passed** (+5 new forward tests, no regressions).

## Milestone status
P1 (data + WF) ✅  P2 (H5 pass / H6 risk-capped) ✅  P3 (portfolio layer, 4% DD cap) ✅
P4 (demo forward harness, no live capital) ✅ — harness built & verified; the
3-month live grading is an ongoing operational step, not a code task.

## What remains for YOU (not the agent)
- Supply TradeLocker demo API keys and wire the executor if you want automated
  paper fills (optional; manual journaling works without it).
- Run the harness monthly for 3 months, then review `data/forward_journal.csv`.
- Decide on the Blueberry 1-Step challenge only after the forward sample validates.
