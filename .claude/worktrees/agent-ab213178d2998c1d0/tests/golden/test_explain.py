"""P4-14: `reval explain C-S1-TEMP` after a /load/scale change matches the golden tree.

Regenerate deliberately with ``REVAL_UPDATE_GOLDEN=1``; review the diff before committing.
"""

import os
from pathlib import Path

from tests.helpers.gitrepo import cli, make_repo

GOLDEN = Path(__file__).with_name("explain_c_s1_temp.txt")


def _explain(root: Path) -> str:
    make_repo(root, "1.05")
    r = cli(root, "explain", "C-S1-TEMP")
    assert r.exit_code == 0, r.output
    return r.stdout.replace("\r\n", "\n")


def test_explain_matches_golden(root: Path) -> None:
    text = _explain(root)
    if os.environ.get("REVAL_UPDATE_GOLDEN") == "1":
        GOLDEN.write_bytes(text.encode("utf-8"))
    assert text == GOLDEN.read_bytes().decode("utf-8").replace("\r\n", "\n")


def test_explain_is_ascii_and_names_dependencies(root: Path) -> None:
    text = _explain(root)
    assert text.isascii()
    assert "dependencies" in text and "params#/load/scale@" in text


def test_explain_unknown_claim_exits_3(root: Path) -> None:
    assert cli(root, "explain", "NOPE").exit_code == 3
