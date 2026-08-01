# Document 4: Post-Test Evaluation Framework

This is the formal review you do at 3 and 6 months. It is not emotional. It is not "I think it's working." It is a statistical analysis.

## Step 1: Statistical Analysis
Calculate these numbers from your trade log:

### Win Rate
```
Win Rate = (Number of Winning Trades / Total Number of Trades) * 100%
```

### Profit Factor
```
Profit Factor = (Sum of Gross Profits / Sum of Gross Losses)
```
- A profit factor > 1.5 is healthy
- A profit factor between 1.0 and 1.5 is marginal
- A profit factor < 1.0 means the system is losing money

### Expectancy (R-Multiple)
```
Expectancy = (Win Rate * Average Win) - (Loss Rate * Average Loss)
```
- Measured in R-multiples (a multiple of the risk taken per trade)
- Positive expectancy means the system makes money on average
- A value of 0.2R means the system makes 0.2x its risk per trade

### Sharpe Ratio
```
Sharpe Ratio = (Average R-Multiple - Risk-Free Rate) / StdDev of R-Multiples
```
- A Sharpe > 1.0 is good
- A Sharpe > 2.0 is excellent
- A Sharpe < 0 means the system is worse than holding cash

### Maximum Drawdown
```
Max DD = (Peak Equity - Lowest Subsequent Equity) / Peak Equity * 100%
```
- Track from the peak after each trade
- Blueberry 1-Step daily lock is 4%
- Blueberry 1-Step total lock is 6%
- If your drawdown exceeds these, the risk layer is not working

## Step 2: Regime Analysis
Group your trades by the regime at entry time:
- **Trending Up:** How many trades? Win rate? Average R?
- **Trending Down:** How many trades? Win rate? Average R?
- **Ranging:** How many trades? Win rate? Average R?
- **Volatile:** How many trades? Win rate? Average R?

**Question: Does the system perform better in some regimes than others?**
- **If yes:** the signal has regime sensitivity. A system that works in trends but not ranges (or vice versa) is still useful, but it means the regime filter is doing real work. Do NOT remove it.
- **If no:** the system works in all conditions. This is stronger evidence of an edge.

## Step 3: Cost Analysis
Calculate:
```
Gross Profit = Sum of all winning trade P&L
Gross Loss = Sum of all losing trade P&L (absolute value)
Net Profit = Gross Profit - Gross Loss
```
Then:
```
Total Costs = Net Profit - (Average Win * Number of Wins) + (Average Loss * Number of Losses)
```
Compare to backtest expectations. If the system is profitable net, check whether the costs are within the backtest's cost model. If the system is profitable in backtest but loses in forward test, the cost model is wrong (slippage or spread is worse in reality than the model assumed).

## Step 4: Failure Mode Analysis
Look at your 5 worst losses. For each one:
- What was the regime?
- What was the news context?
- Did the risk layer catch it?
- Did the trade management layer protect it?
- Was the signal itself wrong, or was the execution wrong?

**Categories:**
- **Signal failure:** The pattern didn't play out. The market went the wrong way.
- **Risk failure:** The position was too large. The risk layer should have reduced it.
- **Execution failure:** The spread was too wide or the fill was bad. The execution layer should have caught it.
- **News failure:** A high-impact event caused the loss. The news filter should have blocked the entry.

**Each category points to a different fix:**
- **Signal failure:** The strategy needs improvement (Phase 7+ refinement).
- **Risk failure:** The risk parameters need adjustment.
- **Execution failure:** The broker has worse conditions than expected (consider switching brokers).
- **News failure:** The news filter needs a longer blackout window.

## Step 5: Compare to Buy-and-Hold
This is the most important comparison. If your system traded XAUUSD for 6 months and made 3%, but buy-and-hold made 15% in the same period, your system underperformed.

```
System Return = (Final Account Balance / Initial Account Balance) - 1
Buy-and-Hold Return = (XAUUSD Close on Last Day / XAUUSD Close on First Day) - 1
```
- If buy-and-hold outperformed your system by a large margin, the system has a cost problem. Trading is inherently more expensive than holding. Your system needs to overcome that cost AND generate alpha. If it can't, the simpler approach (buy and hold) was better.
- If your system outperformed buy-and-hold, the system has real edge. This is the strongest result possible at the 6-month mark.
