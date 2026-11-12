"""Shared types and the common runner for the baselines B1-B4 (docs/06 section 4).

``select_runs(pre, post)`` returns ``(producer_id, subject_id)`` pairs; :func:`execute_baseline` runs them
through the same producer-result cache as B0 and ReVal and assesses the outcome. A baseline never sees
ReVal's change set or freshness classes: old evidence that it did not rerun is trusted as fresh.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from bench.harness.cache import ProducerResultCache
from reval.core.status import AssessInput, assess_all
from reval.domain.assessment import Assessment
from reval.domain.evidence import Evidence, ProducerKind
from reval.domain.settings import DEFAULT_SETTINGS, ReValSettings
from reval.domain.snapshot import Snapshot
from reval.domain.status import FreshnessClass
from reval.services.project import Project

Run = tuple[str, str]
MISSING = "missing"


def file_hashes(root: Path, snapshot: Snapshot) -> dict[str, str]:
    """Whole-file sha256 of every artifact path (an independent, deliberately naive implementation)."""
    out: dict[str, str] = {}
    for art in snapshot.artifacts.values():
        p = root / art.path
        out[art.path] = hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else MISSING
    return out


@dataclass(frozen=True)
class PreState:
    """What a baseline knows about the pre-change state S."""

    snapshot: Snapshot
    evidence: tuple[Evidence, ...]
    files: Mapping[str, str]

    @classmethod
    def capture(cls, root: Path, snapshot: Snapshot, evidence: Sequence[Evidence]) -> PreState:
        """Hash the artifact files NOW (before the change is applied) and keep S's evidence."""
        return cls(snapshot, tuple(evidence), file_hashes(root, snapshot))

    def latest(self) -> dict[Run, Evidence]:
        """Last-recorded evidence per (producer, subject); waivers are ignored (benchmarks have none)."""
        out: dict[Run, Evidence] = {}
        for e in self.evidence:
            if e.producer_kind is not ProducerKind.WAIVER:
                out[(e.producer_id, e.subject_id)] = e
        return out


@dataclass(frozen=True)
class PostState:
    """The post-change workspace: an opened project and its live snapshot S'."""

    project: Project
    snapshot: Snapshot

    @property
    def root(self) -> Path:
        return self.project.root


class Baseline(Protocol):
    id: str

    def select_runs(self, pre: PreState, post: PostState) -> list[Run]: ...


@dataclass(frozen=True)
class BaselineResult:
    baseline_id: str
    runs: tuple[Run, ...]
    cost: float
    evidence: tuple[Evidence, ...]  # evidence the method ends with (kept old + new)
    assessments: Mapping[str, Assessment]


def run_cost(snapshot: Snapshot, runs: Sequence[Run]) -> float:
    return float(sum(snapshot.producers[pid].cost for pid, _ in runs))


def execute_baseline(
    baseline: Baseline,
    pre: PreState,
    post: PostState,
    cache: ProducerResultCache,
    settings: ReValSettings = DEFAULT_SETTINGS,
) -> BaselineResult:
    """Run the selected producers (cached), then assess old-kept + new evidence as fresh at S'."""
    runs = sorted(set(baseline.select_runs(pre, post)))
    new: list[Evidence] = []
    for pid, sid in runs:
        got, _ = cache.run(post.project, post.snapshot, pid, sid, settings)
        new.extend(got)
    rerun = set(runs)
    kept = [e for e in pre.evidence if (e.producer_id, e.subject_id) not in rerun]
    final = tuple(kept) + tuple(new)
    # Baselines have no notion of staleness: whatever they hold is treated as fresh.
    items = [AssessInput(e, FreshnessClass.FRESH_EXACT) for e in final]
    assessments = assess_all(post.snapshot, items)
    return BaselineResult(baseline.id, tuple(runs), run_cost(post.snapshot, runs), final, assessments)
