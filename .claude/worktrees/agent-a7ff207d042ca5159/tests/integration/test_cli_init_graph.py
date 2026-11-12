"""P4-16: `reval init` and `reval graph`."""

import json
from pathlib import Path

from reval.manifest.loader import load_manifest
from tests.helpers.gitrepo import cli, init_repo


def test_init_writes_loadable_manifest_and_refuses_overwrite(tmp_path: Path) -> None:
    r = cli(tmp_path, "init")
    assert r.exit_code == 0, r.output
    assert (tmp_path / ".reval").is_dir()
    m = load_manifest(tmp_path / "reval.yaml")
    assert m.project == "my-project"
    again = cli(tmp_path, "init")
    assert again.exit_code == 3


def test_graph_focus_on_shaft_excludes_load_scale(root: Path, tmp_path: Path) -> None:
    init_repo(root)
    assert cli(root, "run", "--all").exit_code in (0, 1, 2)
    full_path, focus_path = tmp_path / "full.json", tmp_path / "shaft.json"
    assert cli(root, "graph", "--out", str(full_path)).exit_code == 0
    assert cli(root, "graph", "--claim", "C-SHAFT", "--out", str(focus_path)).exit_code == 0
    full = {n["id"] for n in json.loads(full_path.read_text(encoding="utf-8"))["nodes"]}
    focus = {n["id"] for n in json.loads(focus_path.read_text(encoding="utf-8"))["nodes"]}
    assert "claim:C-SHAFT" in focus
    assert "field:params#/load/scale" in full
    assert "field:params#/load/scale" not in focus


def test_graph_unknown_claim_exits_3(root: Path, tmp_path: Path) -> None:
    r = cli(root, "graph", "--claim", "C-NOPE", "--out", str(tmp_path / "g.json"))
    assert r.exit_code == 3
