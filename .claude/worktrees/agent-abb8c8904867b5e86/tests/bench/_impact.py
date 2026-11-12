"""Helpers: apply a scenario to the mini project and see what ReVal flags as affected."""

from pathlib import Path

from bench.scenarios.generate import generate
from bench.scenarios.model import APPLIERS, AppliedChange, GenerateConfig, Scenario
from reval.services.project import DiffReport, Project
from tests.bench._mini import copy_mini

MINI_CFG = dict(t5_requirements=("R-TEMP",), t6_assumptions=("A-ambient",), n_base_snapshots=30)


def scenarios(change_type: str, tier: str = "A", n: int = 6, **cfg: object) -> list[Scenario]:
    config = GenerateConfig(
        instances_per_type=n, change_types=(change_type,), tiers=(tier,), **{**MINI_CFG, **cfg}
    )
    return generate(config, 0)


def impact(tmp_path: Path, sc: Scenario) -> tuple[AppliedChange, DiffReport]:
    """Run all producers on the mini project, apply ``sc``, and diff the two snapshots."""
    root = copy_mini(tmp_path)
    proj = Project.open(root)
    proj.run_all()
    before = proj.snapshot()
    change = APPLIERS[sc.apply](root, sc)
    after_proj = Project.open(root)
    return change, after_proj.diff(before, after_proj.snapshot())
