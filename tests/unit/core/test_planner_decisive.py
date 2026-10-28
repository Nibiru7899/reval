"""P4-17: decisiveness-aware planning (expected cost sum(cost_j / p_j), docs/04 A7)."""

import itertools
import random

import pytest

from reval.core.planner import P_MIN, P_OOD, P_OOD_TOUCHED, build_problem, decisiveness, plan
from reval.core.status import AssessInput, assess_all
from reval.domain import (
    DEFAULT_POLICIES,
    CandidateRun,
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
)
from tests.helpers.planner_cases import Coverage, random_problem

K = ProducerKind
FX = FreshnessClass.FRESH_EXACT
INV = FreshnessClass.INVALIDATED
CF = FreshnessClass.CARRY_FORWARD


def _producer(pid: str, kind: ProducerKind, cost: float, predictors: tuple[str, ...]) -> Producer:
    return Producer(
        id=pid,
        kind=kind,
        quantities=("q",),
        fidelity=2,
        cost=cost,
        code_hash=f"code-{pid}",
        depends_on=(*predictors, "inputs"),
        predictors=predictors,
    )


# Shaped like the M4 demo: cheap ML and physics, an expensive bench measurement.
PRODUCERS = {
    p.id: p
    for p in [
        _producer("ml", K.ML_PREDICTION, 1.0, ("tpm",)),
        _producer("sim", K.PHYSICS_SIM, 5.0, ("lptn",)),
        _producer("meas", K.MEASUREMENT, 100.0, ()),
    ]
}
REQ = Requirement(
    id="R", text="t", quantity="q", op=Comparator.LE, limit=100.0, unit="degC", criticality=Criticality.MEDIUM
)
SNAP = Snapshot.create(
    manifest_hash="m",
    quantities={"q": "degC"},
    artifacts={},
    versions={},
    assumptions={},
    requirements={"R": REQ},
    subjects={},
    claims={"C": Claim(id="C", requirement_id="R", subject_id="S")},  # medium: ML+sim, or meas
    policies=dict(DEFAULT_POLICIES),
    producers=PRODUCERS,
)


def ev(pid: str, lo: float, hi: float, *, in_domain: bool | None = True) -> Evidence:
    p = PRODUCERS[pid]
    return Evidence.create(
        producer_id=pid,
        producer_kind=p.kind,
        fidelity=p.fidelity,
        subject_id="S",
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


def everywhere(_p: str, _s: str) -> bool:
    return True


def _problem(items: tuple[AssessInput, ...], *, with_prior: bool) -> PlanningProblem:
    prior = {(i.evidence.producer_id, i.evidence.subject_id, "q"): i for i in items} if with_prior else None
    return build_problem(SNAP, assess_all(SNAP, items), items, available=everywhere, prior=prior)


# Both cheap producers were inconclusive by a wide margin before the change (now invalidated).
WIDE = (AssessInput(ev("ml", 60, 141), INV), AssessInput(ev("sim", 59, 140), INV))


# --- decisiveness estimate ---------------------------------------------------------------------------------


def test_no_prior_is_decisive() -> None:
    assert decisiveness(None, REQ) == 1.0


@pytest.mark.parametrize(("lo", "hi"), [(80, 90), (110, 120), (90, 100)])
def test_decisive_prior_gives_one(lo: float, hi: float) -> None:
    assert decisiveness(AssessInput(ev("sim", lo, hi), INV), REQ) == 1.0


def test_out_of_domain_prior() -> None:
    e = ev("ml", 80, 90, in_domain=False)
    assert decisiveness(AssessInput(e, FX), REQ) == P_OOD
    assert decisiveness(AssessInput(e, FreshnessClass.FRESH_OUT_OF_SCOPE), REQ) == P_OOD
    assert decisiveness(AssessInput(e, FX), REQ, p_ood=0.2) == 0.2
    # Its dependencies changed since (no longer fresh): a rerun may land back in domain.
    assert decisiveness(AssessInput(e, INV), REQ) == P_OOD_TOUCHED


def test_margin_prior_ratio_and_clip() -> None:
    # center 95, half-width 10 -> |95 - 100| / 10 = 0.5
    assert decisiveness(AssessInput(ev("sim", 85, 105), INV), REQ) == pytest.approx(0.5)
    # center 100.5, half-width 40.5 -> 0.012 -> clipped to p_min
    assert decisiveness(AssessInput(ev("sim", 60, 141), INV), REQ) == P_MIN
    assert decisiveness(AssessInput(ev("sim", 60, 141), INV), REQ, p_min=0.1) == 0.1


def test_prior_without_interval_gives_p_min() -> None:
    e = ev("sim", 85, 105)
    bare = Evidence.create(
        **{
            **{n: getattr(e, n) for n in Evidence.model_fields if n != "id"},
            "result": e.result.model_copy(update={"interval": None, "uncertainty_kind": "none"}),
        }
    )
    assert decisiveness(AssessInput(bare, INV), REQ) == P_MIN


def test_carry_forward_prior_judges_the_original() -> None:
    original = ev("sim", 80, 90)  # PASS as recorded; the carried copy straddles after inflation
    derived = Evidence.create(
        **{
            **{n: getattr(original, n) for n in Evidence.model_fields if n != "id"},
            "result": original.result.model_copy(update={"interval": Interval(lo=70, hi=110, unit="degC")}),
            "derived_from_evidence": original.id,
        }
    )
    assert decisiveness(AssessInput(derived, CF, original=original), REQ) == 1.0


# --- planning ----------------------------------------------------------------------------------------------


def test_demo_like_case_chooses_the_measurement() -> None:
    pr = _problem(WIDE, with_prior=True)
    p_of = {c.id: c.p_decisive for c in pr.candidates}
    assert p_of == {"meas@S": 1.0, "ml@S": P_MIN, "sim@S": P_MIN}
    result = plan(pr)
    assert result.solver_status == "OPTIMAL"
    assert [r.candidate_id for r in result.runs] == ["meas@S"]
    assert result.total_cost == 100.0  # true cost; the objective used the expected cost
    assert result.runs[0].p_decisive == 1.0


def test_one_shot_plan_is_unchanged_without_prior() -> None:
    pr = _problem(WIDE, with_prior=False)
    assert all(c.p_decisive == 1.0 for c in pr.candidates)
    plain = build_problem(SNAP, assess_all(SNAP, WIDE), WIDE, available=everywhere)
    assert pr == plain
    result = plan(pr)
    assert [r.candidate_id for r in result.runs] == ["ml@S", "sim@S"]
    assert result.total_cost == 6.0


def test_narrow_margin_keeps_the_cheap_runs() -> None:
    items = (AssessInput(ev("ml", 92, 102), INV), AssessInput(ev("sim", 93, 101), INV))
    result = plan(_problem(items, with_prior=True))
    assert [r.candidate_id for r in result.runs] == ["ml@S", "sim@S"]
    assert {r.candidate_id: r.p_decisive for r in result.runs} == {
        "ml@S": pytest.approx(0.6),
        "sim@S": pytest.approx(0.75),
    }


def test_greedy_also_uses_expected_cost() -> None:
    result = plan(_problem(WIDE, with_prior=True), planner="greedy")
    assert [r.candidate_id for r in result.runs] == ["meas@S"]


def test_budget_constrains_the_true_cost() -> None:
    pr = _problem(WIDE, with_prior=True)
    # Expected cost of ML + sim is 120, true cost 6: a budget of 6 still restores the claim.
    result = plan(pr, objective="max_restored", budget=6.0)
    assert [r.candidate_id for r in result.runs] == ["ml@S", "sim@S"]
    assert result.deferred == ()


def test_deterministic() -> None:
    a = plan(_problem(WIDE, with_prior=True))
    b = plan(_problem(WIDE, with_prior=True))
    assert a.model_dump_json() == b.model_dump_json()


def test_invalid_probabilities_rejected() -> None:
    with pytest.raises(ValueError):
        CandidateRun(id="x", producer_id="x", subject_id="S", cost=1.0, satisfies=(), p_decisive=0.0)
    with pytest.raises(ValueError):
        build_problem(SNAP, {}, (), available=everywhere, p_min=0.0)


# --- brute force with a fixed p per candidate --------------------------------------------------------------


def _with_random_p(pr: PlanningProblem, seed: int) -> PlanningProblem:
    rng = random.Random(1000 + seed)
    cands = tuple(
        c.model_copy(update={"p_decisive": rng.choice([0.05, 0.1, 0.25, 0.5, 0.8, 1.0])})
        if c.existing_evidence_id is None
        else c
        for c in pr.candidates
    )
    return pr.model_copy(update={"candidates": cands})


def _brute_force(pr: PlanningProblem, budget: float | None) -> tuple[int, int]:
    """(max restored weight, then min expected cost in hundredths) over every subset of candidates."""
    ids = [c.id for c in pr.candidates]
    exp = {c.id: round(c.cost * 100 / c.p_decisive) for c in pr.candidates}
    true = {c.id: round(c.cost * 100) for c in pr.candidates}
    cap = None if budget is None else round(budget * 100)
    cov = Coverage(pr)
    best: tuple[int, int] | None = None
    for r in range(len(ids) + 1):
        for subset in itertools.combinations(ids, r):
            if cap is not None and sum(true[j] for j in subset) > cap:
                continue
            w = sum(pr.claim_weights[c] for c in cov.restored(frozenset(subset)))
            key = (-w, sum(exp[j] for j in subset))
            if best is None or key < best:
                best = key
    assert best is not None
    return -best[0], best[1]


@pytest.mark.parametrize("seed", range(40))
@pytest.mark.parametrize("budget", [None, 3.0])
def test_ilp_matches_brute_force_on_expected_cost(seed: int, budget: float | None) -> None:
    pr = _with_random_p(random_problem(seed, max_candidates=8), seed)
    objective = "min_cost" if budget is None else "max_restored"
    result = plan(pr, objective=objective, budget=budget)
    assert result.solver_status == "OPTIMAL"
    weight, exp_int = _brute_force(pr, budget)
    p_of = {c.id: c.p_decisive for c in pr.candidates}
    got_weight = sum(pr.claim_weights[c] for c in result.chosen_clauses)
    assert got_weight == weight
    # Idle zero-cost runs are dropped from `runs`, so compare on runs with a cost.
    got_exp = sum(round(r.cost * 100 / p_of[r.candidate_id]) for r in result.runs)
    assert got_exp == exp_int
    for r in result.runs:
        assert r.p_decisive == p_of[r.candidate_id]
    if budget is not None:
        assert round(result.total_cost * 100) <= round(budget * 100)
