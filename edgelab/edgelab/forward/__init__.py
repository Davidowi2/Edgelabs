"""Forward-test engine: produce the live signals the combined H5+H6 book
would hold today, for a no-capital demo journal.

This module is broker-agnostic. It emits a JournalEntry list (what we WOULD
hold + at what price) given the latest data. A separate executor (stubbed)
would place the orders on TradeLocker demo; here we only journal.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import pandas as pd


@dataclass
class JournalEntry:
    """One forward-test journal row. 'live' fields are filled by the executor;
    if live fields are None the entry is an unexecuted paper signal."""
    as_of: datetime
    sleeve: str            # 'H5_equity' | 'H6_crypto'
    symbol: str
    direction: str         # LONG | SHORT | FLAT
    signal_price: float
    weight: float
    units: float
    live_fill_price: Optional[float] = None
    live_fill_time: Optional[datetime] = None
    status: str = "PAPER"  # PAPER | FILLED | REJECTED


@dataclass
class ForwardBook:
    as_of: datetime
    entries: list = field(default_factory=list)
    note: str = ""


def build_forward_book(as_of: datetime, h5_positions: list, h6_positions: list,
                       weights: dict, prices: dict) -> ForwardBook:
    """Assemble today's paper book from each sleeve's current positions.

    h5_positions / h6_positions: list of dicts {symbol, direction, price}
    weights: vol-parity sleeve weights {H5_equity, H6_crypto}
    prices: {symbol: last_price} for unit sizing (naive: equity_weight / price)
    """
    entries = []
    for sleeve, poslist, wkey in (("H5_equity", h5_positions, "H5_equity"),
                                  ("H6_crypto", h6_positions, "H6_crypto")):
        w = float(weights.get(wkey, 0.0))
        for p in poslist:
            sym = p["symbol"]; px = float(p["price"])
            last = float(prices.get(sym, px))
            units = (w * 10000.0) / last if last > 0 else 0.0  # $ weight of 10k book / price
            entries.append(JournalEntry(
                as_of=as_of, sleeve=sleeve, symbol=sym,
                direction=str(p["direction"]).upper(), signal_price=px,
                weight=w, units=round(units, 6),
            ))
    return ForwardBook(as_of=as_of, entries=entries,
                       note="paper signals; no live capital deployed")


def current_h5_positions(prices, top_n: int = 3) -> list:
    """Infer H5's current monthly book from the latest 12-1 momentum ranking.

    H5 holds the top-N cross-sectional momentum ETFs for the month. We replicate
    run_h5's ranking at the latest available month so the forward journal
    reflects what H5 would be holding now. Returns [{symbol, direction, price}].
    """
    close_m = pd.DataFrame({s: df["close"].astype(float).resample("ME").last()
                            for s, df in prices.items()}).dropna(how="any")
    if len(close_m) < 14:
        return []
    t = len(close_m) - 1
    if t >= 13:
        mom = (close_m.iloc[t - 1] - close_m.iloc[t - 13]) / close_m.iloc[t - 13]
    else:
        mom = (close_m.iloc[t] - close_m.iloc[0]) / close_m.iloc[0]
    rank = mom.sort_values(ascending=False)
    picks = list(rank.head(top_n).index)
    latest_day = max(df.index.max() for df in prices.values())
    out = []
    for sym in picks:
        px = float(prices[sym].loc[prices[sym].index <= latest_day]["close"].iloc[-1])
        out.append({"symbol": sym, "direction": "LONG", "price": px})
    return out


def current_h6_position(btc4h) -> list:
    """Infer H6's current position from its latest completed 4h bar signal.

    CryptoTrendStrategy.signal returns a dict {direction, entry_price, ...} when
    flat and a breakout is triggered, else None. Returns [{symbol, direction,
    price}] or [] if flat.
    """
    from edgelab.strategy.crypto_trend import CryptoTrendStrategy
    strat = CryptoTrendStrategy()
    i = len(btc4h) - 1
    if i < 200:
        return []
    sig = strat.signal(btc4h, i)
    if sig is None:
        return []
    px = float(sig.get("entry_price", btc4h.iloc[i]["close"]))
    direction = str(sig.get("direction", "LONG")).upper()
    return [{"symbol": "BTC/USDT", "direction": direction, "price": px}]
