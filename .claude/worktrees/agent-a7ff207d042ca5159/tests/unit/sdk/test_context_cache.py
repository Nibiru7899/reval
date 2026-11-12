"""P5-00: the in-process artifact cache never serves a stale artifact."""

import shutil
from pathlib import Path

import pytest

from reval.domain.evidence import Producer
from reval.manifest.loader import load_manifest
from reval.manifest.snapshot_builder import build_snapshot
from reval.sdk import DEFAULT_REGISTRY, Context
from reval.sdk import context as ctxmod

MINI = Path(__file__).resolve().parents[2] / "fixtures" / "mini_project"


def _ctx(root: Path) -> Context:
    manifest = load_manifest(root / "reval.yaml")
    snap = build_snapshot(root, manifest, DEFAULT_REGISTRY)
    meta = Producer(
        id="p",
        kind="physics_sim",
        quantities=("temp_peak",),
        depends_on=("data",),
        code_hash="x",
        fidelity=1,
        cost=1,
    )
    return Context(root, snap, meta)


@pytest.fixture
def mini(tmp_path: Path) -> Path:
    root = tmp_path / "mini"
    shutil.copytree(MINI, root)
    ctxmod.clear_artifact_cache()
    return root


def test_hit_returns_equal_but_independent_frame(mini: Path) -> None:
    a = _ctx(mini).load("data")
    b = _ctx(mini).load("data")
    assert len(ctxmod._CACHE) == 1
    assert a is not b
    a.iloc[0, 1] = 12345.0  # mutating a caller's copy must not leak into the cache
    c = _ctx(mini).load("data")
    assert c.iloc[0, 1] != 12345.0


def test_changed_artifact_is_never_stale(mini: Path) -> None:
    before = _ctx(mini).load("data")
    path = mini / "data" / "data.csv"
    text = path.read_text(encoding="utf-8").splitlines()
    text.append(text[-1].replace(text[-1].split(",")[0], "zz", 1))
    path.write_text("\n".join(text) + "\n", encoding="utf-8")
    after = _ctx(mini).load("data")
    assert len(after) == len(before) + 1


def test_same_hash_but_modified_file_misses(mini: Path) -> None:
    """Even a stale snapshot hash cannot hide an on-disk change (size/mtime are part of the key)."""
    ctx = _ctx(mini)
    first = ctx.load("data")
    path = mini / "data" / "data.csv"
    path.write_text(
        path.read_text(encoding="utf-8") + path.read_text(encoding="utf-8").splitlines()[-1] + "\n"
    )
    assert len(ctx.load("data")) == len(first) + 1


def test_no_hash_means_no_caching(mini: Path) -> None:
    ctx = _ctx(mini)
    ctx._snapshot = ctx._snapshot.model_copy(update={"versions": {}})
    ctxmod.clear_artifact_cache()
    ctx.load("data")
    assert len(ctxmod._CACHE) == 0
