"""Multi-market data feed (Phase: market expansion).

NOTE: the repo already owns `edgelab/data/feed.py` (bar streaming: Bar/iter_bars/
stream). This module is a SEPARATE, additive fetcher for external market data
(yfinance equities/ETFs, ccxt crypto) and does not touch that file.

Normalizes both sources to the canonical EdgeLab OHLCV schema (columns:
timestamp, open, high, low, close, volume; index = tz-aware UTC
DatetimeIndex). Results are cached to data/ as CSV so backtests stay
reproducible (same F-11 discipline as the EURUSD pipeline).

Sources:
  - yfinance : equities / ETFs (e.g. SPY, QQQ, sector ETFs). Daily bars.
  - ccxt     : crypto spot OHLCV from a public exchange (Binance default),
               no API key required for historical OHLCV.

Usage:
    feed = MarketDataFeed()
    df = feed.get("SPY", source="yfinance", interval="1d", years=5)
    df = feed.get("BTC/USDT", source="ccxt", interval="1d", years=5)
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]  # edgelab/ -> repo root
DATA_DIR = ROOT / "data"


class MarketDataFeed:
    def __init__(self, cache_dir: Optional[Path] = None) -> None:
        self.cache_dir = Path(cache_dir) if cache_dir else DATA_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    # ---- public API ----
    def get(self, symbol: str, source: str = "yfinance", interval: str = "1d",
            years: int = 5, use_cache: bool = True, force: bool = False) -> pd.DataFrame:
        cache = self._cache_path(symbol, source, interval)
        if use_cache and not force and cache.exists():
            return self._read_cache(cache)
        df = self._fetch(symbol, source, interval, years)
        df = self._normalize(df)
        self._write_cache(cache, df)
        return df

    # ---- source-specific fetch ----
    def _fetch(self, symbol, source, interval, years):
        if source == "yfinance":
            return self._fetch_yfinance(symbol, interval, years)
        if source == "ccxt":
            return self._fetch_ccxt(symbol, interval, years)
        raise ValueError(f"Unknown source: {source}")

    @staticmethod
    def _fetch_yfinance(symbol, interval, years):
        import yfinance as yf
        # yfinance period tokens: 1y..10y, or "max". Map years>10 to "max".
        if years >= 10:
            period = "max"
        else:
            period = f"{years}y"
        df = yf.Ticker(symbol).history(interval=interval, period=period,
                                       auto_adjust=False)
        if df is None or df.empty:
            raise RuntimeError(f"yfinance returned no data for {symbol}")
        out = df[["Open", "High", "Low", "Close", "Volume"]].copy()
        out.columns = ["open", "high", "low", "close", "volume"]
        out.index.name = "timestamp"
        return out

    @staticmethod
    def _fetch_ccxt(symbol, interval, years):
        import ccxt
        ex = ccxt.binance()
        # Pagination: ccxt caps a single fetch_ohlcv call at ~1000 bars. Walk
        # `since` backward in chunks to assemble years of history.
        # One bar's duration in ms, derived from the timeframe token.
        tf_digits = "".join(c for c in interval if c.isdigit()) or "1"
        tf_unit = interval[-1]
        unit_ms = {"m": 60_000, "h": 3_600_000, "d": 86_400_000}[tf_unit]
        bar_ms = int(tf_digits) * unit_ms
        bars_per_year = int(365.25 * 86_400_000 / bar_ms)
        total_needed = int(bars_per_year * years)
        chunk = 1000  # max per call
        step_ms = chunk * bar_ms
        end = ex.milliseconds()
        collected = []
        max_loops = max(20, (total_needed // chunk) + 5)
        for _ in range(max_loops):
            ohlcv = ex.fetch_ohlcv(symbol, timeframe=interval, since=end - step_ms, limit=chunk)
            if not ohlcv:
                break
            collected = ohlcv + collected
            end = ohlcv[0][0]
            if len(collected) >= total_needed:
                break
        if not collected:
            raise RuntimeError(f"ccxt returned no data for {symbol}")
        df = pd.DataFrame(collected, columns=["ts", "open", "high", "low", "close", "volume"])
        df = df.drop_duplicates(subset=["ts"]).sort_values("ts")
        df["timestamp"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
        return df.set_index("timestamp")[["open", "high", "low", "close", "volume"]]

    # ---- normalization ----
    @staticmethod
    def _normalize(df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()[["open", "high", "low", "close", "volume"]]
        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC")
        else:
            df.index = df.index.tz_convert("UTC")
        df = df.sort_index()
        df["volume"] = df["volume"].fillna(0.0).astype(float)
        df = df.dropna(subset=["open", "high", "low", "close"])
        return df

    # ---- cache IO (reproducibility) ----
    def _cache_path(self, symbol, source, interval):
        safe = symbol.replace("/", "_").replace("=", "_")
        return self.cache_dir / f"{safe}_{source}_{interval}.csv"

    @staticmethod
    def _read_cache(path: Path) -> pd.DataFrame:
        df = pd.read_csv(path)
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        return df.set_index("timestamp").sort_index()

    @staticmethod
    def _write_cache(path: Path, df: pd.DataFrame) -> None:
        out = df.reset_index()
        out["timestamp"] = out["timestamp"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        out.to_csv(path, index=False)
