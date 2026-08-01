"""Data loader for EdgeLab."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd


def load_csv(path: str | Path, **kwargs) -> pd.DataFrame:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Data file not found: {path}")
    df = pd.read_csv(path, **kwargs)
    if df.empty:
        raise ValueError(f"Data file is empty: {path}")
    return df


def validate_dataframe(df: pd.DataFrame) -> None:
    required = {"timestamp", "open", "high", "low", "close", "volume"}
    missing = required.difference({col.lower() for col in df.columns})
    if missing:
        raise ValueError(f"Missing required columns: {missing}")
