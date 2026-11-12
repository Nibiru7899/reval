"""Trajectory models M1-M3 and the peak evaluation harness (docs/05 section 3).

Models are fitted on ``train`` profiles only; the caller selects the rows (AGENTS rule 6).
Temperatures are absolute degrees C, errors are in K (rule 7).
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import TransformedTargetRegressor
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.neural_network import MLPRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from motor.features import make_features

TARGETS = ("pm", "stator_winding")
Kind = Literal["ridge", "hgb", "mlp"]
_KINDS = ("ridge", "hgb", "mlp")


def _make_estimator(kind: str, hyperparams: Mapping[str, Any]) -> Any:
    hp = dict(hyperparams)
    if kind == "ridge":
        return Pipeline([("scale", StandardScaler()), ("reg", Ridge(**{"alpha": 1.0, **hp}))])
    if kind == "hgb":
        return HistGradientBoostingRegressor(**{"random_state": 0, **hp})
    if kind == "mlp":
        reg = MLPRegressor(**{"random_state": 0, "hidden_layer_sizes": (32,), **hp})
        # Scalers are fitted on the rows passed to fit (train only), never on calib or test.
        return Pipeline(
            [
                ("scale", StandardScaler()),
                ("reg", TransformedTargetRegressor(regressor=reg, transformer=StandardScaler())),
            ]
        )
    raise ValueError(f"unknown model kind {kind!r}; expected one of {_KINDS}")


class TrajectoryModel:
    """One regressor per target on the causal-EWMA feature set."""

    def __init__(self, kind: Kind, targets: tuple[str, ...] = TARGETS, **hyperparams: Any) -> None:
        if kind not in _KINDS:
            raise ValueError(f"unknown model kind {kind!r}; expected one of {_KINDS}")
        self.kind: Kind = kind
        self.targets: tuple[str, ...] = tuple(targets)
        self.hyperparams: dict[str, Any] = dict(hyperparams)
        self.feature_names: list[str] = []
        self.estimators: dict[str, Any] = {}

    def features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Frame with all feature columns; computed from raw columns when missing."""
        if self.feature_names and all(c in df.columns for c in self.feature_names):
            return df
        return make_features(df)[0]

    def fit(self, df_train: pd.DataFrame) -> TrajectoryModel:
        """Fit on the given rows (the caller passes ``train`` profiles only)."""
        feats, names = make_features(df_train)
        self.feature_names = list(names)
        x = feats[self.feature_names].to_numpy(dtype=float)
        self.estimators = {}
        for t in self.targets:
            est = _make_estimator(self.kind, self.hyperparams)
            est.fit(x, feats[t].to_numpy(dtype=float))
            self.estimators[t] = est
        return self

    def predict(self, df: pd.DataFrame) -> pd.DataFrame:
        """Predict every target; the result is aligned to ``df.index``."""
        if not self.estimators:
            raise RuntimeError("model is not fitted")
        feats = self.features(df)
        x = feats[self.feature_names].to_numpy(dtype=float)
        return pd.DataFrame({t: self.estimators[t].predict(x) for t in self.targets}, index=feats.index)


def peaks(y: pd.Series, profile_ids: pd.Series, window_rows: int) -> np.ndarray:
    """Max of ``y`` over non-overlapping windows per profile; the trailing partial window is dropped."""
    if window_rows < 1:
        raise ValueError("window_rows must be >= 1")
    out: list[float] = []
    frame = pd.DataFrame({"y": np.asarray(y, dtype=float), "p": np.asarray(profile_ids)})
    for _, g in frame.groupby("p", sort=True):
        v = g["y"].to_numpy()
        for k in range(len(v) // window_rows):
            out.append(float(v[k * window_rows : (k + 1) * window_rows].max()))
    return np.asarray(out, dtype=float)


def evaluate(model: TrajectoryModel, df_test: pd.DataFrame, window_rows: int) -> dict[str, Any]:
    """Per-target MSE (K^2), max abs error (K) and peak MAE (K) over windows of ``window_rows``."""
    pred = model.predict(df_test)
    pid = df_test["profile_id"]
    result: dict[str, Any] = {}
    for t in model.targets:
        err = df_test[t].to_numpy(dtype=float) - pred[t].to_numpy(dtype=float)
        true_pk = peaks(df_test[t], pid, window_rows)
        pred_pk = peaks(pred[t], pid, window_rows)
        result[t] = {
            "mse": float(np.mean(err**2)),
            "max_abs_error": float(np.max(np.abs(err))),
            "peak_mae": float(np.mean(np.abs(true_pk - pred_pk))) if len(true_pk) else float("nan"),
            "n_peaks": len(true_pk),
        }
    return result


def save(model: TrajectoryModel, path: Path, *, meta: Mapping[str, Any]) -> None:
    """Write the model with joblib and a sidecar ``.json`` holding ``meta``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, path)
    sidecar = {"kind": model.kind, "targets": list(model.targets), **dict(meta)}
    path.with_suffix(".json").write_text(
        json.dumps(sidecar, indent=2, sort_keys=True, default=str), encoding="utf-8"
    )


def load(path: Path) -> TrajectoryModel:
    """Load a model written by :func:`save`."""
    model = joblib.load(path)
    if not isinstance(model, TrajectoryModel):
        raise TypeError(f"{path} does not contain a TrajectoryModel")
    return model
