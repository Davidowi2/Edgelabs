# EdgeLab — multi-component autonomous trading bot (DEMO-only)

A research-first trading system. It runs a **multi-component strategy** (vol-targeted
cross-sectional momentum on equities/bonds/gold + time-series-momentum trend on
multi-asset), sizes by risk parity, and is governed by a **4% daily-loss kill switch**
plus a circuit breaker.

> **DEMO / PAPER ONLY. No live capital, ever.** The broker connector refuses live
> accounts. All fills require an explicit user go-ahead flag (`EDGELAB_DEMO_AUTH=1`).

## What it does right now
- Connects to **MetaTrader 5 DEMO** (MetaQuotes-Demo) when `TL_*` creds are present
  in `launcher/.env`. Otherwise runs a simulated `MockBroker`.
- Computes a monthly TSMOM signal on the **tradeable symbols on your demo account**
  (on a generic MetaQuotes demo that is FX-only, it trades FX pairs).
- Places real **DEMO** orders when `EDGELAB_DEMO_AUTH=1`.
- Tracks **daily + realized P&L, win rate** from the live MT5 account into
  `logs/perf_state.json`.
- Serves a **desktop dashboard** on `http://127.0.0.1:8080` showing: what the bot
  holds, why, next rebalance, the 4% halt gauge, and the P&L panel.

## Honest strategy note
- The proven edge (Sharpe ~1.10, PF ~2.2 on a real backtest) used equities/bonds/gold
  CFDs. A generic **MetaQuotes-Demo only enables FX**, where TSMOM is historically a
  *weak/negative* edge (PF ~0.71). So on this demo the bot may lose money — that is
  **real, honest DEMO testing** with visible P&L, not a faked win rate.
- Failed hypotheses are retired, not tuned-to-pass (per research protocol).

## Safety gates (by design)
- `EDGELAB_DEMO_AUTH=1` — explicit user go-ahead to place DEMO orders. Default blank = signal-only.
- 4% daily loss lock — bot halts if equity drops >4% from the day's start.
- Circuit breaker — opens after 5 consecutive submission failures.
- No live-capital path exists anywhere in the connector.

## Repo layout
- `scripts/bot_runner.py` — persistent loop (schedule lib, not cron): monthly rebalance + 5-min P&L update.
- `scripts/run_dashboard.py` — desktop-first dashboard (port 8080), reads `bot_state.json` + `perf_state.json` + today's log.
- `edgelab/execution/tradelocker_broker.py` — MT5-backed broker (`TradeLockerBroker`), with `get_account_info()` / `get_deals_history()` for live P&L.
- `edgelab/execution/tradelocker_rest.py` — alternative REST client (gated, unused by default).
- `edgelab/execution/broker_factory.py` — selects REAL MT5 vs MockBroker.
- `edgelab/strategy/` — `tsmom.py`, `h5_voltarget.py`, `risk_parity.py`.
- `edgelab/monitoring/logger.py` — JSON-line logger.
- `launcher/` — `run.py` (robust entry point), `bot_launcher.bat`, `install_task.bat`, `.env` (gitignored), `.env.example`.

## Setup
1. `python -m venv` (or use the existing Hermes venv) and `pip install -r requirements.txt`
   (pandas, numpy, yfinance, requests, schedule, MetaTrader5).
2. Copy `launcher/.env.example` → `launcher/.env`; fill `TL_LOGIN/TL_PASSWORD/TL_SERVER`
   (MetaQuotes-Demo creds) and optionally `APCA_*` for Alpaca paper.
3. **Start MetaTrader 5 terminal** and log into your demo so the Python `MetaTrader5`
   package can reach the broker.
4. Set `EDGELAB_DEMO_AUTH=1` in `.env` only when you want it to actually trade DEMO.

## Run manually
- Double-click `launcher/bot_launcher.bat` (or `pythonw launcher/run.py`).
- Open `http://127.0.0.1:8080/`.

## Auto-start (Windows Task Scheduler — survives Hermes closing)
The bot must keep running even when Hermes is closed. `launcher/run.py` loads `.env`
in Python (handles special characters in passwords) and spawns the bot + dashboard as
**detached `pythonw` processes**.

1. Right-click `launcher/install_task.bat` → **Run as administrator** (elevation is
   required; without it Windows returns "Access is denied").
2. The task `EdgelabsBot` is registered `/sc onlogon /rl highest` — it auto-starts at
   every Windows logon.
3. Start immediately without logging off: `schtasks /run /tn "EdgelabsBot"`.

## Stop
- `schtasks /end /tn "EdgelabsBot"` then `schtasks /delete /tn "EdgelabsBot" /f`,
  or `taskkill /im pythonw.exe /f` (removes both bot + dashboard).

## Notes
- Credentials live ONLY in `launcher/.env` (gitignored) or session env. Never committed.
- `git check-ignore launcher/.env` confirms it is not tracked.
