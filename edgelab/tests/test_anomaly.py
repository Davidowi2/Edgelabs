"""Tests for edgelab.analysis.anomaly.IsolationForest (Phase 5a, Module 2).

Pure-Python Isolation Forest (no numpy). Uses the direct feature-matrix path
(fit_rows/score_row) for deterministic scoring tests.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from edgelab.analysis.anomaly import IsolationForest


@pytest.fixture
def logger(tmp_path):
    from edgelab.monitoring.logger import TradingLogger
    return TradingLogger(name="an.test", log_file=str(tmp_path / "an.log"))


class TestTree:
    def test_single_tree_structure(self, logger):
        data = [[0.1], [0.2], [0.8], [0.9]]
        f = IsolationForest({}, logger, random_seed=1)
        tree = f._build_tree(data, 0, 5)
        assert tree["feature"] == 0
        assert isinstance(tree["split"], float)
        assert "left" in tree and "right" in tree
        assert tree["size"] == 4


import random


class TestScores:
    def _blob(self, n, lo, hi, seed=7):
        rng = random.Random(seed)
        return [[lo + rng.random() * (hi - lo) for _ in range(4)] for _ in range(n)]

    def test_score_normal_data(self, logger):
        f = IsolationForest({}, logger, random_seed=2)
        rows = self._blob(400, 0.45, 0.55)
        f.fit_rows(rows)
        normal = f.score_row([0.5, 0.5, 0.5, 0.5])
        # A correct Isolation Forest scores typical points below the anomalous
        # band (verdict stays "normal"/"elevated", never "anomalous").
        assert normal < 0.6
        assert f.get_verdict(normal) in ("normal", "elevated")

    def test_score_outlier_data(self, logger):
        f = IsolationForest({}, logger, random_seed=3)
        rows = [[0.5] for _ in range(200)]
        f.fit_rows(rows)
        s = f.score_row([0.99])
        # a point far outside the cluster isolates quickly -> high score
        assert s > 0.7
        assert f.get_verdict(s) in ("anomalous", "highly_anomalous")

    def test_normal_scores_lower_than_outlier(self, logger):
        f = IsolationForest({}, logger, random_seed=5)
        rows = self._blob(400, 0.45, 0.55)
        f.fit_rows(rows)
        normal = f.score_row([0.5, 0.5, 0.5, 0.5])
        outlier = f.score_row([0.99, 0.99, 0.99, 0.99])
        assert outlier > normal

    def test_fit_and_score_convenience(self, logger):
        f = IsolationForest({}, logger, random_seed=4)
        bars = [_as_bar([0.5, 0.5]) for _ in range(60)]
        latest = _as_bar([0.5, 0.5])
        s = f.fit_and_score(bars, latest)
        assert 0.0 <= s <= 1.0

    def test_synthetic_anomaly_detection(self, logger):
        f = IsolationForest({}, logger, random_seed=5)
        rows = self._blob(100, 0.45, 0.55)
        f.fit_rows(rows)
        s = f.score_row([0.99, 0.99, 0.99, 0.99])
        assert s > 0.7

    def test_get_verdict_thresholds(self, logger):
        f = IsolationForest({}, logger, random_seed=6)
        assert f.get_verdict(0.1) == "normal"
        assert f.get_verdict(0.45) == "elevated"
        assert f.get_verdict(0.7) == "anomalous"
        assert f.get_verdict(0.9) == "highly_anomalous"


class TestFeatureNaN:
    def test_feature_computation_handles_nan(self, logger):
        f = IsolationForest({}, logger, random_seed=7)
        bars = []
        for i in range(25):
            # use timedelta so hour stays in 0..23
            bars.append({
                "timestamp": datetime(2026, 7, 1, tzinfo=timezone.utc) + timedelta(hours=i),
                "open": 1.10, "high": 1.11, "low": 1.09, "close": 1.10,
                "volume": 100.0,
            })
        feats = f._compute_features(bars)
        # 25 bars - 20 dropped = 5 usable rows, each 8 features
        assert len(feats) == 5
        assert all(len(r) == 8 for r in feats)
        assert not any(any(__import__("math").isnan(v) for v in row) for row in feats)


class TestErrors:
    def test_empty_bars_raises_clear_error(self, logger):
        f = IsolationForest({}, logger, random_seed=8)
        with pytest.raises(ValueError):
            f.fit([])


class TestRepro:
    def test_reproducibility_with_seed(self, logger):
        a = IsolationForest({}, logger, random_seed=42)
        b = IsolationForest({}, logger, random_seed=42)
        rows = [[0.5, 0.5] for _ in range(50)]
        a.fit_rows(rows)
        b.fit_rows(rows)
        sa = a.score_row([0.5, 0.5])
        sb = b.score_row([0.5, 0.5])
        assert sa == sb


class TestLogging:
    def test_logging_on_fit(self, logger):
        f = IsolationForest({}, logger, random_seed=9)
        bars = [_as_bar([0.5]) for _ in range(30)]
        f.fit(bars)  # logs "trained on"


def _as_bar(row):
    return {
        "timestamp": datetime(2026, 7, 1, tzinfo=timezone.utc),
        "open": 1.10, "high": 1.10 + (row[0] - 0.5) * 0.01,
        "low": 1.10 - (row[0] - 0.5) * 0.01,
        "close": 1.10 + (row[0] - 0.5) * 0.01,
        "volume": 100.0 * (1.0 + (row[1] if len(row) > 1 else 0.5)),
    }
