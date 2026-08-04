"""Fetch XAUUSD H4 via Yahoo (GC=F, 2y cap on 1h) and Stooq fallback.

Yahoo 1h is capped to ~730 days, so we pull 2y of GC=F (gold futures) at 1h and
resample to 4h. If Yahoo fails we try Stooq (xauusd) which has longer history.
New helper script; no repo module modified.
"""
import sys
import pandas as pd

OUT = r"C:\Users\Legacy\Edgelabs\edgelab\data\XAUUSD_H4_raw.csv"


def fetch_yahoo():
    import yfinance as yf
    try:
        tk = yf.Ticker("GC=F")
        d = tk.history(interval="1h", period="2y", auto_adjust=False)
        if d is not None and len(d) > 500:
            print(f"YAHOO GC=F  ROWS_1H {len(d)}")
            return d
    except Exception as e:  # noqa: BLE001
        print("YAHOO_ERR", repr(e))
    return None


def fetch_stooq():
    # Stooq daily gold (xauusd) — longer history but daily only.
    url = "https://stooq.com/q/d/l/?s=xauusd&i=d"
    try:
        d = pd.read_csv(url)
        if d is not None and "Close" in d.columns and len(d) > 500:
            d = d.rename(columns={"Date": "timestamp"})
            d = d.set_index("timestamp")
            print(f"STOOQ xauusd  ROWS_D {len(d)}")
            return d
    except Exception as e:  # noqa: BLE001
        print("STOOQ_ERR", repr(e))
    return None


def to_h4(df, cols_map):
    ohlc = df[list(cols_map.keys())].copy()
    ohlc.columns = list(cols_map.values())
    h4 = ohlc.resample("4h").agg(
        {"open": "first", "high": "max", "low": "min",
         "close": "last", "volume": "sum"}
    ).dropna() if "volume" in ohlc.columns else ohlc.resample("4h").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"}
    ).dropna()
    return h4


def main():
    df = fetch_yahoo()
    src = "yahoo"
    if df is None:
        df = fetch_stooq()
        src = "stooq"
    if df is None:
        print("NO_DATA")
        sys.exit(1)
    cols = {"Open": "open", "High": "high", "Low": "low",
            "Close": "close", "Volume": "volume"}
    # stooq uses lowercase cols
    if src == "stooq":
        cols = {"Open": "open", "High": "high", "Low": "low", "Close": "close"}
    h4 = to_h4(df, cols)
    print(f"SRC {src}  ROWS_4H {len(h4)}  FIRST {h4.index[0]}  LAST {h4.index[-1]}  "
          f"SPAN_DAYS {(h4.index[-1]-h4.index[0]).days}")
    h4.reset_index().to_csv(OUT, index=False)
    print(f"SAVED {OUT} ({len(h4)} bars)")


if __name__ == "__main__":
    main()
