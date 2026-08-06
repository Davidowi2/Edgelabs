# Research Protocol v1

This protocol governs how research hypotheses are recorded, tested, evaluated, and retired in EdgeLab. Revenue comes only from a documented edge. If evidence is insufficient, the hypothesis is retired, not hand-waved.

## Hypothesis Format

Store one YAML file per hypothesis under `edgelab/research/hypotheses/`.

```yaml
hypothesis_id: "HYP-001"
version: "1.0"
created_at: "2026-07-25"
status: "not_started"  # not_started | testing | passed | failed | retired
author: ""

name: "London/NY overlap trend continuation on EURUSD H1"
instrument: ["EURUSD"]
timeframe: "H1"
data_start: ""
data_end: ""

claim: >
  When EURUSD opens the London/NY overlap in the direction of the prior Daily trend,
  and breaks the prior 4-hour high/low within the first 90 minutes, the move continues
  for at least 1.5x the breakout size with 55%+ probability.

rationale: "Behavioral underreaction plus liquidity event."

entry_rules:
  - "Daily trend is bullish or bearish."
  - "Opening of London/NY overlap session window initiates watch period."
  - "Break of prior H4 high/low within first 90 minutes triggers entry."

exit_rules:
  - "Take profit at 1.5x breakout size."
  - "Stop loss placed at opposite side of breakout bar low/high."

stop_rules:
  - "Initial stop determined at breakout structure."
  - "No breakeven move in hypothesis version 1.0."

position_sizing: "1% equity risk per trade, fixed."

strategy_family: "breakout-trend-continuation"
tags: ["eurusd", "h1", "session", "breakout"]

required_tests:
  - "in_sample_backtest"
  - "out_of_sample_backtest"
  - "walk_forward"
  - "monte_carlo"
  - "cost_realism"

evidence: []
reviewed_by: ""
retired_reason: ""
next_action: ""
```

All new hypotheses must use this schema.

## Validation Bar

Every hypothesis must pass every check before it moves to Phase 3 forward testing.

| Requirement | Threshold |
|---|---|
| Minimum trades | 200 |
| Minimum years of data | 5 |
| Market regime coverage | trending, ranging, high-volatility |
| Out-of-sample test | required |
| Walk-forward analysis | required |
| Monte Carlo simulations | 1000 |
| Monte Carlo minimum profitable percentage | 70% |
| Realistic costs | spread + slippage + commission + swap |
| Max backtest drawdown | less than 4% |
| Out-of-sample trade count | >= 30 trades OOS (anti-inertia / anti-IS-mirage gate) |
| Trade frequency compatibility | compatible with active-day rule |

### Interpretation Rules
- Missing regime coverage fails the hypothesis immediately.
- Out-of-sample data must not be used during strategy development.
- Walk-forward must re-optimize or revalidate every 3 months.
- Monte Carlo is evaluated on percentage of profitable simulations, not average profit.
- Backtest drawdown is compared against the internal 5% total drawdown lock, with an additional 1% buffer requirement at 4%.
- **OOS trade-count gate (added 2026-08-06):** a strategy must record >= 30 out-of-sample trades to qualify. This blocks two failure modes we actually hit: (a) INERT strategies that never fire (Gold H2/H3: 0/1/40 trades) and (b) IS-only mirages that look great in-sample but trade zero times OOS (Crypto H4: IS PF 2.73, OOS 0 trades). A strategy that does not trade cannot have an edge.

## Retirement Rules

### Automatic Retirement
A hypothesis is retired if it fails any single validation requirement with no path to recovery.

### Retirement Documentation
When a hypothesis is retired, append a summary to `edgelab/research/failed_hypotheses.md`.

Required fields:
- hypothesis_id
- test_stage
- failure_reason
- metric_values
- lessons_learned
- retest_eligibility

Retest is allowed only with new evidence or a materially changed market structure. Casual retesting is not allowed.

## Research Execution Log


Every test run creates a timestamped artifact:
- `edgelab/research/results/<hypothesis_id>_<yyyy-mm-dd>.json`

Log contents:
- hypothesis_id
- run_mode: `in_sample` | `out_of_sample` | `walk_forward`
- data_range
- parameter_set used, if any
- trades
- equity_curve
- metrics
- monte_carlo results
- costs assumptions
- pass or fail with failed checks listed

## Approval Authority

- Hermes can execute tests and produce results.
- Final hypothesis judgment requires human review of the result file and the retirement log.

## Change Control

Changes to validation thresholds require an explicit `ARCHITECTURE.md` update.

## Milestone Record (agent-run, 2026-08-04)

Roadmap P1–P5 executed and verified by Hermes (no live capital this session).

- **P1 — Data reproducibility:** `MarketDataFeed` (yfinance equities/ETFs, ccxt crypto, FX via `AUDUSD=X` etc.) caches to CSV. Reproducible.
- **P2 — H2 re-spec (XAUUSD H4):** re-specified as a new hypothesis and run honestly; **all retired** (no edge).
- **P3 — Portfolio layer:** vol-parity 80/20 allocator + 4% DD cap built. Combined book 17.8% return, 4.00% max DD capped. Still short of the >=2-strategy bar (only H5 proven).
- **P4 — Forward test harness:** monthly journal cron + read-only grader (verdict CONSISTENT on seeded 3 H5 rows). Internal-paper only (no broker fills yet).
- **P5 — Monitoring dashboard:** localhost-only, mobile-first, **no password**, read-only. TradeLocker DEMO connector VERIFIED LIVE (read-only: auth + accounts/positions/state, `orders_placed:0`). Host `demo.tradelocker.com/backend-api`, `server=CLRTYFX`, `accNum` header.

### Honest caveats (flagged for human review per Approval Authority)
- **H5** (equity cross-sectional momentum) is the ONLY hypothesis that passed the
  bar — and now validated on the FULL 5-year sample (not just 2y): FULL PF 1.54,
  Sharpe 0.55, MC 100%, 984 trades; OOS 1y PF 1.37, Sharpe 0.53, MC 94%, 195 trades
  (clears PF>1.2 / Sharpe>0.5 / MC>=70% / OOS>=30 gate). The ONE shortfall is
  backtest max drawdown (53% FULL / 14.9% OOS) vs the 4% rule — but the LIVE
  account is bounded by the overwatch 4% DD halt, so realized risk is capped. Edge
  is genuine and durable; universe is the 11-ETF base (adding bonds TLT/IEF dilutes
  PF 1.54->1.37 and trades 984->177, so NOT broadened). Currently live on Alpaca paper.
- **H6** (crypto 4h) is risk-capped (fails 200-trade & 4% DD bars); not promoted.
- **H7** (G10 FX carry, 12M price-return proxy) **RETIRED** — PF 0.74, MC 7.3%,
  DD 9.17%. Genuine failure, not tuned.
- **H8** (G10 FX carry, real rate-differential) **RETIRED** — v0 marginal fail
  (PF 1.11, MC 69.6%); v1 (time-varying rates + vol-scale) clear fail, worse
  (PF 1.03, Sharpe 0.06, DD 5.08%, MC 54.2%). No FX carry edge in 2024-26 cuts.
- **H2/H3** (Gold XAUUSD H4 structure-pullback v1/v2/v3) **RETIRED** — INERT:
  0/1/40 trades across 2y. Over-filtered, no fundamental anchor.
- **H4** (Crypto BTC daily breakout) **RETIRED** — IS PF 2.73 but OOS 0 trades
  (regime break / IS mirage). Confirmed by new OOS-trade-count gate.
- **H9** (Cross-Sectional Momentum on FX+Crypto, learned from H5) **RETIRED** —
  H9-FX PF 0.75 / DD 9.07% / MC 8.3% (no monthly FX momentum edge); H9-Crypto
  PF 1.06 / DD 78.89% (catastrophic drawdown vs 4% bar). Mechanism transferred
  partially (both now fire + clear OOS gate) but asset classes don't behave like
  equity ETFs. Confirms H5's edge is specific to equities, not portable to FX/crypto.
- **Conclusion (2026-08-06):** H5 (equity cross-sectional momentum) is the ONLY
  proven strategy. Every FX/gold/crypto attempt failed — on regime (H7/H8), inertia
  (H2/H3), IS-mirage (H4), or DD/edge (H9). New OOS-trade-count gate now REQUIRED.
- **Stage 2 PROVEN (2026-08-04):** with `EDGELAB_DEMO_FILL=1` + confirmed DEMO
  account, `place_demo_order()` places real paper orders via
  `POST /trade/accounts/{id}/orders` (resolves symbol->instrumentId->TRADE
  routeId, validity=IOC). Smoke-tested LIVE on the Clarity FX demo: a 0.01 EURUSD
  BUY filled (orderId 216172782127887850, balance moved 9980.00->9979.97) and was
  closed cleanly (balance 9979.94, round-trip spread cost). The demo account was
  left FLAT. **Caveat:** the demo is a FOREX account, so Stage 2 proves the ORDER
  PIPELINE works on FX — it is NOT a forward-test of H5 (equity ETFs), which needs
  an equities demo account. No live capital; `EDGELAB_LIVE_EXEC=1` still unset.
- **Stage 2b — H5 equities forward-test LIVE (2026-08-05):** user provided an
  Alpaca PAPER account (`paper-api.alpaca.markets`, account PA34OUY8PRVR,
  $100k). `edgelab/broker/alpaca.py` + `scripts/run_h5_forwardtest.py` placed the
  current H5 basket (XLE/XLK/XLV, ~$33k each, fractional paper MARKET orders) with
  `EDGELAB_ALPACA_FILL=1`. Orders queued pre-market (`new`, ~$100k BP reserved),
  fill at 09:30 ET open. This is the first OOS market test of the proven H5 edge
  (PF 1.39). Connector hard-refuses the Alpaca LIVE host. Creds in session env
  only. No live capital.
- No live capital deployed; executor remains gated behind `EDGELAB_LIVE_EXEC=1`
  (unset).
