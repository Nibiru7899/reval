"""P6-13: the GitHub Action and its demo workflow are well-formed and wired as documented in docs/09."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
ACTION = ROOT / ".github" / "actions" / "reval-diff" / "action.yml"
WORKFLOW = ROOT / ".github" / "workflows" / "reval-demo.yml"


def _load(path: Path) -> dict:  # type: ignore[type-arg]
    return yaml.safe_load(path.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def test_workflow_triggers_checkout_and_permissions() -> None:
    wf = _load(WORKFLOW)
    assert "pull_request" in wf[True if True in wf else "on"]  # PyYAML parses a bare `on` as True
    assert wf["permissions"] == {"contents": "read", "pull-requests": "write"}
    steps = wf["jobs"]["reval-diff"]["steps"]
    checkout = next(s for s in steps if s.get("uses", "").startswith("actions/checkout"))
    assert checkout["with"]["fetch-depth"] == 0
    assert any(s.get("uses") == "./.github/actions/reval-diff" for s in steps)


def test_action_runs_diff_in_markdown_and_posts_one_comment() -> None:
    action = _load(ACTION)
    assert action["runs"]["using"] == "composite"
    text = ACTION.read_text(encoding="utf-8")
    assert 'reval diff "origin/${BASE_REF}" HEAD --format markdown' in text
    assert "actions/github-script" in text and "<!-- reval-diff -->" in text
    assert "updateComment" in text and "createComment" in text
    assert action["inputs"]["fail-on"]["default"] == "stale"  # fail closed by default


def test_action_does_not_interpolate_inputs_into_shell_or_print_secrets() -> None:
    for step in _load(ACTION)["runs"]["steps"]:
        run = step.get("run", "")
        assert "${{" not in run, f"interpolation inside a run script: {step.get('name')}"
    assert "secrets." not in ACTION.read_text(encoding="utf-8")
