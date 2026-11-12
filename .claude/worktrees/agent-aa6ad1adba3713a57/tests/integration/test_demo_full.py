import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path("examples/motor_thermal")
PARQUET = ROOT / "data" / "processed" / "measures.parquet"


@pytest.mark.data
@pytest.mark.slow
@pytest.mark.skipif(not PARQUET.exists(), reason="processed motor data not available")
@pytest.mark.skipif(shutil.which("bash") is None, reason="bash not available")
def test_demo_full_runs_and_writes_report(tmp_path):
    keep = tmp_path / "keep"
    env = {**os.environ, "DEMO_KEEP": str(keep)}
    proc = subprocess.run(
        ["bash", str(ROOT / "demo_full.sh")],
        env=env,
        capture_output=True,
        text=True,
        timeout=900,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout[-2000:] + proc.stderr[-2000:]
    report = keep / "report.html"
    assert report.exists() and report.stat().st_size > 0
    assert "demo_full: OK" in proc.stdout
