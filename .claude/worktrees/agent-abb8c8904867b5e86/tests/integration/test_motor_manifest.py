"""P2-13: the motor manifest end to end (snapshot --write, run --all, status) in a temp copy."""

from __future__ import annotations

import shutil
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from typer.testing import CliRunner, Result

from reval.cli.main import app
from reval.sdk import DEFAULT_REGISTRY
from reval.services import Project

ROOT = Path(__file__).resolve().parents[2] / "examples" / "motor_thermal"
PARQUET = ROOT / "data" / "processed" / "measures.parquet"
_MODELS_USED = ("drive_map.joblib", "lptn_report.json")
_STUBBED = [f"{p}_{m}.joblib" for p in ("tpm", "tsw") for m in ("ridge", "hgb", "mlp")]

pytestmark = [
    pytest.mark.data,
    pytest.mark.slow,
    pytest.mark.skipif(
        not PARQUET.exists() or not (ROOT / "models" / "drive_map.joblib").exists(),
        reason="processed motor data / fitted models not available",
    ),
]
runner = CliRunner()


@pytest.fixture
def project(tmp_path: Path) -> Iterator[Path]:
    """Private copy: code, params, subjects, the two models the producers read, the parquet.

    The six ML model files are only hashed in P2-13 (their producers arrive in P4-03), so stubs suffice.
    """
    dst = tmp_path / "motor"
    shutil.copytree(
        ROOT,
        dst,
        ignore=shutil.ignore_patterns(
            "__pycache__", ".reval", "raw", "models", "notebooks", "reval.lock.json", "README.md"
        ),
    )
    (dst / "models").mkdir()
    for name in _MODELS_USED:
        shutil.copy(ROOT / "models" / name, dst / "models" / name)
    for name in _STUBBED:
        (dst / "models" / name).write_bytes(b"stub")
    yield dst
    for name in [m for m in sys.modules if m == "motor" or m.startswith("motor.")]:
        del sys.modules[name]
    sys.path[:] = [p for p in sys.path if p != str(dst.resolve())]
    DEFAULT_REGISTRY.clear()


def _cli(root: Path, *args: str) -> Result:
    return runner.invoke(app, [*args, "--project", str(root)])


def test_every_claim_gets_an_assessment_and_sane_statuses(project: Path) -> None:
    assert _cli(project, "snapshot", "--write").exit_code == 0
    t0 = time.perf_counter()
    assert _cli(project, "run", "--all").exit_code in (0, 1, 2)
    assert time.perf_counter() - t0 < 300  # observed ~25 s
    assessments = Project.open(project).assess()
    assert len(assessments) == 171
    status = {c: a.status.value for c, a in assessments.items()}
    # Locality: the analytic shaft claim is supported by its own evidence alone.
    assert status["C-SHAFT"] == "supported"
    # Recorded cycles have bench measurements, so every recorded pm claim is decided.
    assert all(status[f"C-R{i:02d}-PM"] in ("supported", "violated") for i in range(1, 41))
    # Parametric pm claims (high) have only the simulator until the ML producers exist (P4-03).
    assert all(status[f"C-P{i:02d}-PM"] != "supported" for i in range(1, 41))
    assert _cli(project, "status").exit_code in (0, 1, 2)
