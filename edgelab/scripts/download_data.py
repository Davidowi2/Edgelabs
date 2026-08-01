"""Download and format 5+ years of EURUSD H1 data.

Source: histdata.com (free, 1-minute bar quotes). We download M1 per year and
aggregate to hourly (H1) bars. Output is a clean CSV at data/EURUSD_H1_5y.csv
with columns: timestamp, open, high, low, close, volume (timestamp = YYYY-MM-DD HH:MM:SS, UTC).

Reproducible: re-running downloads the same source months and rebuilds the same file.
Gaps/NaNs are reported, never interpolated or filled.
"""

from __future__ import annotations

import io
import os
import zipfile
from datetime import datetime

import pandas as pd

import histdata

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "data")
TMP_DIR = os.path.join(ROOT, "_dl_tmp")
OUT_CSV = os.path.join(DATA_DIR, "EURUSD_H1_5y.csv")

PAIR = "eurusd"
START_YEAR = 2020


def _download_year(year: int, month: int | None = None) -> list[str]:
    os.makedirs(TMP_DIR, exist_ok=True)
    path = histdata.download_hist_data(
        year=str(year),
        month=(str(month) if month is not None else None),
        pair=PAIR,
        time_frame="M1",
        platform="ASCII",
        output_directory=TMP_DIR,
        verbose=False,
    )
    if isinstance(path, (list, tuple)):
        return list(path)
    return [path]


def _read_m1_csv(zippath: str) -> pd.DataFrame:
    with zipfile.ZipFile(zippath) as z:
        for name in z.namelist():
            if name.lower().endswith(".csv"):
                raw = z.read(name)
    df = pd.read_csv(
        io.BytesIO(raw),
        sep=";",
        header=None,
        names=["ts", "open", "high", "low", "close", "volume"],
    )
    df["ts"] = pd.to_datetime(df["ts"], format="%Y%m%d %H%M%S")
    df = df.set_index("ts").sort_index()
    df["volume"] = df["volume"].astype(float).fillna(0.0)
    return df


def _aggregate_h1(df: pd.DataFrame) -> pd.DataFrame:
    agg = df.resample("1h").agg(
        {
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
        }
    )
    return agg


def build() -> pd.DataFrame:
    now = datetime.now()
    frames: list[pd.DataFrame] = []
    failed: list[str] = []

    year = START_YEAR
    while year <= now.year:
        try:
            if year < now.year:
                zips = _download_year(year)
            else:
                # current year: download month by month up to current month
                for m in range(1, now.month + 1):
                    try:
                        zips = _download_year(year, m)
                    except Exception as e:  # noqa: BLE001
                        failed.append(f"{year}-{m:02d}: {e}")
                        continue
                    for zp in zips:
                        frames.append(_aggregate_h1(_read_m1_csv(zp)))
                year += 1
                continue
            for zp in zips:
                frames.append(_aggregate_h1(_read_m1_csv(zp)))
        except Exception as e:  # noqa: BLE001
            failed.append(f"{year}: {e}")
        year += 1

    if not frames:
        raise RuntimeError(f"No data downloaded. Failures: {failed}")

    combined = pd.concat(frames).sort_index()
    combined = combined[~combined.index.duplicated(keep="first")]

    # Report and drop hours with no M1 coverage (gaps), do not interpolate.
    total_hours = (combined.index[-1] - combined.index[0]).total_seconds() / 3600 + 1
    actual_hours = len(combined)
    nan_hours = int(combined[["open", "high", "low", "close"]].isna().any(axis=1).sum())
    combined = combined.dropna(subset=["open", "high", "low", "close"])

    combined["volume"] = combined["volume"].fillna(0.0)
    combined = combined[["open", "high", "low", "close", "volume"]]

    _print_summary(combined, total_hours, actual_hours, nan_hours, failed)
    return combined


def _print_summary(df: pd.DataFrame, total_hours, actual_hours, nan_hours, failed) -> None:
    first, last = df.index[0], df.index[-1]
    span_days = (last - first).days
    print("=== EURUSD H1 download summary ===")
    print(f"Rows (H1 bars): {len(df)}")
    print(f"First bar: {first}")
    print(f"Last bar:  {last}")
    print(f"Span (days): {span_days}  (~{span_days / 365.25:.2f} years)")
    print(f"Expected hourly slots: {int(total_hours)}")
    print(f"Actual hourly bars:    {actual_hours}")
    print(f"Gap hours (dropped, no M1 data): {nan_hours}")
    print(f"NaN rows after drop: 0")
    ohlc = df[["open", "high", "low", "close"]]
    print(f"Min price: {ohlc.values.min():.5f}  Max price: {ohlc.values.max():.5f}")
    if failed:
        print(f"Download failures ({len(failed)}):")
        for f in failed:
            print(f"  - {f}")
    else:
        print("Download failures: none")
    if span_days < 365.25 * 5:
        print("WARNING: less than 5 years of coverage.")


def main() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    df = build()
    out = df.reset_index()
    out = out.rename(columns={"index": "timestamp", "ts": "timestamp"})
    out["timestamp"] = out["timestamp"].dt.strftime("%Y-%m-%d %H:%M:%S")
    out["volume"] = out["volume"].round().astype(int)
    out = out[["timestamp", "open", "high", "low", "close", "volume"]]
    out.to_csv(OUT_CSV, index=False)
    print(f"Wrote {OUT_CSV} ({os.path.getsize(OUT_CSV)} bytes)")


if __name__ == "__main__":
    main()
