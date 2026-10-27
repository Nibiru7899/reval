"""Applicability domain (docs/04 A4, docs/10 section 5): range box plus kNN distance.

A row is *outside* when any raw feature leaves the training box (per-feature
quantiles of the training data), or when its mean distance to the ``k`` nearest
(standardized) training points exceeds tau, the ``dist_quantile`` quantile of
the same statistic on calibration rows. No I/O here.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np
from scipy.spatial import cKDTree  # type: ignore[import-untyped,unused-ignore]

from reval.domain.base import Frozen


class DomainReport(Frozen):
    """Outcome of an applicability-domain check."""

    inside: bool
    first_violation: int | None
    violating_features: tuple[str, ...]
    frac_outside: float
    max_knn_distance: float
    threshold: float
    box: dict[str, tuple[float, float]]

    def to_dict(self) -> dict[str, Any]:
        """JSON-compatible dict; goes into ``EvidenceResult.domain_report``."""
        return self.model_dump(mode="json")


def _as_2d(X: np.ndarray, n_features: int, name: str) -> np.ndarray:
    arr = np.asarray(X, dtype=float)
    if arr.ndim == 1:
        arr = arr.reshape(-1, n_features)
    if arr.ndim != 2 or arr.shape[1] != n_features:
        raise ValueError(f"{name} must have shape (n, {n_features}); got {arr.shape}")
    if not np.all(np.isfinite(arr)):
        raise ValueError(f"{name} contains non-finite values")
    return arr


class ApplicabilityDomain:
    """Range box + kNN-distance applicability domain, strict by default."""

    def __init__(
        self,
        feature_names: Sequence[str],
        k: int = 10,
        box_quantiles: tuple[float, float] = (0.005, 0.995),
        dist_quantile: float = 0.99,
        max_train_rows: int = 200_000,
    ) -> None:
        self.feature_names: tuple[str, ...] = tuple(feature_names)
        self.k = int(k)
        self.box_quantiles = (float(box_quantiles[0]), float(box_quantiles[1]))
        self.dist_quantile = float(dist_quantile)
        self.max_train_rows = int(max_train_rows)
        self._mean: np.ndarray | None = None
        self._std: np.ndarray | None = None
        self._train_z: np.ndarray | None = None
        self._lo: np.ndarray | None = None
        self._hi: np.ndarray | None = None
        self._tau: float | None = None
        self._tree: cKDTree | None = None

    def fit(self, X_train: np.ndarray, X_calib: np.ndarray) -> ApplicabilityDomain:
        """Fit on train rows; calibrate tau on calib rows (disjoint profiles from train)."""
        d = len(self.feature_names)
        train = _as_2d(X_train, d, "X_train")
        calib = _as_2d(X_calib, d, "X_calib")
        if len(train) == 0 or len(calib) == 0:
            raise ValueError("X_train and X_calib must be non-empty")
        mean = train.mean(axis=0)
        std = train.std(axis=0)
        std = np.where(std > 0, std, 1.0)  # zero-variance feature: avoid dividing by 0
        lo = np.quantile(train, self.box_quantiles[0], axis=0)
        hi = np.quantile(train, self.box_quantiles[1], axis=0)
        sub = train
        if len(sub) > self.max_train_rows:
            rng = np.random.default_rng(0)
            idx = np.sort(rng.choice(len(sub), self.max_train_rows, replace=False))
            sub = sub[idx]
        z = (sub - mean) / std
        self._mean, self._std, self._train_z, self._lo, self._hi = mean, std, z, lo, hi
        self._tree = cKDTree(z)
        calib_d = self._knn_mean((calib - mean) / std)
        self._tau = float(np.quantile(calib_d, self.dist_quantile))
        return self

    def _knn_mean(self, z: np.ndarray) -> np.ndarray:
        assert self._tree is not None and self._train_z is not None
        k = max(1, min(self.k, len(self._train_z)))
        dist, _ = self._tree.query(z, k=k, workers=1)
        dist = np.asarray(dist, dtype=float)
        return dist if dist.ndim == 1 else dist.mean(axis=1)

    def check(self, X: np.ndarray, *, min_inside_frac: float = 1.0) -> DomainReport:
        """Check rows. Strict (1.0): every row must pass; relaxed: 1 - frac_outside >= min_inside_frac."""
        if self._tau is None or self._lo is None or self._hi is None:
            raise RuntimeError("ApplicabilityDomain is not fitted")
        assert self._mean is not None and self._std is not None
        d = len(self.feature_names)
        arr = _as_2d(X, d, "X")
        box = {
            n: (float(a), float(b)) for n, a, b in zip(self.feature_names, self._lo, self._hi, strict=True)
        }
        if len(arr) == 0:
            return DomainReport(
                inside=True,
                first_violation=None,
                violating_features=(),
                frac_outside=0.0,
                max_knn_distance=0.0,
                threshold=self._tau,
                box=box,
            )
        out_box = (arr < self._lo) | (arr > self._hi)
        dist = self._knn_mean((arr - self._mean) / self._std)
        row_out = out_box.any(axis=1) | (dist > self._tau)
        frac = float(row_out.mean())
        first = int(np.argmax(row_out)) if row_out.any() else None
        viol: tuple[str, ...] = ()
        if first is not None:
            viol = tuple(sorted(n for n, v in zip(self.feature_names, out_box[first], strict=True) if v))
        strict = min_inside_frac >= 1.0
        inside = not bool(row_out.any()) if strict else (1.0 - frac) >= min_inside_frac
        return DomainReport(
            inside=inside,
            first_violation=first,
            violating_features=viol,
            frac_outside=frac,
            max_knn_distance=float(dist.max()),
            threshold=self._tau,
            box=box,
        )

    def to_dict(self) -> dict[str, Any]:
        """Plain-JSON state with an exact float round trip (no joblib)."""
        if self._tau is None:
            raise RuntimeError("ApplicabilityDomain is not fitted")
        assert self._mean is not None and self._std is not None
        assert self._train_z is not None and self._lo is not None and self._hi is not None
        return {
            "feature_names": list(self.feature_names),
            "k": self.k,
            "box_quantiles": list(self.box_quantiles),
            "dist_quantile": self.dist_quantile,
            "max_train_rows": self.max_train_rows,
            "mean": self._mean.tolist(),
            "std": self._std.tolist(),
            "lo": self._lo.tolist(),
            "hi": self._hi.tolist(),
            "tau": self._tau,
            "train_z": self._train_z.tolist(),
        }

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> ApplicabilityDomain:
        """Rebuild from :meth:`to_dict` output."""
        bq = d["box_quantiles"]
        obj = cls(
            d["feature_names"],
            k=int(d["k"]),
            box_quantiles=(float(bq[0]), float(bq[1])),
            dist_quantile=float(d["dist_quantile"]),
            max_train_rows=int(d["max_train_rows"]),
        )
        n = len(obj.feature_names)
        obj._mean = np.asarray(d["mean"], dtype=float)
        obj._std = np.asarray(d["std"], dtype=float)
        obj._lo = np.asarray(d["lo"], dtype=float)
        obj._hi = np.asarray(d["hi"], dtype=float)
        obj._train_z = np.asarray(d["train_z"], dtype=float).reshape(-1, n)
        obj._tau = float(d["tau"])
        obj._tree = cKDTree(obj._train_z)
        return obj
