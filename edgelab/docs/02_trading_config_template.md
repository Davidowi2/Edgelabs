# Document 2: Trading Configuration Template

Save this as `config/trading.yaml` in your EdgeLab project directory.

```yaml
# Edgelab Trading Configuration
# Phase 10: Demo Forward Testing

broker:
  mode: tradelocker              # "tradelocker" or "mock"
  login: YOUR_DEMO_LOGIN         # Replace with your TradeLocker demo login number
  password: YOUR_DEMO_PASSWORD  # Replace with your demo password
  server: "TradeLocker-Demo"    # Replace with your broker's server name
  symbol_canonical: "XAUUSD"     # Gold vs US Dollar
  magic_number: 9001            # Unique EA identifier (don't change)
  timeout_ms: 5000              # MT5 connection timeout
  retry_on_error: true          # Auto-reconnect on transient failures

risk:
  firm_preset: blueberry_1step   # Hardcoded to current firm
  internal_risk:
    risk_per_trade_pct: 0.01     # 1% per trade
    daily_loss_lock_pct: 0.02    # 2% daily drawdown kill switch
    total_dd_lock_pct: 0.05      # 5% total drawdown kill switch
    recovery_buffer_pct: 0.10    # 10% safety margin
    inactivity_limit_days: 30    # 30-day max inactivity before close

analysis:
  enable_structure: true         # HH_HL pattern detection
  enable_anomaly: true          # Isolation Forest anomaly detection
  enable_memory: true           # Pattern memory (3-month rolling)
  pattern_detection: true       # H&S, double top/bottom, triangles
  news_calendar_path: "data/news_calendar_2026.json"
  max_confidence: 0.95          # Never exceed 95% confidence

execution:
  spread_max_points: 35.0       # Hard ceiling on spread (Gold typical: 20-50)
  spread_shock_multiplier: 2.0  # Block if current > 2x baseline median
  retry_max_attempts: 4         # Max order submission attempts
  retry_base_delay_ms: 200      # Base exponential backoff
  circuit_failure_threshold: 5  # Consecutive failures before circuit opens
  circuit_cooldown_ms: 30000    # 30-second cooldown when circuit opens

demo_mode:
  enabled: true                 # ALWAYS true for Phase 10
  initial_balance: 10000.00     # Starting demo balance for tracking
  log_file: "edgelab/logs/trading.log"
  decision_file: "edgelab/logs/decisions.log"
  metrics_file: "edgelab/logs/metrics.log"
```

## How To Customize

- **Broker credentials:** Replace `YOUR_DEMO_LOGIN` and `YOUR_DEMO_PASSWORD` with your actual values. Keep `mode: tradelocker` for real demo trading, or set to `mock` for offline testing.
- **Symbol:** The default is `XAUUSD` (Gold). If your broker uses a different symbol (like `GOLD` or `XAUUSD.r`), update `symbol_canonical`. The SymbolResolver handles broker suffix variations automatically.
- **Risk parameters:** Do NOT change `risk_per_trade_pct`, `daily_loss_lock_pct`, or `total_dd_lock_pct` for the first month. These are calibrated for survival. Change them only after the first month of data shows you understand the system.
- **Magic number:** The default `9001` identifies orders from this bot. Don't change it unless you run multiple bots on the same account.

## Where This File Lives
Save this as `config/trading.yaml` inside your EdgeLab project directory:

- **Windows:** `C:\Users\GTHub\Downloads\EDGELABS\config\trading.yaml`
- **Linux VPS:** `/home/youruser/EDGELABS/config/trading.yaml`

If the `config` directory doesn't exist, create it.
