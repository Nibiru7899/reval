"""Producer SDK: decorator validation, registry, Context rules (D11), code hash (D16)."""

import shutil
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from reval.core.canonical import content_id
from reval.domain import Artifact, ArtifactKind, Producer, ProducerKind, Snapshot
from reval.domain.engineering import Assumption
from reval.errors import ProducerError, UndeclaredDependencyError
from reval.sdk import (
    DEFAULT_REGISTRY,
    Context,
    ProducerOutput,
    ProducerRegistry,
    code_hash,
    exact_result,
    interval_result,
    producer,
)

MINI = Path(__file__).resolve().parents[2] / "fixtures" / "mini_project"


def _snapshot() -> Snapshot:
    fields: dict[str, Any] = {
        "git_rev": None,
        "manifest_hash": "m",
        "quantities": {"temp_peak": "degC"},
        "artifacts": {
            "params": Artifact(
                id="params", kind=ArtifactKind.PARAMS, path="params/params.yaml", hasher="yaml-fields"
            ),
            "data": Artifact(
                id="data", kind=ArtifactKind.DATASET, path="data/data.csv", hasher="dataframe", key=("group",)
            ),
            "surrogate": Artifact(
                id="surrogate",
                kind=ArtifactKind.MODEL,
                path="models/surrogate.json",
                hasher="model",
                derived_from=("data",),
            ),
        },
        "versions": {},
        "assumptions": {
            "A-ambient": Assumption(
                id="A-ambient", statement="s", variable="ambient", unit="degC", bounds=(10, 40)
            )
        },
        "requirements": {},
        "subjects": {},
        "claims": {},
        "policies": {},
        "producers": {},
    }
    probe = Snapshot.model_construct(id="", **fields)
    return Snapshot(id=content_id(probe, exclude=frozenset({"id", "git_rev"})), **fields)


def _meta(depends_on: tuple[str, ...], assumes: tuple[str, ...] = ()) -> Producer:
    return Producer(
        id="t:p",
        kind=ProducerKind.ANALYTIC,
        quantities=("temp_peak",),
        fidelity=3,
        cost=1.0,
        code_hash="h",
        depends_on=depends_on,
        assumes=assumes,
    )


def _ctx(depends_on: tuple[str, ...], assumes: tuple[str, ...] = ()) -> Context:
    return Context(MINI, _snapshot(), _meta(depends_on, assumes))


def test_undeclared_artifact_raises() -> None:
    with pytest.raises(UndeclaredDependencyError):
        _ctx(("params#/load/scale",)).load("data")


def test_pointer_only_deps_load_raises_but_param_works() -> None:
    ctx = _ctx(("params#/load/scale",))
    with pytest.raises(UndeclaredDependencyError):
        ctx.load("params")
    assert ctx.param("params#/load/scale") == 1.0


def test_param_outside_declared_subtree_raises() -> None:
    ctx = _ctx(("params#/load/scale",))
    with pytest.raises(UndeclaredDependencyError):
        ctx.param("params#/sim/gain")
    with pytest.raises(UndeclaredDependencyError):
        ctx.param("params#/load")  # wider than the declaration
    with pytest.raises(ProducerError):
        _ctx(("params",)).param("params#/nope/x")


def test_column_deps_return_declared_columns_plus_key() -> None:
    df = _ctx(("data[temp]",)).load("data")
    assert isinstance(df, pd.DataFrame)
    assert sorted(df.columns) == ["group", "temp"]
    assert len(df) == 60


def test_whole_dep_returns_everything() -> None:
    assert sorted(_ctx(("data",)).load("data").columns) == ["group", "temp", "x"]
    assert _ctx(("surrogate",)).load("surrogate") == {"slope": 10.0, "intercept": 20.0}


def test_assumption_must_be_declared() -> None:
    assert _ctx(("params",), ("A-ambient",)).assumption("A-ambient").bounds == (10, 40)
    with pytest.raises(UndeclaredDependencyError):
        _ctx(("params",)).assumption("A-ambient")


def test_seed_is_deterministic() -> None:
    assert _ctx(("params",)).seed == _ctx(("params",)).seed
    assert 0 <= _ctx(("params",)).seed < 2**32


def _noop(subject: object, ctx: object) -> ProducerOutput:
    return ProducerOutput(results=())


def test_decorator_validates_predictors_and_duplicates() -> None:
    reg = ProducerRegistry()
    with pytest.raises(ValueError):
        producer(
            kind="ml_prediction", quantity="q", cost=1, depends_on=["a"], predictors=["b"], registry=reg
        )(_noop)
    producer(kind="analytic", quantity="q", cost=1, id="dup", registry=reg)(_noop)
    with pytest.raises(ValueError, match="duplicate"):
        producer(kind="analytic", quantity="q", cost=1, id="dup", registry=reg)(_noop)
    assert [rp.meta.id for rp in reg.all()] == ["dup"]
    assert reg.get("dup").meta.fidelity == 3


@pytest.fixture
def mini_copy(tmp_path: Path) -> Iterator[Path]:
    dst = tmp_path / "proj"
    shutil.copytree(MINI, dst, ignore=shutil.ignore_patterns("__pycache__"))
    yield dst
    for name in [m for m in sys.modules if m == "mini" or m.startswith("mini.")]:
        del sys.modules[name]
    sys.path[:] = [p for p in sys.path if p != str(dst.resolve())]
    DEFAULT_REGISTRY._items.clear()  # keep the global registry clean for other tests


def test_mini_producers_load_and_code_hash_tracks_helper_edits(mini_copy: Path) -> None:
    DEFAULT_REGISTRY.load_modules(["mini.producers"], mini_copy)
    ids = [rp.meta.id for rp in DEFAULT_REGISTRY.all()]
    assert ids == [
        "mini.producers:measure_temp",
        "mini.producers:predict_temp",
        "mini.producers:shaft_check",
        "mini.producers:sim_temp",
    ]
    rp = DEFAULT_REGISTRY.get("mini.producers:predict_temp")
    assert rp.meta.code_hash not in ("unloaded", "")
    assert rp.meta.predictors == ("surrogate",)
    assert rp.meta.depends_on == ("data[temp,x]", "params#/load/scale", "surrogate")
    before = code_hash(rp.fn, mini_copy)
    assert before == rp.meta.code_hash
    helper = mini_copy / "mini" / "helpers.py"
    helper.write_text(helper.read_text(encoding="utf-8") + "\n# edit\n", encoding="utf-8")
    assert code_hash(rp.fn, mini_copy) != before
    # same package, different function: the qualname differentiates
    assert code_hash(DEFAULT_REGISTRY.get("mini.producers:sim_temp").fn, mini_copy) != code_hash(
        rp.fn, mini_copy
    )


def test_result_helpers() -> None:
    r = interval_result("temp_peak", "degC", 40.0, 39.5, 40.5, uncertainty_kind="conformal", in_domain=True)
    assert r.interval is not None and r.interval.width == 1.0 and r.in_domain is True
    e = exact_result("shaft_d", "mm", 30.0)
    assert e.point == 30.0 and e.uncertainty_kind == "exact"
