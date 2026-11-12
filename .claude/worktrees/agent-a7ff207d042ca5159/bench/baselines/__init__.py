"""Baselines B1-B4 (docs/06 section 4); B0 is the evidence oracle in ``bench.oracles.evidence``."""

from bench.baselines.base import (
    Baseline,
    BaselineResult,
    PostState,
    PreState,
    execute_baseline,
    file_hashes,
)
from bench.baselines.file_level import FileLevel
from bench.baselines.naive import NaiveTrust
from bench.baselines.ood_only import OodOnly, domain_check_via_producer
from bench.baselines.random_budget import RandomBudget

__all__ = [
    "Baseline",
    "BaselineResult",
    "FileLevel",
    "NaiveTrust",
    "OodOnly",
    "PostState",
    "PreState",
    "RandomBudget",
    "domain_check_via_producer",
    "execute_baseline",
    "file_hashes",
]
