from typer.testing import CliRunner

from reval import __version__
from reval.cli.main import app
from reval.domain import ACCEPTED_STATUSES, Status


def test_cli_version() -> None:
    result = CliRunner().invoke(app, ["version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_only_supported_and_waived_are_accepted() -> None:
    assert {Status.SUPPORTED, Status.WAIVED} == ACCEPTED_STATUSES
    assert Status.STALE not in ACCEPTED_STATUSES
    assert Status.INCONCLUSIVE not in ACCEPTED_STATUSES


def test_status_evaluation_order_matches_domain_model() -> None:
    # docs/03-domain-model.md §3: violated → waived → supported → stale → inconclusive
    assert list(Status) == [
        Status.VIOLATED,
        Status.WAIVED,
        Status.SUPPORTED,
        Status.STALE,
        Status.INCONCLUSIVE,
    ]
