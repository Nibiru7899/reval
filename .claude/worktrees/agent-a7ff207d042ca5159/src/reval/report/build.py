"""Build the canonical Report from the current project state (services do the I/O; this assembles)."""

import json
from collections.abc import Mapping
from typing import Any

from reval import __version__
from reval.core.canonical import canonical_json
from reval.domain import Assessment, ChangeSet, Evidence, Snapshot, Status
from reval.domain.plan import RevalidationPlan
from reval.report.model import (
    DISCLAIMER,
    Report,
    ReportChange,
    ReportClaim,
    ReportEvidence,
    ReportPlan,
    ReportPlanRun,
    ReportReason,
    compute_report_hash,
)
from reval.services import Project


def _evidence_rows(
    a: Assessment, by_id: Mapping[str, Evidence], subject_id: str
) -> tuple[ReportEvidence, ...]:
    rows: list[ReportEvidence] = []
    for use in sorted(a.evidence, key=lambda u: u.evidence_id):
        # Carried-forward items are materialised, never stored; fall back to the original they derive from.
        ev = by_id.get(use.evidence_id) or by_id.get(use.derived_from_evidence or "")
        if ev is None:
            continue
        rows.append(
            ReportEvidence(
                id=use.evidence_id,
                producer=ev.producer_id,
                producer_kind=ev.producer_kind.value,
                subject_id=subject_id,
                verdict=use.verdict.value,
                recorded_verdict=use.recorded_verdict.value if use.recorded_verdict else None,
                freshness=use.freshness.value,
                point=ev.result.point,
                interval=use.interval_used if use.interval_used is not None else ev.result.interval,
                used_in_clause=use.used_in_clause,
                derived_from_evidence=use.derived_from_evidence,
                provenance={
                    "snapshot_id": ev.provenance.snapshot_id,
                    "producer_code_hash": ev.provenance.producer_code_hash,
                    "seed": ev.provenance.seed,
                    "uncertainty_kind": ev.result.uncertainty_kind,
                },
            )
        )
    return tuple(rows)


def report_from_parts(
    *,
    snap: Snapshot,
    assessments: Mapping[str, Assessment],
    evidence: Mapping[str, Evidence],
    project: str,
    created_at: str,
    plan: RevalidationPlan | None = None,
    changes: ChangeSet | None = None,
) -> Report:
    """Pure assembly: the same inputs with any ``created_at`` give the same ``report_hash``."""
    claims: list[ReportClaim] = []
    for cid in sorted(assessments):
        a = assessments[cid]
        claim = snap.claims[cid]
        req = snap.requirements[claim.requirement_id]
        claims.append(
            ReportClaim(
                id=cid,
                requirement_id=req.id,
                requirement=req.text,
                quantity=req.quantity,
                op=req.op.value,
                limit=req.limit,
                unit=req.unit,
                criticality=req.criticality.value,
                subject=claim.subject_id,
                status=a.status.value,
                satisfied_clause=a.satisfied_clause,
                reasons=tuple(
                    ReportReason(code=r.code.value, message=r.message, evidence_ids=r.evidence_ids)
                    for r in a.reasons
                ),
                evidence=_evidence_rows(a, evidence, claim.subject_id),
                input_hash=a.input_hash,
            )
        )
    summary = {s.value: 0 for s in Status}
    for c in claims:
        summary[c.status] += 1
    plan_model = (
        None
        if plan is None
        else ReportPlan(
            plan_id=plan.id,
            planner=plan.planner,
            objective=plan.objective,
            budget=plan.budget,
            solver_status=plan.solver_status,
            runs=tuple(
                ReportPlanRun(
                    producer_id=r.producer_id, subject_id=r.subject_id, cost=r.cost, discharges=r.discharges
                )
                for r in plan.runs
            ),
            total_cost=plan.total_cost,
            unrestorable=plan.unrestorable,
            deferred=plan.deferred,
        )
    )
    change_rows = (
        ()
        if changes is None
        else tuple(
            ReportChange(
                kind=c.kind.value,
                target=c.target,
                old=None if c.old is None else str(c.old),
                new=None if c.new is None else str(c.new),
                delta=c.delta,
                detail=c.detail,
            )
            for c in changes.changes
        )
    )
    body: dict[str, Any] = {
        "report_id": "",
        "created_at": created_at,
        "reval_version": __version__,
        "project": project,
        "snapshot_id": snap.id,
        "git_rev": snap.git_rev,
        "disclaimer": DISCLAIMER,
        "summary": summary,
        "claims": claims,
        "changes": change_rows,
        "plan": plan_model,
        "hashes": {c.id: c.input_hash for c in claims},
        "report_hash": "",
    }
    plain = json.loads(canonical_json(body))
    h = compute_report_hash(plain)
    return Report.model_validate({**plain, "report_hash": h, "report_id": h[:16]})


def build_report(
    project: Project, *, changes: ChangeSet | None = None, snapshot: Snapshot | None = None
) -> Report:
    """Assess the working tree (a new batch), attach the stored plan for it, and store the report."""
    snap = snapshot if snapshot is not None else project.snapshot()
    assessments = project.assess(snap)
    evidence = {e.id: e for e in project.store.list_evidence()}
    report = report_from_parts(
        snap=snap,
        assessments=assessments,
        evidence=evidence,
        project=project.manifest.project,
        created_at=project.clock().isoformat(),
        plan=project.store.latest_plan(snap.id),
        changes=changes,
    )
    # Same state at another time has the same id but a different created_at; the first stored body stays.
    if project.store.get_report(report.report_id) is None:
        project.store.put_report(report.report_id, snap.id, report.model_dump(mode="json"))
    return report
