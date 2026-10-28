"""P5-00: in-process caches make warm ML producer runs cheaper and never change the evidence."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3] / "examples" / "motor_thermal"
_needs = pytest.mark.skipif(
    not (
        (ROOT / "data" / "processed" / "measures.parquet").exists()
        and (ROOT / "models" / "uq_tpm_ridge.joblib").exists()
    ),
    reason="no data/models",
)


@pytest.mark.data
@pytest.mark.slow
@_needs
def test_warm_run_is_faster_with_identical_evidence() -> None:
    import sys

    from reval.manifest.loader import load_manifest
    from reval.manifest.snapshot_builder import build_snapshot
    from reval.sdk import DEFAULT_REGISTRY
    from reval.sdk import context as ctxmod
    from reval.sdk.runner import run_producer

    for m in [m for m in sys.modules if m.split(".")[0] == "motor"]:
        del sys.modules[m]
    DEFAULT_REGISTRY.clear()
    manifest = load_manifest(ROOT / "reval.yaml")
    DEFAULT_REGISTRY.load_modules(list(manifest.producers), ROOT)
    import motor.producers as mp

    snap = build_snapshot(ROOT, manifest, DEFAULT_REGISTRY)
    subject = snap.subjects["DC-P01"]
    ctxmod.clear_artifact_cache()
    mp._AD_CACHE.clear()

    t0 = time.perf_counter()
    cold = run_producer(DEFAULT_REGISTRY, "predict_pm_peak_ridge", subject, snap, ROOT)
    t_cold = time.perf_counter() - t0
    t0 = time.perf_counter()
    warm = run_producer(DEFAULT_REGISTRY, "predict_pm_peak_ridge", subject, snap, ROOT)
    t_warm = time.perf_counter() - t0
    print(f"cold {t_cold:.2f}s warm {t_warm:.2f}s")

    assert [e.id for e in cold] == [e.id for e in warm]
    assert t_warm < t_cold
    # a different artifact hash must be a different AD cache entry
    assert all(k[1] != "missing" for k in mp._AD_CACHE)
    DEFAULT_REGISTRY.clear()
