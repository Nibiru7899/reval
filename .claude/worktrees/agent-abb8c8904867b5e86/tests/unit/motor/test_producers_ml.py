"""P4-03: ML producers (metadata, interval=None path, data-backed domain checks)."""

from __future__ import annotations

import importlib
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any, ClassVar

import numpy as np
import pytest

from reval.domain.engineering import Subject
from reval.domain.evidence import ProducerKind
from reval.sdk import DEFAULT_REGISTRY

ROOT = Path(__file__).resolve().parents[3] / "examples" / "motor_thermal"
MODELS = ("ridge", "hgb", "mlp")


@pytest.fixture
def producers() -> Iterator[Any]:
    import motor.producers as mp

    DEFAULT_REGISTRY.clear()
    mp = importlib.reload(mp)
    yield mp
    DEFAULT_REGISTRY.clear()


def test_registered_metadata(producers: Any) -> None:
    for m in MODELS:
        for name, quantity, art in (("pm", "pm_peak", "tpm"), ("sw", "sw_peak", "tsw")):
            meta = DEFAULT_REGISTRY.get(f"predict_{name}_peak_{m}").meta
            assert meta.kind is ProducerKind.ML_PREDICTION
            assert meta.quantities == (quantity,)
            assert meta.predictors == (f"{art}_{m}",)
            deps = set(meta.depends_on)
            assert {f"{art}_{m}", f"uq_{art}_{m}", "drive_map", "cooling#/flow_scale"} <= deps


class _FakeAD:
    @staticmethod
    def from_dict(_: Any) -> Any:
        return SimpleNamespace(check=lambda x, **kw: _report(True))


def _report(inside: bool) -> Any:
    from reval.uq.domain import DomainReport

    return DomainReport(
        inside=inside,
        first_violation=None if inside else 0,
        violating_features=() if inside else ("coolant",),
        frac_outside=0.0 if inside else 1.0,
        max_knn_distance=0.0,
        threshold=1.0,
        box={},
    )


def test_interval_none_when_q_is_infinite(producers: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    import pandas as pd

    class Model:
        feature_names: ClassVar[list[str]] = ["f"]

        def predict(self, feats: Any) -> Any:
            return pd.DataFrame({"pm": np.array([50.0, 70.0])})

    cycle = pd.DataFrame(
        {"torque": [1.0, 2.0], "motor_speed": [3.0, 4.0], "coolant": [20.0, 21.0], "ambient": [22.0, 23.0]}
    )
    feats = pd.DataFrame({"f": [0.0, 1.0]})
    monkeypatch.setattr(producers, "_ml_features", lambda s, c, d: (feats, cycle, _report(True)))
    monkeypatch.setattr(producers, "ApplicabilityDomain", _FakeAD)
    uq = {"ad": {}, "conformal": SimpleNamespace(interval=lambda t, p, c: None)}
    store = {"tpm_ridge": Model(), "uq_tpm_ridge": uq, "drive_map": object()}
    ctx = SimpleNamespace(load=lambda k: store[k])
    subj = Subject(id="s", kind="duty_cycle", generator="motor.cycles:blocks", params={})
    out = producers._predict_peak(subj, ctx, "pm_peak", "ridge")
    r = out.results[0]
    assert r.interval is None and r.point == 70.0 and r.uncertainty_kind == "none"
    assert r.in_domain is True
    assert out.scope.box["coolant"] == (20.0, 21.0)

    uq["conformal"] = SimpleNamespace(interval=lambda t, p, c: (p - 3.0, p + 3.0))
    r = producers._predict_peak(subj, ctx, "pm_peak", "ridge").results[0]
    assert r.uncertainty_kind == "conformal" and r.interval is not None and r.interval.hi == 73.0


class _GateAD:
    """AD stub that is outside under the strict gate and inside once ``min_inside_frac < 1`` (relaxed)."""

    @staticmethod
    def from_dict(_: Any) -> Any:
        return SimpleNamespace(check=lambda x, min_inside_frac=1.0: _report(min_inside_frac < 1.0))


def _predict(producers: Any, monkeypatch: pytest.MonkeyPatch, settings: Any) -> Any:
    import pandas as pd

    from reval.domain.settings import ReValSettings

    class Model:
        feature_names: ClassVar[list[str]] = ["f"]

        def predict(self, feats: Any) -> Any:
            return pd.DataFrame({"pm": np.array([50.0, 70.0])})

    cycle = pd.DataFrame(
        {"torque": [1.0, 2.0], "motor_speed": [3.0, 4.0], "coolant": [20.0, 21.0], "ambient": [22.0, 23.0]}
    )
    feats = pd.DataFrame({"f": [0.0, 1.0]})
    monkeypatch.setattr(producers, "_ml_features", lambda s, c, d: (feats, cycle, _report(True)))
    monkeypatch.setattr(producers, "ApplicabilityDomain", _GateAD)
    uq = {"ad": {}, "conformal": SimpleNamespace(interval=lambda t, p, c: (p - 3.0, p + 3.0))}
    store = {"tpm_ridge": Model(), "uq_tpm_ridge": uq, "drive_map": object()}
    ctx = SimpleNamespace(load=lambda k: store[k], settings=settings or ReValSettings())
    subj = Subject(id="s", kind="duty_cycle", generator="motor.cycles:blocks", params={})
    return producers._predict_peak(subj, ctx, "pm_peak", "ridge").results[0]


def test_default_settings_keep_conformal_and_strict_gate(
    producers: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    r = _predict(producers, monkeypatch, None)
    assert r.uncertainty_kind == "conformal" and r.in_domain is False  # strict gate: stub is outside
    assert r.interval is not None and (r.interval.lo, r.interval.hi) == (67.0, 73.0)


def test_a4_relaxed_gate_changes_domain_verdict(producers: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    from reval.domain.settings import ReValSettings

    r = _predict(producers, monkeypatch, ReValSettings(ad_gate="relaxed"))
    assert r.in_domain is True


def test_a4_off_forces_in_domain(producers: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    from reval.domain.settings import ReValSettings

    r = _predict(producers, monkeypatch, ReValSettings(ad_gate="off"))
    assert r.in_domain is True


def test_a5_fixed_margin_replaces_conformal_interval(producers: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    from reval.domain.settings import ReValSettings

    r = _predict(producers, monkeypatch, ReValSettings(interval_method="fixed_margin"))
    assert r.uncertainty_kind != "conformal"
    assert r.interval is not None and (r.interval.lo, r.interval.hi) == (65.0, 75.0)


def test_a8_cqr_raises_until_quantile_models_exist(producers: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    from reval.domain.settings import ReValSettings
    from reval.errors import ProducerError

    with pytest.raises(ProducerError, match="Q-P5-19"):
        _predict(producers, monkeypatch, ReValSettings(interval_method="cqr"))


_PARQUET = ROOT / "data" / "processed" / "measures.parquet"
_needs_data = pytest.mark.skipif(
    not (_PARQUET.exists() and (ROOT / "models" / "uq_tpm_ridge.joblib").exists()), reason="no data/models"
)


@pytest.mark.data
@_needs_data
def test_recorded_in_domain_and_hot_coolant_out(producers: Any) -> None:
    import joblib
    import pandas as pd
    from motor.models import load

    from reval.services import project  # noqa: F401  (ensures package import)

    df = pd.read_parquet(_PARQUET)
    drive_map = joblib.load(ROOT / "models" / "drive_map.joblib")
    store = {
        "measures": df,
        "drive_map": drive_map,
        "tpm_ridge": load(ROOT / "models" / "tpm_ridge.joblib"),
        "uq_tpm_ridge": joblib.load(ROOT / "models" / "uq_tpm_ridge.joblib"),
    }
    ctx = SimpleNamespace(load=lambda k: store[k])
    import yaml

    sub = yaml.safe_load((ROOT / "subjects.yaml").read_text(encoding="utf-8"))["DC-R02"]
    subj = Subject(id="DC-R02", kind="duty_cycle", generator=sub["generator"], params=sub["params"])
    r = producers._predict_peak(subj, ctx, "pm_peak", "ridge").results[0]
    assert r.in_domain is True, r.domain_report
    assert r.interval is not None

    hot = Subject(
        id="hot",
        kind="duty_cycle",
        generator="motor.cycles:blocks",
        params={"blocks": [[50.0, 2000.0, 600]], "coolant": 95.0, "ambient": 25.0},
    )
    r = producers._predict_peak(hot, ctx, "pm_peak", "ridge").results[0]
    assert r.in_domain is False
    parts = r.domain_report["parts"]
    assert "coolant" in parts["drive_map"]["violating_features"] + parts["model"]["violating_features"]
