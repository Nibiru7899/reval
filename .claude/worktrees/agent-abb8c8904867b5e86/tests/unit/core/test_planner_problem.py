"""P4-05: build_problem — obligations, reuse and new-run candidates, independence, lost-fail reruns."""

from typing import Any

import pytest

from reval.core.diff import diff_snapshots
from reval.core.freshness import carry_forward, classify_all
from reval.core.planner import CRITICALITY_WEIGHT, build_problem, plan
from reval.core.status import AssessInput, assess_all
from reval.domain import (
    DEFAULT_POLICIES,
    Claim,
    Comparator,
    Criticality,
    Evidence,
    EvidenceResult,
    FreshnessClass,
    Interval,
    PlanningProblem,
    Producer,
    ProducerKind,
    Provenance,
    Requirement,
    Snapshot,
    Status,
)
from tests.helpers.mini_fresh import edit, pid, run_all

K = ProducerKind
FX = FreshnessClass.FRESH_EXACT
CF = FreshnessClass.CARRY_FORWARD
INV = FreshnessClass.INVALIDATED


def _producer(
    pid_: str, kind: ProducerKind, fidelity: int, cost: float, predictors: tuple[str, ...]
) -> Producer:
    return Producer(
        id=pid_,
        kind=kind,
        quantities=("q",),
        fidelity=fidelity,
        cost=cost,
        code_hash=f"code-{pid_}",
        depends_on=(*predictors, "inputs"),
        predictors=predictors,
    )


PRODUCERS = {
    p.id: p
    for p in [
        _producer("ml", K.ML_PREDICTION, 1, 1.0, ("tpm",)),
        _producer("ml_lptn", K.ML_PREDICTION, 1, 1.5, ("lptn",)),  # shares a predictor with `sim`
        _producer("sim", K.PHYSICS_SIM, 2, 3.0, ("lptn",)),
        _producer("meas", K.MEASUREMENT, 3, 10.0, ()),
    ]
}
REQ = Requirement(
    id="R", text="t", quantity="q", op=Comparator.LE, limit=100.0, unit="degC", criticality=Criticality.MEDIUM
)
CLAIMS = {
    c.id: c
    for c in [
        Claim(id="C-A", requirement_id="R", subject_id="S1"),  # medium (criticality)
        Claim(id="C-B", requirement_id="R", subject_id="S1", policy_id="low"),
        Claim(id="C-S2", requirement_id="R", subject_id="S2", policy_id="low"),
    ]
}
SNAP = Snapshot.create(
    manifest_hash="m",
    quantities={"q": "degC"},
    artifacts={},
    versions={},
    assumptions={},
    requirements={"R": REQ},
    subjects={},
    claims=CLAIMS,
    policies=dict(DEFAULT_POLICIES),
    producers=PRODUCERS,
)


def ev(pid_: str, lo: float, hi: float, *, subject: str = "S1", in_domain: bool | None = True) -> Evidence:
    p = PRODUCERS[pid_]
    return Evidence.create(
        producer_id=pid_,
        producer_kind=p.kind,
        fidelity=p.fidelity,
        subject_id=subject,
        result=EvidenceResult(
            quantity="q",
            unit="degC",
            point=(lo + hi) / 2,
            interval=Interval(lo=lo, hi=hi, unit="degC"),
            uncertainty_kind="model_form",
            in_domain=in_domain,
        ),
        deps=(),
        provenance=Provenance(producer_code_hash=p.code_hash, snapshot_id="s0"),
        cost=p.cost,
    )


def PASS(pid_: str, **kw: Any) -> Evidence:
    return ev(pid_, 80, 90, **kw)


def FAIL(pid_: str, **kw: Any) -> Evidence:
    return ev(pid_, 110, 120, **kw)


def cf(original: Evidence, widen: float) -> AssessInput:
    assert original.result.interval is not None
    derived = Evidence.create(
        **{
            **{name: getattr(original, name) for name in Evidence.model_fields if name != "id"},
            "result": original.result.model_copy(update={"interval": original.result.interval.widen(widen)}),
            "derived_from_evidence": original.id,
        }
    )
    return AssessInput(evidence=derived, freshness=CF, original=original)


def everywhere(_p: str, _s: str) -> bool:
    return True


def problem(*items: AssessInput, **kw: Any) -> PlanningProblem:
    return build_problem(
        SNAP, assess_all(SNAP, items), items, available=kw.pop("available", everywhere), **kw
    )


def cand(pr: PlanningProblem, cid: str) -> Any:
    (c,) = [c for c in pr.candidates if c.id == cid]
    return c


def ids(pr: PlanningProblem) -> set[str]:
    return {c.id for c in pr.candidates}


def test_weights_and_every_conjunct_is_an_obligation() -> None:
    pr = problem()
    assert CRITICALITY_WEIGHT == {"low": 1, "medium": 3, "high": 10}
    assert pr.claim_weights == {"C-A": 3, "C-B": 3, "C-S2": 3}  # weight follows the requirement's criticality
    assert pr.clauses["C-A"] == (("C-A/0/0", "C-A/0/1"), ("C-A/1/0",), ("C-A/2/0",))
    assert len(pr.clauses["C-B"]) == 4
    assert all(pr.obligations[k].key == k for k in pr.obligations)
    assert [c.id for c in pr.candidates] == sorted(c.id for c in pr.candidates)
    assert pr.snapshot_id == SNAP.id


def test_one_measurement_serves_two_claims_on_its_subject() -> None:
    pr = problem()
    assert cand(pr, "meas@S1").satisfies == ("C-A/1/0", "C-B/2/0")
    assert cand(pr, "meas@S1").cost == 10.0
    assert cand(pr, "meas@S2").satisfies == ("C-S2/2/0",)


def test_fresh_pass_is_reused_at_cost_zero_and_blocks_its_own_rerun() -> None:
    p = PASS("sim")
    pr = problem(AssessInput(p, FX))
    c = cand(pr, f"existing:{p.id}")
    assert c.cost == 0 and c.existing_evidence_id == p.id
    assert c.satisfies == ("C-A/0/1",)  # C-B (low) is already supported by it, so not planned
    assert c.predictors == ("lptn",)
    assert "sim@S1" not in ids(pr)  # FRESH_EXACT: a deterministic rerun would reproduce it
    assert "sim@S2" in ids(pr)


def test_unavailable_and_known_out_of_domain_producers_yield_no_candidate() -> None:
    pr = problem(available=lambda p, s: not (p == "meas" and s == "S2"))
    assert "meas@S2" not in ids(pr) and "meas@S1" in ids(pr)
    pr = problem(known_out_of_domain=frozenset({("ml", "S1"), ("sim", "S2")}))
    assert "ml@S1" not in ids(pr)
    assert "ml@S2" in ids(pr)
    assert "sim@S2" in ids(pr)  # known_out_of_domain only removes ML candidates


def test_shared_predictor_gives_incompatible_entries() -> None:
    pr = problem()
    # medium clause 0: physics (o = C-A/0/1) must be independent of ML (o' = C-A/0/0).
    assert ("sim@S1", "C-A/0/1", "ml_lptn@S1", "C-A/0/0") in pr.incompatible
    assert ("sim@S1", "C-A/0/1", "ml@S1", "C-A/0/0") not in pr.incompatible
    assert list(pr.incompatible) == sorted(pr.incompatible)
    out = plan(pr, planner="ilp")
    assert out.chosen_clauses["C-A"] == 0
    assert {r.candidate_id for r in out.runs} == {"ml@S1", "sim@S1", "ml@S2"}


def test_carried_forward_item_stays_rerunnable() -> None:
    item = cf(PASS("sim"), 1.0)
    pr = problem(item)
    assert "sim@S1" in ids(pr)
    assert f"existing:{item.evidence.id}" in ids(pr)  # its widened interval [79, 91] still passes


def test_out_of_scope_item_stays_rerunnable() -> None:
    pr = problem(AssessInput(PASS("sim"), FreshnessClass.FRESH_OUT_OF_SCOPE))
    assert "sim@S1" in ids(pr)


def test_lost_fail_adds_mandatory_rerun_that_reuse_cannot_discharge() -> None:
    lost, meas = FAIL("sim"), PASS("meas")
    items = (AssessInput(lost, INV), AssessInput(meas, FX))
    status = assess_all(SNAP, items)
    assert status["C-A"].status is Status.STALE  # rule 2: lost fail
    pr = problem(*items)
    rk = "rerun:sim@S1"
    assert all(rk in clause for clause in pr.clauses["C-A"])
    assert all(rk in clause for clause in pr.clauses["C-B"])
    assert cand(pr, f"existing:{meas.id}").satisfies == ("C-A/1/0", "C-B/2/0")
    assert rk in cand(pr, "sim@S1").satisfies
    assert [c.id for c in pr.candidates if rk in c.satisfies] == ["sim@S1"]

    broke = plan(pr, objective="max_restored", budget=0)
    assert {"C-A", "C-B"} <= set(broke.deferred)
    assert "C-A" not in broke.chosen_clauses and "C-A" not in broke.unrestorable
    assert broke.total_cost == 0

    full = plan(pr)
    assert full.chosen_clauses["C-A"] == 1  # measurement reused, rerun paid once for both claims
    (run,) = [r for r in full.runs if r.candidate_id == "sim@S1"]
    assert rk in run.discharges


def test_lost_fail_without_rerun_candidate_is_unrestorable() -> None:
    items = (AssessInput(FAIL("sim"), INV), AssessInput(PASS("meas"), FX))
    pr = problem(*items, available=lambda p, s: p != "sim")
    out = plan(pr)
    assert {"C-A", "C-B"} <= set(out.unrestorable)


def test_deterministic_problem() -> None:
    items = (AssessInput(FAIL("sim"), INV), AssessInput(PASS("meas"), FX), cf(PASS("ml"), 0.5))
    assert problem(*items) == problem(*reversed(items))


# ---------------------------------------------------------------- mini project (hand-derived, EXPECTED.md)


def _mini_items(mini: Any, skip: set[str], new_scale: str) -> tuple[Snapshot, list[AssessInput]]:
    s0 = mini.snapshot()
    ev0 = {k: e for k, e in run_all(mini, s0).items() if k[0] not in skip}
    edit(mini, "params/params.yaml", "scale: 1.0", f"scale: {new_scale}")
    s1 = mini.snapshot()
    fr = classify_all(list(ev0.values()), {s0.id: s0}, s1, {s0.id: diff_snapshots(s0, s1)})
    items = []
    for e in ev0.values():
        r = fr[e.id]
        if r.cls is CF:
            items.append(AssessInput(carry_forward(e, r, s1), CF, original=e))
        else:
            items.append(AssessInput(e, r.cls))
    return s1, items


def _mini_problem(mini: Any, s1: Snapshot, items: list[AssessInput]) -> PlanningProblem:
    avail = {rp.meta.id: rp.available_for for rp in mini.registry.all()}

    def available(p: str, s: str) -> bool:
        f = avail[p]
        return f is None or bool(f(s1.subjects[s]))

    return build_problem(
        s1,
        assess_all(s1, items),
        items,
        available=available,
        known_out_of_domain=frozenset({(pid(mini, "predict_temp"), "S2")}),
    )


def test_mini_small_scale_change_without_measurement(mini: Any) -> None:
    # scale 1.0 -> 1.02: predict_temp invalidated (no tolerance), sim_temp carried forward (still PASS on S1).
    s1, items = _mini_items(mini, {"measure_temp"}, "1.02")
    st = assess_all(s1, items)
    assert st["C-S1-TEMP"].status is Status.STALE and st["C-S1-HI"].status is Status.STALE
    assert st["C-S2-TEMP"].status is Status.VIOLATED  # carried-forward FAIL stays FAIL; not planned
    pr = _mini_problem(mini, s1, items)
    assert set(pr.claim_weights) == {"C-S1-TEMP", "C-S1-HI"}
    predict, sim, meas = (pid(mini, n) for n in ("predict_temp", "sim_temp", "measure_temp"))
    assert {c.id for c in pr.candidates if c.existing_evidence_id is None} == {
        f"{predict}@S1",
        f"{sim}@S1",  # carried forward: still rerunnable
        f"{meas}@S1",
    }

    best = plan(pr)
    assert best.solver_status == "OPTIMAL"
    assert best.total_cost == 1.0
    (run,) = best.runs
    assert run.candidate_id == f"{predict}@S1"
    assert run.discharges == ("C-S1-HI/1/1", "C-S1-TEMP/0/0")
    assert best.chosen_clauses == {"C-S1-HI": 1, "C-S1-TEMP": 0}
    assert best.unrestorable == () and best.deferred == ()

    assert plan(pr, objective="max_restored", budget=0).deferred == ("C-S1-HI", "C-S1-TEMP")
    assert plan(pr, objective="max_restored", budget=1).deferred == ()
    assert plan(pr, planner="greedy").total_cost == 1.0
    assert plan(pr, planner="all").total_cost == 14.0


def test_mini_out_of_range_change_makes_lost_fail_unrestorable(mini: Any) -> None:
    # scale 1.0 -> 2.0 is outside sim_temp's valid range: the S2 FAIL is lost; S2 has no ML (OOD),
    # no measurement and no analytic producer, so C-S2-TEMP cannot be restored. S1 stays measured.
    s1, items = _mini_items(mini, set(), "2.0")
    st = assess_all(s1, items)
    assert st["C-S2-TEMP"].status is Status.STALE
    pr = _mini_problem(mini, s1, items)
    sim = pid(mini, "sim_temp")
    assert set(pr.claim_weights) == {"C-S2-TEMP"}
    rk = f"rerun:{sim}@S2"
    assert all(rk in clause for clause in pr.clauses["C-S2-TEMP"])
    assert [c.id for c in pr.candidates] == [f"{sim}@S2"]
    out = plan(pr)
    assert out.unrestorable == ("C-S2-TEMP",)
    assert out.runs == () and out.total_cost == 0


def test_build_problem_rejects_unknown_claim() -> None:
    from reval.domain import Assessment

    a = Assessment(
        claim_id="X", snapshot_id=SNAP.id, status=Status.STALE, reasons=(), evidence=(), input_hash="h"
    )
    with pytest.raises(ValueError):
        build_problem(SNAP, {"X": a}, (), available=everywhere)
