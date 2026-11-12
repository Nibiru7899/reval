"""P4-08: greedy and "all" planners against the ILP."""

import pytest

from reval.core.planner import plan
from tests.helpers.planner_cases import Coverage, plan_cost_int, random_problem


@pytest.mark.parametrize("seed", range(200))
def test_greedy_is_feasible_and_never_beats_the_ilp(seed: int) -> None:
    pr = random_problem(seed)
    ilp, greedy = plan(pr), plan(pr, planner="greedy")
    assert greedy.solver_status == "GREEDY" and greedy.planner == "greedy"
    assert plan_cost_int(greedy.total_cost) >= plan_cost_int(ilp.total_cost)
    assert set(greedy.chosen_clauses) >= set(ilp.chosen_clauses)
    assert greedy.unrestorable == ilp.unrestorable
    selected = {r.candidate_id for r in greedy.runs} | {
        c.id for c in pr.candidates if c.existing_evidence_id is not None
    }
    assert set(greedy.chosen_clauses) <= Coverage(pr).restored(frozenset(selected))  # respects incompatible


@pytest.mark.parametrize("seed", range(100))
def test_all_selects_every_useful_new_run(seed: int) -> None:
    pr = random_problem(seed)
    out = plan(pr, planner="all")
    useful = [c for c in pr.candidates if c.existing_evidence_id is None and c.satisfies]
    assert out.solver_status == "ALL"
    assert {r.candidate_id for r in out.runs} == {c.id for c in useful}
    assert plan_cost_int(out.total_cost) == sum(round(c.cost * 100) for c in useful)
    assert set(out.chosen_clauses) == set(pr.claim_weights) - set(out.unrestorable)


@pytest.mark.parametrize("seed", range(50))
def test_greedy_under_budget(seed: int) -> None:
    pr = random_problem(seed)
    out = plan(pr, planner="greedy", objective="max_restored", budget=2.0)
    assert plan_cost_int(out.total_cost) <= 200
    assert not set(out.deferred) & set(out.chosen_clauses)
    assert set(out.deferred) | set(out.chosen_clauses) | set(out.unrestorable) == set(pr.claim_weights)


def test_all_rejects_a_budget() -> None:
    with pytest.raises(ValueError):
        plan(random_problem(0), planner="all", objective="max_restored", budget=1.0)
