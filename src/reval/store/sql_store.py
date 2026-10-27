"""SQLAlchemy-backed store (docs/10 §8, ADR 0003). Evidence and assessments are append-only."""

import json
import os
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Protocol

from sqlalchemy import Connection, Engine, create_engine, func, insert, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.pool import StaticPool

from reval.core.canonical import canonical_json
from reval.domain import Assessment, Evidence, RevalidationPlan, Snapshot
from reval.errors import StoreError
from reval.store import tables as t
from reval.store.jobs import Job, JobState


class Store(Protocol):
    def put_snapshot(self, s: Snapshot) -> None: ...
    def get_snapshot(self, snapshot_id: str) -> Snapshot | None: ...
    def list_snapshots(self) -> tuple[Snapshot, ...]: ...
    def put_evidence(self, e: Evidence) -> None: ...
    def list_evidence(self, *, subject_id: str | None = None) -> tuple[Evidence, ...]: ...
    def put_assessments(self, snapshot_id: str, items: Sequence[Assessment]) -> int: ...
    def get_assessments(self, snapshot_id: str, *, seq: int | None = None) -> dict[str, Assessment]: ...
    def latest_assessed_snapshot(self, *, before: str | None = None) -> str | None: ...
    def put_plan(self, p: RevalidationPlan) -> None: ...
    def get_plan(self, plan_id: str) -> RevalidationPlan | None: ...
    def latest_plan(self, snapshot_id: str) -> RevalidationPlan | None: ...
    def put_job(self, job: Job) -> None: ...
    def update_job_state(
        self, job_id: str, state: JobState, *, result: dict[str, Any] | None = None
    ) -> None: ...
    def get_job(self, job_id: str) -> Job | None: ...
    def put_report(self, report_id: str, snapshot_id: str, body: dict[str, Any]) -> None: ...
    def get_report(self, report_id: str) -> dict[str, Any] | None: ...


def _body(obj: object) -> str:
    return canonical_json(obj).decode("utf-8")


class SqlStore:
    """SQLite (default) or PostgreSQL store. ``created_seq`` is a store counter, never a clock."""

    def __init__(self, url: str) -> None:
        kwargs: dict[str, Any] = {}
        if url in ("sqlite://", "sqlite:///:memory:"):
            # One shared connection, otherwise every connection would see its own empty database.
            kwargs = {"poolclass": StaticPool, "connect_args": {"check_same_thread": False}}
        elif url.startswith("sqlite"):
            kwargs = {"connect_args": {"check_same_thread": False}}
        try:
            self._engine: Engine = create_engine(url, **kwargs)
            t.metadata.create_all(self._engine)
        except SQLAlchemyError as exc:
            raise StoreError(f"cannot open store at {url!r}: {exc}") from exc

    # -- helpers -----------------------------------------------------------------------------

    @staticmethod
    def _next_seq(conn: Connection) -> int:
        """Increment and return the global counter. The UPDATE takes the write lock first."""
        res = conn.execute(
            update(t.counters).where(t.counters.c.name == "seq").values(value=t.counters.c.value + 1)
        )
        if res.rowcount == 0:
            conn.execute(insert(t.counters).values(name="seq", value=1))
            return 1
        return int(conn.execute(select(t.counters.c.value).where(t.counters.c.name == "seq")).scalar_one())

    def _put_once(self, table: Any, id_value: str, body: str, extra: dict[str, Any], *, what: str) -> None:
        """Insert-or-verify: same id and body is a no-op, same id with a different body is an error."""
        with self._engine.begin() as conn:
            existing = conn.execute(select(table.c.body).where(table.c.id == id_value)).scalar_one_or_none()
            if existing is not None:
                if existing != body:
                    raise StoreError(f"{what} {id_value!r} already stored with a different body")
                return
            values = {"id": id_value, "body": body, **extra}
            if "created_seq" in table.c:
                values["created_seq"] = self._next_seq(conn)
            conn.execute(insert(table).values(**values))

    # -- snapshots ---------------------------------------------------------------------------

    def put_snapshot(self, s: Snapshot) -> None:
        # The snapshot id ignores git_rev, so the same content seen at another revision is the same snapshot;
        # the first stored git_rev wins and the body comparison ignores it.
        with self._engine.begin() as conn:
            row = conn.execute(
                select(t.snapshots.c.body).where(t.snapshots.c.id == s.id)
            ).scalar_one_or_none()
            if row is not None:
                stored = Snapshot.model_validate_json(row)
                if _body(stored.model_copy(update={"git_rev": None})) != _body(
                    s.model_copy(update={"git_rev": None})
                ):
                    raise StoreError(f"snapshot {s.id!r} already stored with a different body")
                return
            conn.execute(
                insert(t.snapshots).values(
                    id=s.id, git_rev=s.git_rev, created_seq=self._next_seq(conn), body=_body(s)
                )
            )

    def get_snapshot(self, snapshot_id: str) -> Snapshot | None:
        with self._engine.connect() as conn:
            row = conn.execute(
                select(t.snapshots.c.body).where(t.snapshots.c.id == snapshot_id)
            ).scalar_one_or_none()
        return None if row is None else Snapshot.model_validate_json(row)

    def list_snapshots(self) -> tuple[Snapshot, ...]:
        with self._engine.connect() as conn:
            rows = (
                conn.execute(select(t.snapshots.c.body).order_by(t.snapshots.c.created_seq)).scalars().all()
            )
        return tuple(Snapshot.model_validate_json(r) for r in rows)

    # -- evidence ----------------------------------------------------------------------------

    def put_evidence(self, e: Evidence) -> None:
        self._put_once(
            t.evidence,
            e.id,
            _body(e),
            {
                "subject_id": e.subject_id,
                "producer_id": e.producer_id,
                "snapshot_id": e.provenance.snapshot_id,
            },
            what="evidence",
        )

    def list_evidence(self, *, subject_id: str | None = None) -> tuple[Evidence, ...]:
        q = select(t.evidence.c.body).order_by(t.evidence.c.created_seq)
        if subject_id is not None:
            q = q.where(t.evidence.c.subject_id == subject_id)
        with self._engine.connect() as conn:
            rows = conn.execute(q).scalars().all()
        return tuple(Evidence.model_validate_json(r) for r in rows)

    # -- assessments -------------------------------------------------------------------------

    def put_assessments(self, snapshot_id: str, items: Sequence[Assessment]) -> int:
        claim_ids = [a.claim_id for a in items]
        if len(set(claim_ids)) != len(claim_ids):
            raise StoreError("duplicate claim_id in assessment batch")
        for a in items:
            if a.snapshot_id != snapshot_id:
                raise StoreError(
                    f"assessment for {a.claim_id!r} belongs to snapshot {a.snapshot_id!r}, "
                    f"not {snapshot_id!r}"
                )
        with self._engine.begin() as conn:
            current = conn.execute(
                select(func.max(t.assessments.c.seq)).where(t.assessments.c.snapshot_id == snapshot_id)
            ).scalar_one()
            seq = (current or 0) + 1
            created = self._next_seq(conn)
            for a in items:
                conn.execute(
                    insert(t.assessments).values(
                        snapshot_id=snapshot_id,
                        claim_id=a.claim_id,
                        seq=seq,
                        created_seq=created,
                        status=a.status.value,
                        input_hash=a.input_hash,
                        body=_body(a),
                    )
                )
        return int(seq)

    def get_assessments(self, snapshot_id: str, *, seq: int | None = None) -> dict[str, Assessment]:
        with self._engine.connect() as conn:
            if seq is None:
                seq = conn.execute(
                    select(func.max(t.assessments.c.seq)).where(t.assessments.c.snapshot_id == snapshot_id)
                ).scalar_one()
                if seq is None:
                    return {}
            rows = conn.execute(
                select(t.assessments.c.claim_id, t.assessments.c.body)
                .where(t.assessments.c.snapshot_id == snapshot_id, t.assessments.c.seq == seq)
                .order_by(t.assessments.c.claim_id)
            ).all()
        return {cid: Assessment.model_validate_json(body) for cid, body in rows}

    def latest_assessed_snapshot(self, *, before: str | None = None) -> str | None:
        """Snapshot of the most recent assessment batch (by batch order, not snapshot creation order).

        With ``before``, the batches considered are those older than the latest batch of that snapshot,
        skipping the snapshot itself; if ``before`` was never assessed, it is simply ignored.
        """
        a = t.assessments
        with self._engine.connect() as conn:
            q = select(a.c.snapshot_id, func.max(a.c.created_seq).label("cs")).group_by(a.c.snapshot_id)
            per_snapshot = {sid: int(cs) for sid, cs in conn.execute(q).all()}
        if before is not None and before in per_snapshot:
            limit = per_snapshot[before]
            per_snapshot = {sid: cs for sid, cs in per_snapshot.items() if sid != before and cs < limit}
        elif before is not None:
            per_snapshot = {sid: cs for sid, cs in per_snapshot.items() if sid != before}
        if not per_snapshot:
            return None
        best: str = max(per_snapshot, key=lambda sid: per_snapshot[sid])
        return best

    # -- plans -------------------------------------------------------------------------------

    def put_plan(self, p: RevalidationPlan) -> None:
        self._put_once(t.plans, p.id, _body(p), {"snapshot_id": p.snapshot_id}, what="plan")

    def get_plan(self, plan_id: str) -> RevalidationPlan | None:
        with self._engine.connect() as conn:
            row = conn.execute(select(t.plans.c.body).where(t.plans.c.id == plan_id)).scalar_one_or_none()
        return None if row is None else RevalidationPlan.model_validate_json(row)

    def latest_plan(self, snapshot_id: str) -> RevalidationPlan | None:
        with self._engine.connect() as conn:
            row = conn.execute(
                select(t.plans.c.body)
                .where(t.plans.c.snapshot_id == snapshot_id)
                .order_by(t.plans.c.created_seq.desc())
                .limit(1)
            ).scalar_one_or_none()
        return None if row is None else RevalidationPlan.model_validate_json(row)

    # -- jobs --------------------------------------------------------------------------------

    @staticmethod
    def _job_from_row(row: Any) -> Job:
        return Job(
            id=row.id,
            kind=row.kind,
            state=JobState(row.state),
            payload=json.loads(row.payload),
            result=None if row.result is None else json.loads(row.result),
        )

    def put_job(self, job: Job) -> None:
        with self._engine.begin() as conn:
            if conn.execute(select(t.jobs.c.id).where(t.jobs.c.id == job.id)).first() is not None:
                raise StoreError(f"job {job.id!r} already exists")
            conn.execute(
                insert(t.jobs).values(
                    id=job.id,
                    kind=job.kind,
                    state=job.state.value,
                    payload=_body(job.payload),
                    result=None if job.result is None else _body(job.result),
                    created_seq=self._next_seq(conn),
                )
            )

    def update_job_state(self, job_id: str, state: JobState, *, result: dict[str, Any] | None = None) -> None:
        """The only in-place update in the store (AGENTS rule 5 exception, docs/10 §8)."""
        values: dict[str, Any] = {"state": state.value}
        if result is not None:
            values["result"] = _body(result)
        with self._engine.begin() as conn:
            res = conn.execute(update(t.jobs).where(t.jobs.c.id == job_id).values(**values))
            if res.rowcount == 0:
                raise StoreError(f"unknown job {job_id!r}")

    def get_job(self, job_id: str) -> Job | None:
        with self._engine.connect() as conn:
            row = conn.execute(select(t.jobs).where(t.jobs.c.id == job_id)).first()
        return None if row is None else self._job_from_row(row)

    # -- reports -----------------------------------------------------------------------------

    def put_report(self, report_id: str, snapshot_id: str, body: dict[str, Any]) -> None:
        text = _body(body)
        with self._engine.begin() as conn:
            row = conn.execute(select(t.reports).where(t.reports.c.id == report_id)).first()
            if row is not None:
                if row.body != text or row.snapshot_id != snapshot_id:
                    raise StoreError(f"report {report_id!r} already stored with a different body")
                return
            conn.execute(insert(t.reports).values(id=report_id, snapshot_id=snapshot_id, body=text))

    def get_report(self, report_id: str) -> dict[str, Any] | None:
        with self._engine.connect() as conn:
            row = conn.execute(
                select(t.reports.c.body).where(t.reports.c.id == report_id)
            ).scalar_one_or_none()
        if row is None:
            return None
        loaded: dict[str, Any] = json.loads(row)
        return loaded

    def close(self) -> None:
        self._engine.dispose()


def open_store(project_root: Path) -> SqlStore:
    """Open the project's store: ``REVAL_DATABASE_URL`` or ``<root>/.reval/reval.db`` (SQLite)."""
    url = os.environ.get("REVAL_DATABASE_URL")
    if not url:
        d = project_root / ".reval"
        d.mkdir(parents=True, exist_ok=True)
        url = f"sqlite:///{(d / 'reval.db').as_posix()}"
    return SqlStore(url)
