"""Application service: one engineering project on disk (manifest + producers + store). Docs/10 §10."""

import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from reval.core.selectors import selector_hash
from reval.core.status import AssessInput, assess_all
from reval.domain import Assessment, Evidence, FreshnessClass, Snapshot
from reval.domain.engineering import Subject
from reval.errors import ProducerError, RevalError
from reval.gitio import lockfile
from reval.manifest import ManifestModel, load_manifest
from reval.manifest.snapshot_builder import build_snapshot
from reval.sdk import DEFAULT_REGISTRY, ProducerRegistry
from reval.sdk.runner import run_producer
from reval.store import SqlStore, open_store

MANIFEST_FILE = "reval.yaml"


def _purge_modules(names: list[str]) -> None:
    """Drop cached producer packages so a re-opened project re-registers its producers."""
    tops = {n.split(".")[0] for n in names}
    for mod in [m for m in sys.modules if m.split(".")[0] in tops]:
        del sys.modules[mod]


def placeholder_freshness(e: Evidence, current: Snapshot) -> FreshnessClass:
    """Phase 2 placeholder (replaced by core/freshness.py in P3-06).

    FRESH_EXACT iff every dependency hash and the producer code hash match the current snapshot;
    anything else, including an unparseable selector or a vanished producer, is INVALIDATED (fail closed).
    """
    producer = current.producers.get(e.producer_id)
    if producer is None or producer.code_hash != e.provenance.producer_code_hash:
        return FreshnessClass.INVALIDATED
    for dep in e.deps:
        try:
            now = selector_hash(current, dep.selector)
        except RevalError:
            return FreshnessClass.INVALIDATED
        if now != dep.version_hash:
            return FreshnessClass.INVALIDATED
    return FreshnessClass.FRESH_EXACT


class Project:
    """Opens a project directory and orchestrates snapshot, run and assess. Adapters do the I/O."""

    def __init__(
        self,
        root: Path,
        manifest: ManifestModel,
        registry: ProducerRegistry,
        store: SqlStore,
        clock: Callable[[], datetime],
    ) -> None:
        self.root = root
        self.manifest = manifest
        self.registry = registry
        self.store = store
        self.clock = clock  # report timestamps only (D19); never reaches core

    @classmethod
    def open(cls, root: Path, *, clock: Callable[[], datetime] | None = None) -> "Project":
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
        return cls(root, manifest, DEFAULT_REGISTRY, open_store(root), clock or (lambda: datetime.now(UTC)))

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
        items = [AssessInput(e, placeholder_freshness(e, snap)) for e in self.store.list_evidence()]
        assessments = assess_all(snap, items)
        self.store.put_assessments(snap.id, list(assessments.values()))
        return assessments

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
