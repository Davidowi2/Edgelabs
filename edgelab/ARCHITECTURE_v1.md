# EdgeLab Architecture v1

This document is the source of truth for project decisions. If any file in the repository contradicts this document, this document wins.

## Governance
- Reviewable only with a documented reason.
- Phase 0 rules hard-lock agent scope: no live broker integration, no strategy logic, no live trading.

## Constitution

```yaml
account:
  firm: "Blueberry Funded"
  challenge_type: "1-Step"
  profit_target_pct: 0.10
  daily_dd_pct: 0.04
  total_dd_pct: 0.06
  min_active_days: 3
  active_day_profit_threshold: 0.005
  news_blackout_minutes: 30
  daily_reset_time: "TBD-verify-with-Blueberry"
  max_trading_days: null
  bots_allowed: true
  consistency_rule: null

internal_risk:
  risk_per_trade_pct: 0.01
  daily_loss_lock_pct: 0.02
  total_dd_lock_pct: 0.05
  daily_lockout_hours: 24
  dd_lockout_hours: 72
  max_open_positions: 2
  correlation_groups:
    USD_EXPOSURE: ["EURUSD", "GBPUSD", "AUDUSD", "NZDUSD", "USDCHF", "USDCAD"]
    JPY_EXPOSURE: ["USDJPY", "EURJPY", "GBPJPY"]
    METALS: ["XAUUSD", "XAGUSD"]
  session_filter_ny:
    - [8, 0, 11, 0]
    - [13, 30, 16, 0]
  spread_pips_per_symbol:
    EURUSD: 0.8
    GBPUSD: 1.0
    XAUUSD: 2.5

strategy:
  family: "TBD-by-observation"
  initial_test_candidate: "trend-following-on-Daily-or-H4"
  ai_in_live_system: false
  ai_in_research: true

paths:
  phase_0_now: "Build + Validate Risk Engine + Download Data"
  phase_1_weeks_1_4: "Observe EURUSD, generate 2-3 hypotheses"
  phase_2_weeks_4_6: "Test hypotheses through backtester + validation bar"
  decision_point_week_6: "If no surviving hypothesis → kill project or restart"
  phase_3_months_2_4: "Forward test on TradeLocker demo (NOT Blueberry)"
  phase_4_months_5_plus: "Blueberry 1-Step challenge"

validation_bar:
  minimum_trades: 200
  minimum_years_data: 5
  must_include_regimes: ["trending", "ranging", "high-volatility"]
  out_of_sample_required: true
  walk_forward_required: true
  monte_carlo_simulations: 1000
  monte_carlo_min_profitable_pct: 70
  realistic_costs: true
  max_backtest_drawdown_pct: 0.04

environment:
  language: "Python 3.10+"
  coding_agent: "Hermes"
  data_source: "Dukascopy (free) for EURUSD H1/Daily, 5+ years"
  broker_for_demo: "Clarity FX on TradeLocker (later phase)"
  prop_firm_for_live: "Blueberry 1-Step (Phase 4 only)"
```

## Explanations

### Account Risks
- Firm limits are the hard boundary for later phases.
- Internal locks are set below firm limits to leave safety buffers.
- No live trading, so Phase 0 uses the internal limits directly as governor constraints.

### Internal Risk
- The governor enforces lockouts, max open positions, correlation buckets, and session filters.
- Risk per trade is based on current equity before the trade is approved.
- Spread cost is included in the pre-trade check used for lot sizing.

### Strategy
- Phase 0 does not encode a strategy.
- The architecture keeps strategy code isolated so future hypotheses can be tested without changing risk or state logic.

### Validation Bar
- Every testable hypothesis must clear this bar before any form of forward progression.
- Backtest drawdown is checked against the internal lock; firm limits are checked later when live challenge rules apply.

## Phase Access Rules
- Phase 0 modules must not import broker SDKs.
- State bus is the only allowed shared mechanism between modules.

## Milestone Record (agent-run, 2026-08-04)

P1–P5 executed (no live capital). See `RESEARCH_PROTOCOL_v1.md` Milestone Record
for detail + honest caveats. Summary of deviations from this document to review:

- **`broker_for_demo`** is now concrete: **Clarity FX on TradeLocker**, account
  `CLRTYFX#D#2329061` (DEMO, `#D#` marker). A read-only connector is verified
  live (`demo.tradelocker.com/backend-api`, `server=CLRTYFX`, `accNum` header).
  It places NO orders. Within the "no live trading / no live broker" lock.
- **Stage 2 (paper fills)** capability (`place_demo_order`) PROVEN live on the
  Clarity FX demo (2026-08-04): 0.01 EURUSD filled + closed, account left flat.
  Gated behind `EDGELAB_DEMO_FILL=1` + confirmed DEMO; never touches live. Auto-exec
  still disabled (no scheduled trading). H5 forward-test needs an equities demo.
- **Data source** expanded beyond Dukascopy: `MarketDataFeed` uses yfinance
  (equities/ETFs/FX) + ccxt (crypto), cached to CSV — reproducible.
- **H5** is the only proven edge; validated on ~2y daily (shorter than the 5y
  bar in `validation_bar`). Human review required before promotion.
- **H7** RETIRED (genuine failure); **H8** drafted (true rate carry, blocked on
  FRED package/key decision).
- No `EDGELAB_LIVE_EXEC=1`; no live capital; Phase 4 (Blueberry) not started.
