"""P4-12: the canonical report JSON on the mini project matches its golden file; the hash ignores the clock.

Regenerate deliberately with ``REVAL_UPDATE_GOLDEN=1``; review the diff before committing.
"""

import os
from datetime import UTC, datetime
from pathlib import Path

from reval.core.canonical import content_id
from reval.report import DISCLAIMER, Report, build_report
from reval.services import Project

GOLDEN = Path(__file__).with_name("report_mini.json")


def mini_report(root: Path, when: datetime) -> Report:
    proj = Project.open(root, clock=lambda: when)
    proj.run_all()
    return build_report(proj)


def _json(report: Report) -> str:
    return report.model_dump_json(indent=2) + "\n"


def test_report_json_matches_golden(root: Path) -> None:
    text = _json(mini_report(root, datetime(2026, 1, 1, tzinfo=UTC)))
    if os.environ.get("REVAL_UPDATE_GOLDEN") == "1":
        GOLDEN.write_bytes(text.encode("utf-8"))
    assert text == GOLDEN.read_bytes().decode("utf-8").replace("\r\n", "\n")


def test_hash_ignores_clock_and_id_is_prefix(root: Path) -> None:
    a = mini_report(root, datetime(2026, 1, 1, tzinfo=UTC))
    b = mini_report(root, datetime(2031, 6, 7, 8, 9, tzinfo=UTC))
    assert a.created_at != b.created_at
    assert a.report_hash == b.report_hash
    assert a.report_id == a.report_hash[:16]
    body = a.model_dump(mode="json")
    assert content_id(body, exclude=frozenset({"report_hash", "report_id", "created_at"})) == a.report_hash


def test_disclaimer_is_mandatory_and_stored(root: Path) -> None:
    proj = Project.open(root, clock=lambda: datetime(2026, 1, 1, tzinfo=UTC))
    proj.run_all()
    report = build_report(proj)
    assert report.disclaimer == DISCLAIMER
    stored = proj.store.get_report(report.report_id)
    assert stored is not None
    assert Report.model_validate(stored) == report
