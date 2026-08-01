"""Isolation Forest anomaly detector for EdgeLab (Phase 5a, Module 2).

Implemented FROM SCRATCH in pure Python (no numpy/sklearn). On-demand: fit a
forest on historical bars, then score a new bar's anomaly (0=normal, 1=weird).
Feature computation uses only the standard library. Pure list-of-lists.
"""

from __future__ import annotations

import math
import random
from datetime import datetime
from typing import List, Optional

from edgelab.monitoring.logger import TradingLogger

DEFAULT_FEATURES = [
    "return", "range_atr_ratio", "volume_ratio", "spread_ratio",
    "hour_sin", "hour_cos", "dow_sin", "dow_cos",
]


class IsolationForest:
    def __init__(self, config: dict, logger: TradingLogger, random_seed: Optional[int] = None) -> None:
        self._logger = logger
        cfg = config or {}
        self.n_trees = int(cfg.get("n_trees", 20))
        self.sample_size = int(cfg.get("sample_size", 256))
        self.feature_cols = cfg.get("feature_cols", list(DEFAULT_FEATURES))
        self._rng = random.Random(random_seed)
        self._trees: List[dict] = []

    # ---------- tree building ----------
    def _build_tree(self, data: List[List[float]], depth: int, max_depth: int) -> Optional[dict]:
        if not data or len(data) <= 1 or depth >= max_depth:
            return {"feature": -1, "split": 0.0, "left": None, "right": None, "size": len(data)}
        n_feat = len(data[0])
        feat = self._rng.randrange(n_feat)
        col = [row[feat] for row in data]
        lo, hi = min(col), max(col)
        if hi == lo:
            return {"feature": -1, "split": lo, "left": None, "right": None, "size": len(data)}
        split = lo + self._rng.random() * (hi - lo)
        left = [r for r in data if r[feat] <= split]
        right = [r for r in data if r[feat] > split]
        return {
            "feature": feat,
            "split": split,
            "left": self._build_tree(left, depth + 1, max_depth),
            "right": self._build_tree(right, depth + 1, max_depth),
            "size": len(data),
        }

    def _path_length(self, point: List[float], tree: dict, depth: int) -> float:
        if tree is None or tree["feature"] == -1:
            return float(depth)
        feat = tree["feature"]
        if point[feat] <= tree["split"]:
            return self._path_length(point, tree["left"], depth + 1)
        return self._path_length(point, tree["right"], depth + 1)

    @staticmethod
    def _c(n: int) -> float:
        if n <= 1:
            return 0.0
        return 2.0 * (math.log(n - 1) + 0.5772156649) - 2.0 * (n - 1) / n

    def _compute_anomaly_score(self, point: List[float], trees: List[dict]) -> float:
        if not trees:
            return 0.0
        lengths = [self._path_length(point, t, 0) for t in trees]
        avg = sum(lengths) / len(lengths)
        c = self._c(self.sample_size)
        if c == 0.0:
            return 0.0
        return 2.0 ** (-avg / c)

    # ---------- features ----------
    def _compute_features(self, bars: List[dict]) -> List[List[float]]:
        n = len(bars)
        closes = [b["close"] for b in bars]
        highs = [b["high"] for b in bars]
        lows = [b["low"] for b in bars]
        vols = [b["volume"] for b in bars]
        out: List[List[float]] = []
        for i in range(n):
            if i < 20:
                continue  # need 20-bar window for ATR/avg volume
            # return (close-close_prev)
            ret = closes[i] - closes[i - 1]
            # 20-bar ATR
            rngs = [highs[j] - lows[j] for j in range(i - 19, i + 1)]
            atr = sum(rngs) / 20.0
            range_atr = (highs[i] - lows[i]) / atr if atr > 0 else 1.0
            avg_vol = sum(vols[j] for j in range(i - 19, i + 1)) / 20.0
            vol_ratio = vols[i] / avg_vol if avg_vol > 0 else 1.0
            spread_ratio = 1.0  # placeholder, no spread data
            ts = bars[i]["timestamp"]
            if isinstance(ts, datetime):
                h = ts.hour + ts.minute / 60.0
                dow = ts.weekday()
            else:
                h, dow = 0.0, 0
            hr = (h / 24.0) * 2 * math.pi
            dr = (dow / 7.0) * 2 * math.pi
            out.append([
                ret, range_atr, vol_ratio, spread_ratio,
                math.sin(hr), math.cos(hr), math.sin(dr), math.cos(dr),
            ])
        return out

    # ---------- public ----------
    def fit_rows(self, rows: List[List[float]]) -> None:
        """Fit directly on a precomputed feature matrix (list of lists)."""
        if len(rows) < 2:
            raise ValueError(
                f"IsolationForest needs >= 2 feature rows, got {len(rows)}"
            )
        max_depth = int(math.ceil(math.log2(self.sample_size))) + 1
        self._trees = []
        for _ in range(self.n_trees):
            sample = rows
            if len(rows) > self.sample_size:
                sample = self._rng.sample(rows, self.sample_size)
            self._trees.append(self._build_tree(sample, 0, max_depth))
        self._logger.info("Isolation Forest trained", n_rows=len(rows),
                          n_features=len(self.feature_cols), n_trees=len(self._trees))

    def fit(self, bars: List[dict]) -> None:
        if not bars:
            raise ValueError("IsolationForest.fit requires non-empty bars (got empty list)")
        feats = self._compute_features(bars)
        if len(feats) < 2:
            raise ValueError(
                f"IsolationForest.fit needs >= 22 bars for features, got {len(feats)} usable rows"
            )
        self.fit_rows(feats)

    def score_row(self, point: List[float]) -> float:
        if not self._trees:
            return 0.0
        s = self._compute_anomaly_score(point, self._trees)
        self._logger.debug("anomaly score", score=round(s, 4))
        return s

    def score(self, latest_bar: dict) -> float:
        feats = self._compute_features([latest_bar])
        if not feats:
            self._logger.debug("anomaly score: no feature row")
            return 0.0
        return self.score_row(feats[0])

    def fit_and_score(self, bars: List[dict], latest_bar: dict) -> float:
        self.fit(bars)
        return self.score(latest_bar)

    def get_verdict(self, score: float) -> str:
        if score < 0.3:
            return "normal"
        if score < 0.6:
            return "elevated"
        if score < 0.8:
            return "anomalous"
        return "highly_anomalous"
