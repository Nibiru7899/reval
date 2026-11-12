"""Application service: one engineering project on disk (manifest + producers + store). Docs/10 §10."""

import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from reval.core.diff import diff_snapshots
from reval.core.freshness import FreshnessResult, carry_forward, classify_all
from reval.core.planner import build_problem
from reval.core.planner import plan as make_plan
from reval.core.status import FRESH_CLASSES, AssessInput, assess_all
from reval.domain import Assessment, ChangeSet, Evidence, FreshnessClass, Snapshot
from reval.domain.engineering import Subject
from reval.domain.evidence import ProducerKind
from reval.domain.plan import PlannedRun, RevalidationPlan
from reval.domain.settings import DEFAULT_SETTINGS, ReValSettings
from reval.errors import ProducerError, RevalError
from reval.gitio import lockfile
from reval.manifest import ManifestModel, load_manifest
from reval.manifest.snapshot_builder import build_snapshot
from reval.sdk import DEFAULT_REGISTRY, ProducerRegistry
from reval.sdk.runner import run_producer
from reval.services.jobs import run_jobs
from reval.store import Job, SqlStore, open_store

MANIFEST_FILE = "reval.yaml"


def _purge_modules(names: list[str]) -> None:
    """Drop cached producer packages so a re-opened project re-registers its producers."""
    tops = {n.split(".")[0] for n in names}
    for mod in [m for m in sys.modules if m.split(".")[0] in tops]:
        del sys.modules[mod]


@dataclass(frozen=True)
class DiffReport:
    """Result of comparing two snapshots (docs/10 §10)."""

    changes: ChangeSet
    freshness: dict[str, FreshnessResult]
    before: dict[str, Assessment]
    after: dict[str, Assessment]
    affected_claims: tuple[str, ...]  # status changed, or any evidence for the claim not FRESH_EXACT


@dataclass(frozen=True)
class PlanOutcome:
    """Result of executing a plan: evidence appended, one job per run, statuses before and after."""

    plan_id: str
    evidence: tuple[Evidence, ...]
    jobs: tuple[Job, ...]
    before: dict[str, Assessment]
    after: dict[str, Assessment]


class Project:
    """Opens a project directory and orchestrates snapshot, run and assess. Adapters do the I/O."""

    def __init__(
        self,
        root: Path,
        manifest: ManifestModel,
        registry: ProducerRegistry,
        store: SqlStore,
        clock: Callable[[], datetime],
        settings: ReValSettings = DEFAULT_SETTINGS,
    ) -> None:
        self.root = root
        self.manifest = manifest
        self.registry = registry
        self.store = store
        self.clock = clock  # report timestamps only (D19); never reaches core
        self.settings = settings  # benchmark ablations; the defaults are the full method

    @classmethod
    def open(
        cls,
        root: Path,
        *,
        clock: Callable[[], datetime] | None = None,
        settings: ReValSettings = DEFAULT_SETTINGS,
    ) -> "Project":
        """Load the manifest, import the producer modules and open the store."""
        root = Path(root).resolve()
        manifest = load_manifest(root / MANIFEST_FILE)
        modules = list(manifest.producers)
        _purge_modules(modules)
        DEFAULT_REGISTRY.clear()
        try:
            DEFAULT_REGISTRY.load_modules(modules, root)
        except RevalError:
            raise
        except Exception as exc:
            raise ProducerError(
                f"cannot import producer modules {modules}: {type(exc).__name__}: {exc}"
            ) from exc
        return cls(
            root,
            manifest,
            DEFAULT_REGISTRY,
            open_store(root),
            clock or (lambda: datetime.now(UTC)),
            settings,
        )

    def snapshot(self, *, write_lock: bool = False) -> Snapshot:
        """Live snapshot of the working tree; stored, and optionally written to ``reval.lock.json``."""
        snap = build_snapshot(self.root, self.manifest, self.registry)
        self.store.put_snapshot(snap)
        if write_lock:
            lockfile.write_lock(self.root, snap)
        return snap

    def assess(self, snapshot: Snapshot | None = None) -> dict[str, Assessment]:
        """Assess every claim; the result is stored as a new assessment batch (append-only)."""
        snap = snapshot if snapshot is not None else self.snapshot()
        self.store.put_snapshot(snap)
        previous_id = self.store.latest_assessed_snapshot(before=snap.id)
        previous = self.store.get_snapshot(previous_id) if previous_id is not None else None
        # Only for the REQUIREMENT_CHANGED note; it never influences freshness.
        note = diff_snapshots(previous, snap) if previous is not None else None
        assessments, _ = self._assess_at(snap, note)
        self.store.put_assessments(snap.id, list(assessments.values()))
        return assessments

    def _assess_at(
        self, snap: Snapshot, note: ChangeSet | None = None
    ) -> tuple[dict[str, Assessment], dict[str, FreshnessResult]]:
        assessments, freshness, _ = self._assess_detail(snap, note)
        return assessments, freshness

    def _assess_detail(
        self, snap: Snapshot, note: ChangeSet | None = None
    ) -> tuple[dict[str, Assessment], dict[str, FreshnessResult], list[AssessInput]]:
        """Classify all stored evidence against ``snap`` and assess; stores nothing.

        A missing old snapshot leaves its evidence without a change set, which classify_all
        invalidates (fail closed). Carried items are materialised here and never stored (D5).
        """
        evidence = self.store.list_evidence()
        snapshots: dict[str, Snapshot] = {}
        changesets: dict[str, ChangeSet] = {}
        for sid in sorted({e.provenance.snapshot_id for e in evidence}):
            old = snap if sid == snap.id else self.store.get_snapshot(sid)
            if old is not None:
                snapshots[sid] = old
                changesets[sid] = diff_snapshots(old, snap)
        freshness = classify_all(evidence, snapshots, snap, changesets, settings=self.settings)
        items: list[AssessInput] = []
        for e in evidence:
            fr = freshness[e.id]
            if fr.cls is FreshnessClass.CARRY_FORWARD:
                items.append(
                    AssessInput(carry_forward(e, fr, snap), FreshnessClass.CARRY_FORWARD, original=e)
                )
            else:
                items.append(AssessInput(e, fr.cls))
        return assess_all(snap, items, note), freshness, items

    def diff(self, a: Snapshot, b: Snapshot) -> DiffReport:
        """Change set a -> b, evidence freshness at b, and claim statuses at a and at b (nothing stored)."""
        self.store.put_snapshot(a)
        self.store.put_snapshot(b)
        changes = diff_snapshots(a, b)
        before, _ = self._assess_at(a)
        after, freshness = self._assess_at(b, changes)
        evidence = self.store.list_evidence()
        affected: list[str] = []
        for cid in sorted(b.claims):
            claim = b.claims[cid]
            quantity = b.requirements[claim.requirement_id].quantity
            stale_evidence = any(
                e.subject_id == claim.subject_id
                and e.result.quantity == quantity
                and freshness[e.id].cls is not FreshnessClass.FRESH_EXACT
                for e in evidence
            )
            old_status = before[cid].status if cid in before else None
            if stale_evidence or old_status != after[cid].status:
                affected.append(cid)
        return DiffReport(changes, freshness, before, after, tuple(affected))

    def plan(
        self,
        snapshot: Snapshot | None = None,
        *,
        planner: str | None = None,
        objective: str = "min_cost",
        budget: float | None = None,
        decisiveness_aware: bool = True,
    ) -> RevalidationPlan:
        """Plan the cheapest runs that restore STALE/INCONCLUSIVE claims; the plan is stored (append-only).

        With ``decisiveness_aware`` (the default) the planner minimizes expected cost, using the most recent
        stored evidence of each (producer, subject, quantity) to estimate P(decisive) (P4-17); with False it
        assumes every run is decisive (the one-shot plan). ``planner=None`` uses ``settings.planner`` (A6).
        """
        planner = self.settings.planner if planner is None else planner
        snap = snapshot if snapshot is not None else self.snapshot()
        self.store.put_snapshot(snap)
        assessments, _, items = self._assess_detail(snap)

        def available(producer_id: str, subject_id: str) -> bool:
            rp = self.registry.get(producer_id)
            return rp.available_for is None or rp.available_for(snap.subjects[subject_id])

        # Latest fresh ML evidence outside its domain: a rerun would only reproduce that (docs/10 §4.6).
        position = {e.id: i for i, e in enumerate(self.store.list_evidence())}
        latest: dict[tuple[str, str], tuple[int, bool]] = {}
        for inp in items:
            e = inp.evidence
            if inp.freshness in FRESH_CLASSES and e.producer_kind is ProducerKind.ML_PREDICTION:
                key = (e.producer_id, e.subject_id)
                pos = position.get(e.id, -1)
                if key not in latest or pos >= latest[key][0]:
                    latest[key] = (pos, e.result.in_domain is False)
        out_of_domain = frozenset(k for k, (_, ood) in latest.items() if ood)

        # Most recent stored item per (producer, subject, quantity), whatever its freshness (P4-17).
        prior: dict[tuple[str, str, str], AssessInput] | None = None
        if decisiveness_aware:
            prior = {}
            ranked: dict[tuple[str, str, str], int] = {}
            for inp in items:
                e = inp.original if inp.original is not None else inp.evidence
                if e.producer_kind is ProducerKind.WAIVER:
                    continue
                key3 = (e.producer_id, e.subject_id, e.result.quantity)
                pos = position.get(e.id, -1)
                if key3 not in ranked or pos >= ranked[key3]:
                    ranked[key3] = pos
                    prior[key3] = inp

        problem = build_problem(
            snap,
            assessments,
            items,
            available=available,
            known_out_of_domain=out_of_domain,
            prior=prior,
        )
        try:
            result = make_plan(
                problem,
                planner=planner,  # type: ignore[arg-type]
                objective=objective,  # type: ignore[arg-type]
                budget=budget,
            )
        except ValueError as exc:
            raise RevalError(str(exc)) from exc
        self.store.put_plan(result)
        return result

    def execute_plan(self, plan: RevalidationPlan, *, only: str | None = None) -> PlanOutcome:
        """Run the plan's runs in order as jobs, append the evidence, then re-assess (a new batch, D18)."""
        snap = self.snapshot()
        if snap.id != plan.snapshot_id:
            raise RevalError(
                f"plan {plan.id[:12]} was made for snapshot {plan.snapshot_id[:12]}, "
                f"but the working tree is at {snap.id[:12]}; run `reval plan` again"
            )
        if only is not None and only not in snap.producers:
            raise RevalError(f"unknown producer {only!r}")
        before = self.assess(snap)
        runs = [r for r in plan.runs if only is None or r.producer_id == only]

        def execute(run: PlannedRun) -> tuple[Evidence, ...]:
            return self._run(snap, run.producer_id, self._subject(snap, run.subject_id))

        evidence, jobs = run_jobs(self.store, plan.id, runs, execute)
        after = self.assess(snap)
        return PlanOutcome(plan.id, evidence, jobs, before, after)

    def run_plan(self, plan: RevalidationPlan) -> tuple[Evidence, ...]:
        """Execute ``plan`` and re-assess; returns the evidence it appended."""
        return self.execute_plan(plan).evidence

    def run(self, producer_id: str, subject_id: str) -> tuple[Evidence, ...]:
        """Run one producer on one subject against the live snapshot and store the evidence."""
        snap = self.snapshot()
        return self._run(snap, producer_id, self._subject(snap, subject_id))

    def run_all(self) -> tuple[Evidence, ...]:
        """Run every producer on every claim subject it is available for (the B0 baseline).

        A producer is only run on a subject when it yields a quantity some claim on that subject needs;
        running it elsewhere would store evidence no claim can use.
        """
        snap = self.snapshot()
        needed: dict[str, set[str]] = {}
        for claim in snap.claims.values():
            needed.setdefault(claim.subject_id, set()).add(snap.requirements[claim.requirement_id].quantity)
        out: list[Evidence] = []
        for rp in self.registry.all():
            for sid in sorted(needed):
                subject = snap.subjects[sid]
                if not needed[sid] & set(rp.meta.quantities):
                    continue
                if rp.available_for is not None and not rp.available_for(subject):
                    continue
                out.extend(self._run(snap, rp.meta.id, subject))
        return tuple(out)

    def _subject(self, snap: Snapshot, subject_id: str) -> Subject:
        try:
            return snap.subjects[subject_id]
        except KeyError:
            raise ProducerError(f"unknown subject {subject_id!r}") from None

    def _run(self, snap: Snapshot, producer_id: str, subject: Subject) -> tuple[Evidence, ...]:
        if producer_id not in snap.producers:
            raise ProducerError(f"unknown producer {producer_id!r}")
        evidence = run_producer(self.registry, producer_id, subject, snap, self.root)
        for e in evidence:
            self.store.put_evidence(e)
        return evidence
