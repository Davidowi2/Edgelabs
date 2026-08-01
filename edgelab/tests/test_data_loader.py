"""Tests for the CSV data loader."""

from __future__ import annotations

import pandas as pd
import pytest

from edgelab.data.loader import load_csv, validate_dataframe


class TestLoadCSV:
    def test_loads_valid_csv(self, tmp_path):
        p = tmp_path / "data.csv"
        p.write_text("timestamp,open,high,low,close,volume\n2026-01-01,1.1,1.2,1.0,1.15,100\n")
        df = load_csv(p)
        assert not df.empty
        assert list(df.columns)[:6] == ["timestamp", "open", "high", "low", "close", "volume"]

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_csv(tmp_path / "nope.csv")

    def test_empty_file_raises(self, tmp_path):
        p = tmp_path / "empty.csv"
        p.write_text("")
        with pytest.raises(ValueError):
            load_csv(p)

    def test_load_csv_passes_kwargs(self, tmp_path):
        p = tmp_path / "data.csv"
        p.write_text("a,b\n1,2\n3,4\n")
        df = load_csv(p)
        assert len(df) == 2


class TestValidateDataframe:
    def test_valid_passes(self):
        df = pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])
        # should not raise
        validate_dataframe(df)

    def test_missing_columns_raises(self):
        df = pd.DataFrame(columns=["open", "high", "low", "close"])
        with pytest.raises(ValueError) as exc:
            validate_dataframe(df)
        assert "timestamp" in str(exc.value)
        assert "volume" in str(exc.value)

    def test_case_insensitive_columns(self):
        df = pd.DataFrame(columns=["TIMESTAMP", "Open", "HIGH", "Low", "Close", "Volume"])
        validate_dataframe(df)
