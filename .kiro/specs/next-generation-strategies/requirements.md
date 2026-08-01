# Requirements Document: Next-Generation Strategy Development Framework

## Introduction

EdgeLab has completed its initial hypothesis testing phase with three strategies (Turtle, Session Expansion, Structure Pullback) that all failed to meet the validation bar (PF < 1.2, insufficient profitability, or inadequate trade count). The analysis revealed valuable insights: Wednesday outperforms other days, London/NY sessions matter, NY-session-only subset achieved PF=1.15, and prior 4H trend filters show potential.

This document specifies requirements for a framework that will systematically develop, test, and validate the next generation of trading strategies. The framework must learn from failures, enforce rigorous validation standards, and operate within the existing EdgeLab architecture.

## Glossary

- **Hypothesis**: A testable trading edge documented in YAML format following the research protocol
- **Validation_Bar**: The complete set of thresholds (200+ trades, 5+ years, PF > 1.2, <4% DD, 70%+ Monte Carlo) that every hypothesis must pass
- **Strategy_Runner**: The backtest execution engine that processes hypothesis tests through in-sample, out-of-sample, and walk-forward analysis
- **Research_Protocol**: The governance document (RESEARCH_PROTOCOL_v1.md) that defines hypothesis lifecycle, retirement rules, and evidence requirements
- **BaseStrategy**: The abstract interface that all strategy implementations must inherit from
- **StateBus**: The shared state management system for positions and account state
- **RiskEngine**: The component responsible for position sizing, spread costs, and risk approval
- **Subset_Analysis**: The process of filtering trade results by dimensions (session, day-of-week, trend direction) to discover conditional edges
- **Walk_Forward**: A validation technique that re-optimizes or revalidates parameters every 3 months on rolling windows
- **Monte_Carlo**: A robustness test that runs 1000 simulations with randomized trade sequences
- **In_Sample_Period**: The initial 80% of historical data used for hypothesis development and parameter tuning
- **Out_Of_Sample_Period**: The final 20% of historical data reserved for unbiased validation testing
- **Property_Based_Test**: A test that validates universal invariants across randomly generated inputs
- **Hypothesis_Generator**: The system component that produces new testable hypotheses from empirical observations

## Requirements

### Requirement 1: Data-Driven Hypothesis Generation

**User Story:** As a researcher, I want to generate new strategy hypotheses based on empirical observations from failed tests, so that new hypotheses have evidentiary grounding rather than being random guesses.

#### Acceptance Criteria

1. WHEN the system analyzes completed test results, THE Hypothesis_Generator SHALL extract statistically significant patterns from subset analysis
2. WHEN a pattern shows PF > 1.0 with N >= 50 trades in out-of-sample data, THE Hypothesis_Generator SHALL flag it as a candidate edge
3. WHEN creating a new hypothesis, THE Hypothesis_Generator SHALL reference the evidence source (test result artifact, subset filter applied, metric values observed)
4. THE Hypothesis_Generator SHALL validate that new hypotheses do not duplicate retired hypothesis claims
5. WHEN a hypothesis is generated, THE System SHALL create a YAML file conforming to the research protocol schema
6. THE System SHALL populate the hypothesis YAML with entry_rules, exit_rules, stop_rules, and rationale derived from the observed pattern
7. WHEN no patterns meet the candidate threshold, THE Hypothesis_Generator SHALL report no viable candidates rather than generating weak hypotheses

### Requirement 2: Hypothesis YAML Management

**User Story:** As a researcher, I want all hypotheses stored in a consistent YAML format, so that I can track hypothesis lifecycle, evidence, and retirement reasons systematically.

#### Acceptance Criteria

1. THE System SHALL store hypothesis YAML files in the directory edgelab/research/hypotheses/
2. WHEN a hypothesis is created, THE System SHALL assign a unique hypothesis_id in format HYP-NNN
3. THE System SHALL validate every hypothesis YAML against the research protocol schema before acceptance
4. WHEN a hypothesis YAML is missing required fields, THE System SHALL reject it with a descriptive error listing missing fields
5. THE System SHALL enforce that hypothesis_id values are unique across all YAML files
6. WHEN a hypothesis status changes, THE System SHALL update the YAML file status field to reflect the new state (not_started, testing, passed, failed, retired)
7. THE System SHALL preserve all hypothesis YAML files including retired hypotheses for historical record

### Requirement 3: Validation Pipeline Execution

**User Story:** As a researcher, I want to execute the complete validation pipeline (in-sample → out-of-sample → walk-forward → Monte Carlo) for each hypothesis, so that I can determine whether it meets the validation bar.

#### Acceptance Criteria

1. WHEN a hypothesis enters testing, THE Strategy_Runner SHALL execute in-sample backtest first using the initial 80% of data
2. WHEN in-sample testing completes, THE Strategy_Runner SHALL execute out-of-sample backtest using the final 20% of data that was never used during hypothesis development
3. WHEN out-of-sample testing completes, THE Strategy_Runner SHALL execute walk-forward analysis with 3-month rolling windows
4. WHEN walk-forward testing completes, THE Strategy_Runner SHALL execute 1000 Monte Carlo simulations randomizing trade sequence
5. THE Strategy_Runner SHALL apply realistic costs (spread, slippage, commission, swap) to every trade in every test phase
6. WHEN any test phase fails to meet validation bar thresholds, THE Strategy_Runner SHALL halt further testing and mark the hypothesis as failed
7. WHEN all test phases pass, THE Strategy_Runner SHALL mark the hypothesis as passed and eligible for forward testing

### Requirement 4: Validation Bar Enforcement

**User Story:** As a researcher, I want every hypothesis automatically checked against validation bar thresholds, so that only robust hypotheses proceed to forward testing.

#### Acceptance Criteria

1. THE System SHALL enforce minimum 200 trades across the complete backtest period
2. THE System SHALL enforce minimum 5 years of historical data coverage
3. THE System SHALL enforce that backtest data includes trending, ranging, and high-volatility market regimes
4. THE System SHALL enforce profit factor > 1.2 on out-of-sample data
5. THE System SHALL enforce maximum drawdown < 4% on backtest equity curve
6. THE System SHALL enforce that at least 70% of Monte Carlo simulations result in profitable outcomes
7. WHEN any threshold is violated, THE System SHALL document the specific failure reason in the test result artifact

### Requirement 5: Subset Analysis and Conditional Edge Discovery

**User Story:** As a researcher, I want to analyze trade results by session, day-of-week, trend direction, and volatility filters, so that I can discover conditional edges that may guide new hypotheses.

#### Acceptance Criteria

1. WHEN a backtest completes, THE System SHALL compute trade metrics grouped by session (LONDON, NY, OTHER)
2. WHEN a backtest completes, THE System SHALL compute trade metrics grouped by day-of-week (Monday through Friday)
3. WHEN a backtest completes, THE System SHALL compute trade metrics grouped by prior 4H trend direction (BULL, BEAR, NEUTRAL)
4. WHEN a backtest completes, THE System SHALL compute trade metrics grouped by ATR quartiles (low, medium, high volatility)
5. FOR ALL subset filters, THE System SHALL compute N trades, profit factor, win rate, and maximum drawdown
6. WHEN a subset has N >= 50 trades in out-of-sample data, THE System SHALL flag it for review if PF > 1.0
7. THE System SHALL output subset analysis results in a structured format (JSON or markdown table) attached to the test result artifact

### Requirement 6: Strategy Parameter Optimization Framework

**User Story:** As a researcher, I want to systematically test parameter variations during in-sample testing, so that I can identify robust parameter sets without overfitting.

#### Acceptance Criteria

1. WHEN a hypothesis defines parameter ranges, THE System SHALL generate a grid of parameter combinations for testing
2. THE System SHALL execute in-sample backtests for each parameter combination
3. WHEN in-sample testing completes, THE System SHALL rank parameter sets by profit factor and drawdown
4. THE System SHALL select the top-N parameter sets (N=3) for out-of-sample validation
5. WHEN out-of-sample testing shows performance degradation > 20% relative to in-sample, THE System SHALL flag the parameter set as overfit
6. THE System SHALL document all tested parameter combinations and their in-sample and out-of-sample metrics
7. WHEN no parameter set survives out-of-sample validation, THE System SHALL retire the hypothesis with reason "parameter_instability"

### Requirement 7: Walk-Forward Analysis Implementation

**User Story:** As a researcher, I want to validate strategy robustness using rolling 3-month windows, so that I can detect parameter drift and regime sensitivity.

#### Acceptance Criteria

1. WHEN walk-forward analysis begins, THE System SHALL divide the backtest period into consecutive 3-month windows
2. FOR ALL windows, THE System SHALL re-optimize or revalidate strategy parameters on that window
3. WHEN a window's out-of-sample profit factor falls below 1.0, THE System SHALL record that window as failed
4. THE System SHALL compute the percentage of windows that achieved PF > 1.0
5. THE System SHALL enforce that at least 70% of windows pass the PF > 1.0 threshold
6. WHEN walk-forward analysis fails the 70% threshold, THE System SHALL retire the hypothesis with reason "regime_instability"
7. THE System SHALL output walk-forward results as a time series showing per-window profit factor and drawdown

### Requirement 8: Monte Carlo Robustness Testing

**User Story:** As a researcher, I want to run 1000 Monte Carlo simulations randomizing trade sequence, so that I can measure whether profitability depends on trade order rather than edge.

#### Acceptance Criteria

1. WHEN Monte Carlo testing begins, THE System SHALL extract all trades from the backtest result
2. FOR ALL 1000 simulations, THE System SHALL randomly shuffle trade sequence and compute equity curve
3. FOR ALL simulations, THE System SHALL compute final equity, maximum drawdown, and profit factor
4. THE System SHALL compute the percentage of simulations that result in final equity > initial equity
5. THE System SHALL enforce that at least 70% of simulations are profitable
6. WHEN Monte Carlo testing fails the 70% threshold, THE System SHALL retire the hypothesis with reason "luck_dependent"
7. THE System SHALL output Monte Carlo results as a distribution of final equity values and a histogram of profit factors

### Requirement 9: Test Result Artifact Persistence

**User Story:** As a researcher, I want every test run to produce a timestamped JSON artifact, so that I can review historical tests and trace hypothesis evolution.

#### Acceptance Criteria

1. WHEN a test run completes, THE System SHALL create a JSON file in edgelab/research/results/
2. THE System SHALL name the artifact using format hypothesis_id_YYYY-MM-DD_HH-MM-SS.json
3. THE System SHALL include in the artifact: hypothesis_id, run_mode (in_sample, out_of_sample, walk_forward, monte_carlo), data_range, parameter_set, trades, equity_curve, metrics, costs assumptions
4. WHEN validation bar checks are performed, THE System SHALL include pass/fail status and failed check names in the artifact
5. THE System SHALL include Monte Carlo distribution statistics in the artifact when applicable
6. THE System SHALL include walk-forward per-window results in the artifact when applicable
7. THE System SHALL ensure artifacts are human-readable JSON with consistent schema

### Requirement 10: Hypothesis Retirement and Documentation

**User Story:** As a researcher, I want failed hypotheses automatically retired with documented failure reasons, so that I do not waste time retesting fundamentally flawed ideas.

#### Acceptance Criteria

1. WHEN a hypothesis fails any validation bar check, THE System SHALL update its YAML status field to "retired"
2. WHEN a hypothesis is retired, THE System SHALL append a summary to edgelab/research/failed_hypotheses.md
3. THE System SHALL include in the retirement summary: hypothesis_id, test_stage (in_sample, out_of_sample, walk_forward, monte_carlo), failure_reason, metric_values, lessons_learned
4. THE System SHALL mark retirement records with a timestamp
5. WHEN a hypothesis retirement reason is "insufficient_trades", THE System SHALL document the observed trade count
6. WHEN a hypothesis retirement reason is "low_profit_factor", THE System SHALL document the observed out-of-sample profit factor
7. THE System SHALL prevent re-testing of retired hypotheses unless explicitly flagged for retest with new evidence

### Requirement 11: Integration with BaseStrategy Interface

**User Story:** As a developer, I want all new strategy implementations to inherit from BaseStrategy, so that they integrate seamlessly with StateBus, RiskEngine, and Strategy_Runner.

#### Acceptance Criteria

1. THE System SHALL enforce that all strategy implementations inherit from BaseStrategy
2. WHEN a strategy is instantiated, THE System SHALL pass a StateBus instance and config dict to the constructor
3. THE System SHALL enforce that every strategy implements the evaluate(symbol, now) method returning Optional[dict]
4. WHEN a strategy generates a signal, THE returned dict SHALL include direction, entry_price, stop_loss, and optional take_profit
5. THE System SHALL enforce that strategies do not directly interact with broker APIs or manage risk calculations
6. THE System SHALL enforce that strategies do not persist state outside of StateBus
7. WHEN a strategy evaluation raises an exception, THE Strategy_Runner SHALL log the error and continue without halting the backtest

### Requirement 12: Strategy State Management Extensions

**User Story:** As a strategy developer, I want to track entry conditions, exit logic state, and position context, so that I can implement complex exit rules (trailing stops, time stops, breakout exits).

#### Acceptance Criteria

1. THE System SHALL extend BaseStrategy with methods: exit_signal(df, i) returning Optional[str] for exit reason
2. THE System SHALL extend BaseStrategy with methods: on_fill(direction, fill_price, bar_index, dataframe) for post-entry state updates
3. THE System SHALL extend BaseStrategy with methods: on_exit() for state cleanup after position close
4. WHEN a strategy exits a position, THE exit_signal method SHALL return a reason string (take_profit, stop_loss, trailing_stop, time_stop, signal_reversal)
5. THE System SHALL allow strategies to store internal state variables for tracking entry conditions and exit logic
6. THE System SHALL reset strategy internal state when on_exit() is called
7. WHEN Strategy_Runner evaluates exits, THE System SHALL call exit_signal on every bar while a position is open

### Requirement 13: Realistic Cost Modeling

**User Story:** As a researcher, I want all backtests to include spread, slippage, commission, and swap costs, so that profitability estimates reflect real trading conditions.

#### Acceptance Criteria

1. WHEN a trade entry is filled, THE System SHALL apply spread cost by adjusting entry price worse by the configured spread_pips
2. WHEN a trade entry is filled, THE System SHALL apply slippage cost by adjusting entry price worse by the configured slippage_pips
3. WHEN a trade exit is filled, THE System SHALL apply slippage cost by adjusting exit price worse by the configured slippage_pips
4. THE System SHALL retrieve spread_pips from the config file per-symbol spread_pips_per_symbol map
5. THE System SHALL default slippage_pips to 0.5 pips unless overridden in backtest configuration
6. WHEN commission is configured, THE System SHALL deduct commission from trade PnL
7. WHEN swap is configured, THE System SHALL deduct daily swap cost for positions held overnight

### Requirement 14: Research Workflow Tracking

**User Story:** As a researcher, I want to track the complete lifecycle of each hypothesis from generation through testing to retirement, so that I maintain an audit trail of research decisions.

#### Acceptance Criteria

1. WHEN a hypothesis is generated, THE System SHALL log the event with timestamp, hypothesis_id, and evidence source
2. WHEN a hypothesis enters testing, THE System SHALL log the event with timestamp, hypothesis_id, and test_stage
3. WHEN a test phase completes, THE System SHALL log the event with timestamp, hypothesis_id, test_stage, and pass/fail result
4. WHEN a hypothesis is retired, THE System SHALL log the event with timestamp, hypothesis_id, and retirement_reason
5. THE System SHALL store research workflow logs in edgelab/research/workflow.log
6. THE System SHALL format workflow logs as structured JSON lines for easy parsing
7. THE System SHALL include log entries for parameter optimization iterations and subset analysis findings

### Requirement 15: Hypothesis Comparison and Ranking

**User Story:** As a researcher, I want to compare multiple hypotheses side-by-side on key metrics, so that I can prioritize the most promising candidates for forward testing.

#### Acceptance Criteria

1. WHEN multiple hypotheses have completed testing, THE System SHALL generate a comparison report
2. THE comparison report SHALL include for each hypothesis: hypothesis_id, name, out-of-sample profit factor, out-of-sample win rate, maximum drawdown, total trades, Monte Carlo pass percentage
3. THE System SHALL rank hypotheses by a composite score combining profit factor, drawdown, and Monte Carlo robustness
4. THE System SHALL highlight hypotheses that meet all validation bar thresholds
5. THE System SHALL output the comparison report as a markdown table
6. WHEN no hypotheses meet the validation bar, THE System SHALL report that no viable candidates exist
7. THE System SHALL update the comparison report automatically when new test results are generated

### Requirement 16: Configuration Management for Hypothesis Testing

**User Story:** As a researcher, I want to specify test configurations (data range, symbol, initial equity, costs) in the hypothesis YAML, so that tests are reproducible and self-documenting.

#### Acceptance Criteria

1. THE System SHALL read data_start and data_end from the hypothesis YAML to determine backtest date range
2. THE System SHALL read instrument list from the hypothesis YAML to determine which symbols to test
3. THE System SHALL read timeframe from the hypothesis YAML to determine data granularity
4. THE System SHALL default initial_equity to 10000 unless overridden in the hypothesis YAML
5. THE System SHALL read cost parameters (spread_pips, slippage_pips, commission_per_lot) from the hypothesis YAML when present
6. WHEN cost parameters are missing from hypothesis YAML, THE System SHALL use default values from the base config
7. THE System SHALL validate that data_start and data_end span at least 5 years before executing tests

### Requirement 17: Error Handling and Test Recovery

**User Story:** As a researcher, I want the test pipeline to handle errors gracefully and continue testing other hypotheses, so that one bad hypothesis does not block the entire research queue.

#### Acceptance Criteria

1. WHEN a strategy implementation raises an exception during signal evaluation, THE Strategy_Runner SHALL log the error and skip that bar
2. WHEN a backtest fails due to data loading errors, THE System SHALL mark the hypothesis as "error" status and document the error message
3. WHEN a hypothesis YAML is malformed, THE System SHALL skip that hypothesis and continue processing other hypotheses
4. THE System SHALL retry transient failures (file I/O errors) up to 3 times before marking a test as failed
5. WHEN a test pipeline is interrupted, THE System SHALL preserve completed test results and allow resumption from the last completed stage
6. THE System SHALL log all errors to edgelab/research/errors.log with timestamp, hypothesis_id, and stack trace
7. WHEN a hypothesis accumulates more than 5 errors across test runs, THE System SHALL retire it with reason "implementation_unstable"

### Requirement 18: Visualization Support for Test Results

**User Story:** As a researcher, I want to generate equity curves, drawdown charts, and trade distribution plots, so that I can visually assess hypothesis performance.

#### Acceptance Criteria

1. WHEN a backtest completes, THE System SHALL generate an equity curve plot showing cumulative PnL over time
2. WHEN a backtest completes, THE System SHALL generate a drawdown chart showing percentage drawdown over time
3. WHEN a backtest completes, THE System SHALL generate a histogram of trade PnL distribution
4. THE System SHALL save visualization outputs as PNG files in edgelab/research/results/visualizations/
5. THE System SHALL name visualization files using format hypothesis_id_YYYY-MM-DD_chart-type.png
6. WHEN walk-forward analysis completes, THE System SHALL generate a per-window profit factor time series plot
7. WHEN Monte Carlo testing completes, THE System SHALL generate a histogram of final equity distribution across simulations

### Requirement 19: Baseline Strategy Benchmark

**User Story:** As a researcher, I want to compare new hypotheses against a simple baseline strategy (buy-and-hold or random entry), so that I can verify that observed edges are not due to market drift.

#### Acceptance Criteria

1. THE System SHALL implement a buy-and-hold baseline strategy that enters long at the start of the backtest period and exits at the end
2. THE System SHALL implement a random-entry baseline strategy that enters randomly with the same position sizing as the hypothesis under test
3. WHEN a hypothesis completes testing, THE System SHALL run the same tests on the baseline strategies using identical data and cost assumptions
4. THE System SHALL include baseline strategy metrics in the comparison report
5. WHEN a hypothesis profit factor is less than 1.1x the random-entry baseline profit factor, THE System SHALL flag the hypothesis as potentially spurious
6. THE System SHALL document baseline comparison results in the test result artifact
7. THE System SHALL enforce that hypotheses must outperform baselines to pass validation

### Requirement 20: Session and Time-Based Filtering

**User Story:** As a strategy developer, I want to specify session windows and time-based filters in the hypothesis, so that strategies only trade during high-probability time periods.

#### Acceptance Criteria

1. THE System SHALL parse session_filter_ny from the hypothesis YAML when present
2. WHEN session_filter_ny is specified, THE Strategy_Runner SHALL pass it to the RiskEngine to gate trade entries
3. THE RiskEngine SHALL reject trade entries that occur outside the specified session windows
4. THE System SHALL support multiple session windows per hypothesis (e.g., [[8,0,11,0], [13,30,16,0]])
5. WHEN no session_filter_ny is specified, THE System SHALL allow entries at any time
6. THE System SHALL convert UTC timestamps to NY time for session filtering using timezone-aware datetime objects
7. THE System SHALL log rejected entries with timestamp and rejection reason "outside_session_window"
