from typer.testing import CliRunner

from reval import __version__
from reval.cli.main import app
from reval.domain import ACCEPTED_STATUSES, ReasonCode, Status


def test_cli_version() -> None:
    result = CliRunner().invoke(app, ["version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_only_supported_and_waived_are_accepted() -> None:
    assert {Status.SUPPORTED, Status.WAIVED} == ACCEPTED_STATUSES
    assert Status.STALE not in ACCEPTED_STATUSES
    assert Status.INCONCLUSIVE not in ACCEPTED_STATUSES


def test_status_members_match_domain_model() -> None:
    # docs/03-domain-model.md §3; declaration order is not the evaluation order.
    assert {s.value for s in Status} == {"violated", "waived", "supported", "stale", "inconclusive"}


def test_reason_codes_match_domain_model_table() -> None:
    # docs/03-domain-model.md §6
    assert {c.value for c in ReasonCode} == {
        "policy_satisfied",
        "waiver_applied",
        "requirement_violated",
        "conflicting_evidence",
        "no_evidence",
        "out_of_domain",
        "margin_below_uncertainty",
        "policy_unmet",
        "evidence_invalidated",
        "unknown_change",
        "missing_tolerance",
        "requirement_changed",
    }
