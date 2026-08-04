# Hypothesis H4: Crypto Trend (BTC/USDT, daily)

Status: NEW hypothesis — UNCORRELATED edge class vs the FX/gold trend family
we retired. Crypto is 24/7, different regime exposure, different liquidity.

## Edge type
Time-series TREND on a high-volatility 24/7 asset. Distinct from the (failed)
XAUUSD H4 pullback family in both market and mechanism.

## Rules (written before running)
1. Trend filter: close > EMA200 (daily) -> long only; (no shorts in v1; crypto
   bear markets are brutal and we have no short backtest history to trust).
2. Entry trigger: price makes a 20-day highest-close breakout (close = max close
   of last 20 bars), AND we are in an uptrend per (1).
3. Stop: 2 x ATR(20) below entry.
4. Position sizing: 1% risk (standard EdgeLab risk gate).
5. Exit: stop hit, OR close < EMA50 (trend invalidation), OR 30-bar time stop.
6. NO session filter (crypto is 24/7).
7. Slippage: 0.1% (Binance taker-ish, conservative for daily). No spread cost
   modeled separately (already in slippage).

## Prediction (stated before running)
Crypto trends are strong but whipsaw-prone. Expect PF 1.0-1.4, moderate trade
count (~15-40 over 3y on daily), high volatility. If PF<=1.2 OOS or MC fails,
H4 is RETIRED — not patched. Data length: ccxt caps ~1000 daily bars (~2.7y),
so 5y bar not met; reported honestly.
