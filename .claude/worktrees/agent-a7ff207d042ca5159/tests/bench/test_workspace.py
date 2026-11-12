"""P5-02: throwaway workspaces and deterministic scenario commits."""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from bench.harness.workspace import GIT_ENV, Workspace

MINI = Path(__file__).resolve().parents[1] / "fixtures" / "mini_project"


def _init_repo(dst: Path) -> Path:
    shutil.copytree(MINI, dst, ignore=shutil.ignore_patterns("__pycache__", ".reval"))
    (dst / ".gitignore").write_text(".reval/\n__pycache__/\n", encoding="utf-8")
    env = {**os.environ, **GIT_ENV}
    for args in (["init", "-q"], ["add", "-A"], ["commit", "-q", "-m", "base"]):
        subprocess.run(["git", *args], cwd=dst, env=env, check=True, capture_output=True)
    return dst


@pytest.fixture
def base(tmp_path: Path) -> Path:
    return _init_repo(tmp_path / "base")


def _scale_change(ws: Workspace) -> str:
    p = ws.root / "params" / "params.yaml"
    p.write_text(p.read_text(encoding="utf-8").replace("scale: 1.0", "scale: 1.1"), encoding="utf-8")
    return ws.commit("scale 1.1")


def test_commit_shows_one_field_changed(base: Path, tmp_path: Path) -> None:
    ws = Workspace.create(base, tmp_path / "ws", scenario_id="s1")
    assert "scale: 1.0" in (ws.root / "params" / "params.yaml").read_text(encoding="utf-8")
    ws.commit("base lock")
    _scale_change(ws)
    proc = ws.run_reval(["diff", "HEAD~1", "HEAD", "--format", "json"])
    changes = json.loads(proc.stdout)["changes"]["changes"]
    assert [c["kind"] for c in changes].count("field_changed") == 1
    ws.cleanup()
    assert not ws.clone.exists()


def test_user_repo_untouched_and_commits_deterministic(base: Path, tmp_path: Path) -> None:
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=base, capture_output=True, text=True, check=True
    ).stdout
    a = Workspace.create(base, tmp_path / "w", scenario_id="a")
    b = Workspace.create(base, tmp_path / "w", scenario_id="b")
    a.commit("base lock")
    b.commit("base lock")
    la, lb = (w.root / "reval.lock.json" for w in (a, b))
    assert la.read_text(encoding="utf-8") == lb.read_text(encoding="utf-8")
    assert a.head() == b.head()
    assert _scale_change(a) == _scale_change(b)
    subprocess.run(["git", "status", "--porcelain"], cwd=base, check=True)
    assert (
        subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=base, capture_output=True, text=True, check=True
        ).stdout
        == head
    )
    assert "1.1" not in (base / "params" / "params.yaml").read_text(encoding="utf-8")


def test_untracked_dirs_linked_and_detach_protects_cache(base: Path, tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    (cache / "data").mkdir(parents=True)
    (cache / "data" / "big.bin").write_bytes(b"original")
    ws = Workspace.create(base, tmp_path / "ws", cache, scenario_id="s")
    target = ws.root / "data" / "big.bin"
    assert target.read_bytes() == b"original"
    ws.detach("data/big.bin")
    target.write_bytes(b"changed")
    assert (cache / "data" / "big.bin").read_bytes() == b"original"


def test_existing_workspace_refused(base: Path, tmp_path: Path) -> None:
    Workspace.create(base, tmp_path / "ws", scenario_id="s")
    with pytest.raises(FileExistsError):
        Workspace.create(base, tmp_path / "ws", scenario_id="s")
