# Document 1: Demo Account Setup Guide

## Before You Start
You need three things:

1. **A TradeLocker demo account** (opened through Clarity FX broker)
2. **A VPS or a clean local machine** to run the bot on
3. **The EdgeLab system files** (everything from `C:\Users\GTHub\Downloads\EDGELABS\edgelab`)

## Opening the TradeLocker Demo Account
1. Go to https://tradelocker.com or through your Clarity FX broker portal.
2. Sign up for a demo account (demo is free, no deposit required).
3. You will receive:
   - **Login number** (integer, like `12345678`)
   - **Password** (string, like `aBcD3fG7h`)
   - **Server name** (string, like `TradeLocker-Demo` or `ClarityFX-Demo`)
4. Save these three values. You will need them for the configuration file.

## Important Constraints
- **Demo accounts have 30-day expiration on some brokers.** You may need to renew.
- **Demo accounts have lower leverage than live** (usually 1:100 instead of 1:500).
- **Some symbols may not be available on demo.** Verify that XAUUSD (Gold vs US Dollar) is listed.
- **Demo accounts do not have real market liquidity.** Your orders may fill at worse prices than live. This is expected.
- **No real money is at risk.** All results are simulation.

## VPS vs Local Machine
You can run the bot on:

- **A VPS** (recommended for 24/5 operation) — any Linux VPS with 1+ GB RAM works. Cost: $5–20/month.
- **Your local machine** (simpler, but must stay awake during market hours) — fine for initial testing.

For Phase 10 forward testing, **a local machine is fine for the first 2–4 weeks** while you confirm everything works. Then **migrate to a VPS** for the full 4-month test.

## Where to put the files
The system lives at:

- **Windows:** `C:\Users\GTHub\Downloads\EDGELABS\edgelab`
- **Linux VPS:** `/home/youruser/EDGELABS/edgelab`

Keep this directory intact. Do not move individual files out of it.
