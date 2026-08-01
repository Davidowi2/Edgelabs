# Document 3: Forward Test Tracking Template

This is the weekly journal format. Every Sunday, spend 15 minutes filling it out. The discipline of recording is what makes this a real test, not a vibe.

## Weekly Journal Entry
**Week of:** YYYY-MM-DD (Monday date)

### Account State
- Starting balance: $_______
- Ending balance: $_______
- Net P&L this week: $_______
- Current equity high: $_______
- Current drawdown from high: _______%

### This Week's Trades
| Date | Time | Symbol | Direction | Entry | SL | TP | Exit | Exit Reason | P&L (pips) | R-Multiple | Pattern Match |
|------|------|--------|-----------|-------|------|------|------|------------|------------|-----------|--------------|
| | | | | | | | | | | | |
| | | | | | | | | | | | |
| | | | | | | | | | | | |

### System Behavior This Week
- Total signals generated: _______
- Signals filtered by news: _______
- Signals filtered by risk: _______
- Signals filtered by spread: _______
- Signals filtered by circuit: _______
- Signals actually executed: _______
- Execution rate: _______%

### Confidence Distribution This Week
- 0.0 – 0.3 (low confidence): _______ signals
- 0.3 – 0.5 (medium): _______ signals
- 0.5 – 0.7 (high): _______ signals
- 0.7 – 0.95 (very high): _______ signals

### Regime This Week
- Primary regime: [trending_up / trending_down / ranging / volatile]
- Confidence in regime: _______
- Regime changes during week: _______

### Observations
- Did the system behave as expected? _______
- Were there any unexpected events? _______
- Any errors in the logs? _______
- What did I learn this week? _______

### Emotional State
- Did I manually override the system? [yes/no] (if yes, document why)
- Did I check the dashboard more than 3 times per day? [yes/no]
- Am I tempted to change the configuration? [yes/no]
- How am I feeling about the system's performance? _______

## Monthly Roll-Up
At the end of each month, calculate:
- Total trades this month: _______
- Win rate: _______%
- Average R-multiple: _______
- Profit factor: _______
- Max drawdown: _______%
- Net P&L: $_______
- Best single trade: $_______
- Worst single trade: $_______
- Longest losing streak: _______ trades
- Longest winning streak: _______ trades

## Quarterly Decision Framework
After every 3 months, ask these questions:
- Is the win rate > 40%? If not, the system may not have an edge. Document and decide.
- Is the profit factor > 1.0? (Gross profit / Gross loss) If not, the system is losing money.
- Is the max drawdown < 6%? (Blueberry's daily lock threshold) If exceeded, the system is behaving outside its safety parameters.
- Is the system taking enough trades? If < 1 trade per week on average, the signal is too strict and the system may be over-filtered.
- Is the system taking too many trades? If > 5 per week with poor performance, the signal may be over-eager.

### Decision Rules At 3 Months
| Result | Decision |
|--------|----------|
| Win rate > 45% AND profit factor > 1.2 AND max DD < 5% | Continue to 6 months. System shows potential. |
| Win rate 35–45% AND profit factor 0.9–1.2 | Continue cautiously. Mixed signals. Look for regime bias. |
| Win rate < 35% OR profit factor < 0.9 | Stop and document. No edge detected. Write up what was learned. |
| Max drawdown > 8% | Risk layer is broken. Check risk configuration. Stop trading until fixed. |

### Decision Rules At 6 Months
| Result | Decision |
|--------|----------|
| Profitable for 2+ consecutive quarters | Consider micro-live ($500–1000). Start with minimum position size. |
| Mixed (some profitable, some not) | Continue on demo for 3 more months. If still mixed, document and move on. |
| Losing money consistently | Stop. The system does not have an edge. Move on. |
