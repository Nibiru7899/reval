"""I6 plan soundness (docs/03 §5): if every planned run returns decisive PASS evidence, every claim that is
neither unrestorable nor deferred ends decided (SUPPORTED, or WAIVED when it carries a waiver). The generated
cases include lost-fail claims, whose mandatory rerun obligations make the fresh same-producer PASS supersede
the invalidated FAIL (I4)."""

from collections.abc import Sequence

import pytest
from hypothesis import given
from hypothesis import strategies as st

from reval.core.planner import PLANNED_STATUSES, build_problem, plan
from reval.core.status import AssessInput, assess_all
from reval.domain import Evidence, FreshnessClass, Status
from reval.domain.plan import RevalidationPlan
from tests.property.strategies import (
    PRODUCERS,
    SUBJECTS,
    Case,
    cases,
    make_evidence,
    single_claim_snapshot,
)

FX = FreshnessClass.FRESH_EXACT
# docs/03 I6: "decided" = Supported, Violated or Waived. Only PASS evidence is added, so never Violated; a
# claim with a waiver ends Waived once its lost FAIL is superseded (the lost-fail rule outranks the waiver).
DECIDED = frozenset({Status.SUPPORTED, Status.WAIVED})
# A decisive PASS for each quantity of the catalogue: q <= 100 degC, q2 >= 10 A.
PASS_INTERVAL = {"q": (40.0, 50.0), "q2": (20.0, 30.0)}


def pass_evidence(producer_id: str, subject_id: str) -> list[Evidence]:
    """What an always-succeeding fake registry returns for one planned run."""
    prod = PRODUCERS[producer_id]
    return [
        make_evidence(
            producer_id,
            subject_id,
            q,
            lo,
            hi,
            in_domain=True,
            fidelity=prod.fidelity,
            seed=7,
        )
        for q, (lo, hi) in PASS_INTERVAL.items()
    ]


def plan_case(case: Case, planner: str = "ilp") -> tuple[RevalidationPlan, set[str]]:
    assessments = assess_all(case.snapshot, case.items)
    problem = build_problem(case.snapshot, assessments, case.items, available=lambda p, s: True)
    result = plan(problem, planner=planner)  # type: ignore[arg-type]
    planned = {c for c, a in assessments.items() if a.status in PLANNED_STATUSES}
    return result, planned


def run_all_planned(case: Case, result: RevalidationPlan) -> dict[str, Status]:
    items: dict[str, AssessInput] = {i.evidence.id: i for i in case.items}
    for run in result.runs:
        for e in pass_evidence(run.producer_id, run.subject_id):
            items.setdefault(e.id, AssessInput(e, FX))
    after = assess_all(case.snapshot, [items[k] for k in sorted(items)])
    return {c: a.status for c, a in after.items()}


def _assert_sound(case: Case, planner: str) -> None:
    result, planned = plan_case(case, planner)
    statuses = run_all_planned(case, result)
    restorable = planned - set(result.unrestorable) - set(result.deferred)
    for cid in sorted(restorable):
        assert statuses[cid] in DECIDED, (cid, statuses[cid], result.runs)


@given(cases())
def test_i6_ilp_plan_restores_every_restorable_claim(case: Case) -> None:
    _assert_sound(case, "ilp")


@given(cases())
def test_i6_greedy_and_all_plans_restore_what_they_cover(case: Case) -> None:
    _assert_sound(case, "greedy")
    _assert_sound(case, "all")


@given(st.sampled_from(SUBJECTS), st.sampled_from(["meas", "ana", "sim", "ml"]), st.sampled_from([FX]))
def test_i6_lost_fail_claim_is_restored_by_the_rerun(subject: str, pid: str, fresh: FreshnessClass) -> None:
    """Deterministic lost-fail case: an invalidated FAIL on the claim's subject must be superseded."""
    snap = single_claim_snapshot()  # C0 on S1, q <= 100
    fail = make_evidence(
        pid,
        "S1",
        "q",
        120.0,
        130.0,
        in_domain=True,
        fidelity=PRODUCERS[pid].fidelity,
        seed=1,
    )
    items: Sequence[AssessInput] = [AssessInput(fail, FreshnessClass.INVALIDATED)]
    case = Case(snapshot=snap, items=tuple(items))
    assessments = assess_all(snap, items)
    assert assessments["C0"].status is Status.STALE  # lost-fail
    result, planned = plan_case(case)
    if "C0" in result.unrestorable:
        pytest.skip("policy cannot be met by any candidate")  # e.g. the low policy needs a kind we lack
    assert "C0" in planned and "C0" not in result.deferred
    assert any(r.producer_id == pid for r in result.runs), "the failing producer must be rerun"
    assert run_all_planned(case, result)["C0"] is Status.SUPPORTED
