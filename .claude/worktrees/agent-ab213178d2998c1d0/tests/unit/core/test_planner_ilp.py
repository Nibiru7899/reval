"""P4-06: CP-SAT min-cost planner against brute force over all candidate subsets."""

import pytest

from reval.core.canonical import canonical_json, content_id
from reval.core.planner import plan
from reval.domain import CandidateRun, EvidenceRequirement, Obligation, PlanningProblem, ProducerKind
from tests.helpers.planner_cases import Coverage, brute_force, plan_cost_int, random_problem

K = ProducerKind


def _selected(problem: PlanningProblem, run_ids: set[str]) -> frozenset[str]:
    return frozenset(run_ids | {c.id for c in problem.candidates if c.existing_evidence_id is not None})


@pytest.mark.parametrize("seed", range(200))
def test_ilp_matches_brute_force(seed: int) -> None:
    pr = random_problem(seed)
    out = plan(pr)
    assert out.solver_status == "OPTIMAL" and out.reproducible
    opt = brute_force(pr)
    assert plan_cost_int(out.total_cost) == opt.cost_int
    assert sum(pr.claim_weights[c] for c in out.chosen_clauses) == opt.weight
    assert set(out.chosen_clauses) == opt.restorable  # min_cost restores every restorable claim
    assert set(out.unrestorable) == set(pr.claim_weights) - opt.restorable
    assert out.deferred == ()
    # Every chosen clause is covered by the planned runs plus reuse, under distinctness and independence.
    cov = Coverage(pr)
    assert set(out.chosen_clauses) <= cov.restored(_selected(pr, {r.candidate_id for r in out.runs}))
    assert [(r.cost, r.candidate_id) for r in out.runs] == sorted((r.cost, r.candidate_id) for r in out.runs)
    assert all(not r.candidate_id.startswith("existing:") for r in out.runs)


def test_same_input_gives_byte_identical_plan() -> None:
    for seed in range(20):
        pr = random_problem(seed)
        a, b = plan(pr), plan(pr.model_copy())
        assert canonical_json(a) == canonical_json(b)
        assert a.id == content_id(a)


def _medium(
    cands: list[CandidateRun], incompatible: tuple[tuple[str, str, str, str], ...]
) -> PlanningProblem:
    o_ml = Obligation(
        claim_id="C", clause_index=0, conjunct_index=0, requirement=EvidenceRequirement(kind=K.ML_PREDICTION)
    )
    o_ph = Obligation(
        claim_id="C",
        clause_index=0,
        conjunct_index=1,
        requirement=EvidenceRequirement(kind=K.PHYSICS_SIM, independent_of=(K.ML_PREDICTION,)),
    )
    return PlanningProblem(
        snapshot_id="s",
        claim_weights={"C": 3},
        clauses={"C": ((o_ml.key, o_ph.key),)},
        obligations={o_ml.key: o_ml, o_ph.key: o_ph},
        candidates=tuple(sorted(cands, key=lambda c: c.id)),
        incompatible=incompatible,
    )


def _run(jid: str, cost: float, sat: str, pred: str) -> CandidateRun:
    return CandidateRun(
        id=jid, producer_id=jid.split("@")[0], subject_id="S", cost=cost, satisfies=(sat,), predictors=(pred,)
    )


def test_incompatible_pair_is_never_used_together() -> None:
    cands = [
        _run("ml@S", 1.0, "C/0/0", "a"),
        _run("ph@S", 1.0, "C/0/1", "a"),
        _run("ph2@S", 2.5, "C/0/1", "b"),
    ]
    inc = (("ph@S", "C/0/1", "ml@S", "C/0/0"),)
    out = plan(_medium(cands, inc))
    assert {r.candidate_id for r in out.runs} == {"ml@S", "ph2@S"}
    assert out.total_cost == 3.5
    # Without the independent alternative the claim is unrestorable; the incompatible pair never covers it.
    out = plan(_medium(cands[:2], inc))
    assert out.unrestorable == ("C",) and out.runs == ()


def test_one_run_counts_once_per_clause() -> None:
    o1, o2 = (
        Obligation(
            claim_id="C",
            clause_index=0,
            conjunct_index=i,
            requirement=EvidenceRequirement(kind=K.MEASUREMENT),
        )
        for i in range(2)
    )
    both = CandidateRun(id="m@S", producer_id="m", subject_id="S", cost=1.0, satisfies=(o1.key, o2.key))
    pr = PlanningProblem(
        snapshot_id="s",
        claim_weights={"C": 1},
        clauses={"C": ((o1.key, o2.key),)},
        obligations={o1.key: o1, o2.key: o2},
        candidates=(both,),
    )
    assert plan(pr).unrestorable == ("C",)


def test_invalid_arguments() -> None:
    pr = random_problem(0)
    with pytest.raises(ValueError):
        plan(pr, budget=5.0)  # min_cost takes no budget
    with pytest.raises(ValueError):
        plan(pr, planner="nope")  # type: ignore[arg-type]
