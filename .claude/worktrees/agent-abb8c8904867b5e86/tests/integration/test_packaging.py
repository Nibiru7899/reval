"""P7-04: build the wheel, install it into a fresh venv and run the installed `reval`.

Slow (it builds and pip-installs all dependencies) and needs network access to a package index; it is skipped,
not failed, when the index is unreachable.
"""

import subprocess
import sys
import venv
from pathlib import Path

import pytest

import reval

ROOT = Path(__file__).resolve().parents[2]
_OFFLINE_MARKERS = (
    "Could not find a version",
    "No matching distribution",
    "Connection",
    "Temporary failure in name resolution",
    "getaddrinfo failed",
    "Max retries exceeded",
)


def _run(cmd: list[str | Path], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run([str(c) for c in cmd], cwd=cwd, capture_output=True, text=True, check=False)


def _skip_if_offline(proc: subprocess.CompletedProcess[str], what: str) -> None:
    text = proc.stdout + proc.stderr
    if proc.returncode != 0 and any(m in text for m in _OFFLINE_MARKERS):
        pytest.skip(f"{what} needs a package index (offline?): {text[-300:]}")


@pytest.mark.slow
def test_wheel_installs_in_fresh_venv_and_runs(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    built = _run([sys.executable, "-m", "build", "--wheel", "--outdir", dist, ROOT], cwd=tmp_path)
    _skip_if_offline(built, "building the wheel")
    assert built.returncode == 0, built.stdout + built.stderr
    wheels = list(dist.glob("reval-*.whl"))
    assert len(wheels) == 1, wheels

    env_dir = tmp_path / "venv"
    venv.EnvBuilder(with_pip=True, clear=True).create(env_dir)
    bindir = env_dir / ("Scripts" if sys.platform == "win32" else "bin")
    py = bindir / ("python.exe" if sys.platform == "win32" else "python")
    installed = _run([py, "-m", "pip", "install", "--quiet", wheels[0]], cwd=tmp_path)
    _skip_if_offline(installed, "installing the wheel")
    assert installed.returncode == 0, installed.stdout + installed.stderr

    exe = bindir / ("reval.exe" if sys.platform == "win32" else "reval")
    helped = _run([exe, "--help"], cwd=tmp_path)
    assert helped.returncode == 0, helped.stderr
    assert "Usage" in helped.stdout and "snapshot" in helped.stdout

    version = _run([exe, "version"], cwd=tmp_path)
    assert version.returncode == 0, version.stderr
    assert version.stdout.strip() == f"reval {reval.__version__}"

    # Package data is really in the wheel: `init` renders a bundled template.
    project = tmp_path / "proj"
    project.mkdir()
    init = _run([exe, "init"], cwd=project)
    assert init.returncode == 0, init.stdout + init.stderr
    assert (project / "reval.yaml").exists()
