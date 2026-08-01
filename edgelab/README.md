# EdgeLab

Research-first trading foundation for the EdgeLab project. Phase 0 goal is *not* to build a live bot. It is to build and validate the hard risk governor, data pipeline, state bus, and backtester so a real edge can be tested later without rewriting core infrastructure.

## Status
- Phase 0 in progress
- Risk engine: planned
- Backtester: planned
- Data feed: planned

## Repo layout
- `edgelab/edgelab/config.py` loads constitution settings.
- `edgelab/edgelab/state/` holds the shared state bus and clock.
- `edgelab/edgelab/risk/` holds the governor, sizing, and circuit breakers.
- `edgelab/edgelab/backtest/` holds the bar-by-bar runner and metrics.
- `edgelab/edgelab/strategy/` holds strategy interfaces only.
- `scripts/` contains data download and validation utilities.
- `tests/` contains pytest coverage for core modules.
- `data/` is the offline OHLCV folder.

## Quick start
- Create a virtualenv.
- Install dependencies.
- Run tests.

## Notes
- No broker integration in Phase 0.
- No AI-assisted live decision making in the live system path.
