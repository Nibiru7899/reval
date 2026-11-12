"""P3-09: `reval diff --format markdown` on the mini project's /load/scale scenario matches the golden file.

Regenerate deliberately with ``REVAL_UPDATE_GOLDEN=1``; review the diff before committing.
"""

import os
from pathlib import Path

from tests.helpers.gitrepo import cli, make_repo

GOLDEN = Path(__file__).with_name("diff_markdown.md")


def _render(root: Path) -> str:
    make_repo(root, "1.05")
    r = cli(root, "diff", "HEAD~1", "HEAD", "--format", "markdown")
    assert r.exit_code == 2, r.output  # C-S2-TEMP stays violated
    return r.stdout.replace("\r\n", "\n")


def test_markdown_matches_golden(root: Path) -> None:
    text = _render(root)
    if os.environ.get("REVAL_UPDATE_GOLDEN") == "1":
        GOLDEN.write_bytes(text.encode("utf-8"))
    assert text == GOLDEN.read_bytes().decode("utf-8").replace("\r\n", "\n")


def test_markdown_carries_disclaimer_and_status_text(root: Path) -> None:
    text = _render(root)
    assert text.rstrip().endswith("It does not certify safety._")
    assert "claim needs revalidation" in text or "claims need revalidation" in text
    assert "SUPPORTED" in text  # status text accompanies the icon
