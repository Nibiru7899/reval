"""P4-13: Markdown golden, self-contained and honest HTML, and `reval report`.

Regenerate deliberately with ``REVAL_UPDATE_GOLDEN=1``; review the diff before committing.
"""

import os
import re
from datetime import UTC, datetime
from pathlib import Path

from reval.report import DISCLAIMER
from reval.report.model import Report
from reval.report.render import render_html, render_markdown
from tests.golden.test_report_json import mini_report
from tests.helpers.gitrepo import cli, make_repo

GOLDEN = Path(__file__).with_name("report_mini.md")
CLOCK = datetime(2026, 1, 1, tzinfo=UTC)
SRC = Path(__file__).resolve().parents[2] / "src" / "reval" / "report"


def test_markdown_matches_golden(root: Path) -> None:
    text = render_markdown(mini_report(root, CLOCK))
    if os.environ.get("REVAL_UPDATE_GOLDEN") == "1":
        GOLDEN.write_bytes(text.encode("utf-8"))
    assert text == GOLDEN.read_bytes().decode("utf-8").replace("\r\n", "\n")


def test_markdown_disclaimer_first_paragraph(root: Path) -> None:
    text = render_markdown(mini_report(root, CLOCK))
    assert text.split("\n\n")[1] == f"_{DISCLAIMER}_"


def _html(root: Path) -> tuple[Report, str]:
    rep = mini_report(root, CLOCK)
    return rep, render_html(rep)


def test_html_has_disclaimer_claims_and_text_status(root: Path) -> None:
    rep, html = _html(root)
    assert DISCLAIMER in html
    for c in rep.claims:
        assert c.id in html
    assert html.index(DISCLAIMER) < html.index("<h2>Claims</h2>")  # disclaimer at the top
    for label in ("Supported", "Violated"):
        assert re.search(rf"</svg>{label}", html)  # icon immediately followed by the word


def test_html_is_self_contained(root: Path) -> None:
    _, html = _html(root)
    assert "http" not in html
    assert "<script" not in html and "<link" not in html and "@import" not in html
    assert "prefers-color-scheme: dark" in html and "@media print" in html


def test_html_escapes_content(root: Path) -> None:
    rep, _ = _html(root)
    evil = rep.model_copy(update={"project": "<img src=x onerror=alert(1)>"})
    assert "<img src=x" not in render_html(evil)


def test_render_sources_avoid_forbidden_wording() -> None:
    # The disclaimer lives in model.py and is the only place these words may appear.
    for name in ("render.py", "styles.py", "explain.py"):
        text = (SRC / name).read_text(encoding="utf-8").lower()
        for word in ("safe", "certified", "guarantee"):
            assert word not in text, f"{word!r} in {name}"


def test_cli_report_writes_files(root: Path) -> None:
    make_repo(root, "1.05")
    out = root / "r.html"
    r = cli(root, "report", "--html", "--out", str(out), "--since", "HEAD~1")
    assert r.exit_code == 0, r.output
    html = out.read_text(encoding="utf-8")
    assert DISCLAIMER in html and "<h2>Changes</h2>" in html
    md = cli(root, "report")
    assert md.exit_code == 0 and DISCLAIMER in md.stdout
