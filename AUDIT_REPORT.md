# EdgeLab Full Audit Report

Audit date: 2026-08-01. Scope: look-ahead / hidden bias / governance gaps / measurement honesty.
Method: read every core module (risk, signal, strategy x3, backtest x2, metrics, state, regime, sizing, indicators, runner script, docs). NO code modified.

## Severity legend
- [CRITICAL] invalidates current results / would mislead a go-live decision
- [HIGH] materially biases results, needs fix before trusting numbers
- [MED] correctness/consistency issue, fix soon
- [LOW] hygiene / clarity

---

## FINDINGS

### F-01 [CRITICAL] Two different backtest runners with two different PnL conventions — results not comparable
`backtest/runner.py` uses `StateBus._calculate_pnl` which multiplies (exit-entry)*lot with NO contract multiplier → PnL is 100,000× too small (correct for units but wrong for $ on a standard lot).
`backtest/strategy_runner.py` (the one `run_strategy_backtests.py` actually calls) applies `CONTRACT_MULTIPLIER = 100_000` as a *post-hoc* patch to equity and recorded PnL.
Problem: `runner.py` equity curves are nonsense in dollars; `strategy_runner.py` equity is "corrected" by mutating state after the fact (a hack). The two runners are not interchangeable and the patching makes the code fragile and easy to misuse. The repo's analysis CSVs (`strategy1_trades.csv` pnl_dollars) appear to come from a THIRD path. **Which runner produced STRATEGY_ANALYSIS.md is undocumented.**
→ Fix: one canonical backtester with correct PnL from the start; delete the other or clearly mark it dead.

### F-02 [CRITICAL] The "live candidate" (Strategy 2, XAUUSD H4) was NEVER backtested in this repo
- `SignalDetector`, `confluence`, `trading.yaml` all target **XAUUSD H4** as the forward-test instrument.
- `run_strategy_backtests.py` and `STRATEGY_ANALYSIS.md` test **EURUSD H1** (SYMBOL="EURUSD", DATA_CSV="EURUSD_H1_5y.csv").
- Strategy 2 `StructurePullbackStrategy` is coded for H1 (4-bar = H4 proxy) and is run on EURUSD H1 in the script. There is NO XAUUSD H4 backtest anywhere.
→ You would be forward-testing Gold on a system validated only on EURUSD. This is the single biggest gap between research and the live plan.

### F-03 [HIGH] Same-bar entry fill + optimistic SL/TP conflict
CORRECTION (post-read): `runner.py` (lines 70-71) is actually **stop-first** (`exit_price = stop_loss if stop_hit else tp`), so it is conservative on the SL/TP conflict. The TP-first optimism lives in `strategy_runner.py` (lines 152-159, checks `take_profit` BEFORE `stop_loss` → on a bar touching both, it returns "take_profit"). So: `runner.py` = stop-first (OK); `strategy_runner.py` = TP-first (optimistic). 
The real shared flaw in BOTH: **entries fill on the signal bar** (runners add the position within the same loop iteration; `strategy_runner` fills at signal-bar close ± spread/slip). Real fills cannot execute on the signal bar — you fill at the NEXT bar's open. This is mild optimism in both runners.
→ Fix (canonical runner): next-bar-open entry; on same-bar SL+TP touch, stop-first (already correct in runner.py; make strategy_runner consistent). Document the choice.

### F-04 [HIGH] Monte Carlo is REQUIRED by the protocol but is NOT implemented
`RESEARCH_PROTOCOL_v1.md` mandates: 1000 Monte Carlo sims, 70% profitable threshold. `ARCHITECTURE_v1` validation_bar lists `monte_carlo_simulations: 1000`.
Search of the codebase: **zero occurrences** of monte/walk_forward/bootstrap/simulation in any module. The runner script does a walk-forward (good) but NO Monte Carlo. So the validation bar cannot actually be passed as written — the 70%-profitable check is never computed.
→ Fix: implement bootstrap Monte Carlo on the trade PnL sequence → profitability distribution; gate on 70% profitable.

### F-05 [HIGH] Walk-forward in the script uses NO parameter re-optimization and tests on the WRONG split
`_walk_forward` (lines 108-139) takes the strategy as-is and tests each 3-month window with the *same fixed parameters* — that is an out-of-sample *stability* check, not true walk-forward (which re-optimizes on train, validates on test). Also it resamples to monthly start (`df.resample("MS")`) just to get month boundaries — fragile but works. Acceptable as a robustness check, but it should be labeled "rolling OOS stability," not "walk-forward," to avoid overclaiming.

### F-06 [MED] Session-window timezone handling is subtle and easy to get wrong
`strategy_runner.py` passes a tz-aware UTC timestamp so the naive Clock treats it as NY wall-clock. `runner.py`'s Clock converts naive→assumes UTC→NY. The two runners handle timezone differently. `structure_pullback` and `turtle` use `in_window` on naive timestamps (treated as NY). A single canonical time-handling path is needed; right now correctness depends on each caller doing it right by hand.

### F-07 [MED] Circuit-breaker locks are NEUTRALIZED in the strategy runner
`_neutral_config` (lines 70-87) sets `daily_loss_lock_pct=1.0`, `total_dd_lock_pct=1.0` (i.e. 100%) and `max_open_positions=1` so the measured DD is "the strategy's own edge." That's a legitimate research choice, BUT it means the runner's equity curve does NOT reflect the real governor. The live system uses the real 2%/5% locks. The demo/forward test will behave differently (get shut down sooner). Document this clearly so nobody conflates "strategy edge DD" with "account DD under the governor."

### F-08 [MED] Risk-engine `_in_session` depends on config windows; turtle disables it (None) — inconsistent
Turtle passes `session_windows=None` → Clock falls back to constitution windows (8-11 NY). The doc says turtle has NO session filter. So turtle IS session-gated by the fallback, contradicting the spec. The `strategy_runner` handles None by passing `[]` (no gate) — but the RiskEngine path (used by `runner.py`) uses the constitution fallback. Inconsistent gating between the two runners again (see F-01).

### F-09 [LOW] `SignalDetector` is long-only and XAUUSD-only, but `confluence` expects 3-way confluence for live
The detector only emits `EMA_PULLBACK_LONG`. The live system is long-only Gold. Fine as a design choice, but it means no short edge exists and the "regime TRENDING_DOWN" branch in confluence is dead for the live path. Acceptable, just note it limits the live system to long-only.

### F-10 [LOW] `summarize_trades` counts `p <= 0` as a loss; tiny-zero PnL trades (e.g. time-stop at flat) would be misclassified. Minor.

### F-11 [MED] No test data file present
`run_strategy_backtests.py` points at `data/EURUSD_H1_5y.csv` — not in the repo (only `strategy1_trades.csv`, `strategy3_trades.csv`, `news_calendar_2026.json` exist). So the backtests in STRATEGY_ANALYSIS.md cannot be reproduced from this checkout without the data file. Reproducibility gap → the "evidence" is not re-runnable as-is.

### F-12 [LOW] `docs` vs `ARCHITECTURE` drift on profit target
ARCHITECTURE says `profit_target_pct: 0.10` (10%), docs reference Blueberry 1-Step 10%. Consistent. But `daily_reset_time: "TBD-verify-with-Blueberry"` is still TBD — the daily loss lock's reset time is unverified, which matters for the 4% daily lock.

---

## SUMMARY
The repo is exceptionally well-governed on PAPER (validation bar, hypothesis retirement, honest post-mortem docs). The weakness is between the paper and the code:
1. Two backtest runners with conflicting PnL math (F-01) — measurement is not trustworthy yet.
2. The instrument actually slated for live (XAUUSD H4) has no backtest at all (F-02).
3. The validation bar's Monte Carlo requirement is unimplemented (F-04) — so no hypothesis can formally "pass."
4. Data file for reproduction is missing (F-11).

None of these are fatal. They are exactly the things Phase 0 should fix before any result is trusted. The risk engine, regime classifier, news filter, and governance docs are genuinely good.

## RECOMMENDED FIX ORDER (do not tune strategies until done)
1. F-01: collapse to ONE backtester, correct PnL, delete/quarantine the other.
2. F-03: next-bar-open entries + conservative same-bar SL/TP resolution.
3. F-04: implement Monte Carlo (required by your own bar).
4. F-02: acquire XAUUSD H4 5y data; backtest Strategy 2 on the REAL candidate.
5. F-11: commit the data file (or a fetcher + checksum) so results reproduce.
6. F-05/F-06/F-07/F-08: align session/time handling + label the WF correctly + document governor-neutering.

Audit complete. No source modified. Awaiting instruction before applying any fix.
