import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path("examples/motor_thermal")
PARQUET = ROOT / "data" / "processed" / "measures.parquet"


@pytest.mark.data
@pytest.mark.slow
@pytest.mark.skipif(not PARQUET.exists(), reason="processed motor data not available")
def test_reproduce_m1_quick(tmp_path):
    spec = importlib.util.spec_from_file_location("reproduce_m1", ROOT / "scripts" / "reproduce_m1.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    out = mod.main(["--quick", "--models-dir", str(tmp_path)])
    rep = json.loads(out.read_text(encoding="utf-8"))
    assert rep["mode"] == "quick"
    needed = {"inputs", "model_test_metrics", "coverage_tables", "lptn", "drive_map_r2", "optimizer"}
    assert needed <= set(rep)
    assert set(rep["coverage_tables"]) == {"alpha_0.1", "alpha_0.05"}
    assert set(rep["optimizer"]["variants"]) == {"O1", "O2", "O3"}
    assert len(rep["inputs"]["parquet_sha256"]) == 64
