"""P4-07: budgeted (max_restored) planner: brute force, monotonicity, deferred vs unrestorable."""

import pytest

from reval.core.planner import plan
from tests.helpers.planner_cases import brute_force, plan_cost_int, random_problem

BUDGETS = [0.0, 1.0, 2.5, 6.0]


@pytest.mark.parametrize("seed", range(100))
def test_budgeted_ilp_matches_brute_force_and_is_monotone(seed: int) -> None:
    pr = random_problem(seed)
    last_weight = -1
    for b in BUDGETS:
        out = plan(pr, objective="max_restored", budget=b)
        assert out.solver_status == "OPTIMAL"
        assert out.budget == b and out.objective == "max_restored"
        opt = brute_force(pr, budget=b)
        weight = sum(pr.claim_weights[c] for c in out.chosen_clauses)
        assert weight == opt.weight
        assert plan_cost_int(out.total_cost) == opt.cost_int
        assert plan_cost_int(out.total_cost) <= round(b * 100)
        # unrestorable does not depend on the budget; deferred is the rest of the uncovered claims.
        assert set(out.unrestorable) == set(pr.claim_weights) - opt.restorable
        assert set(out.deferred) == opt.restorable - set(out.chosen_clauses)
        assert not set(out.deferred) & set(out.unrestorable)
        assert weight >= last_weight  # a larger budget never restores less weight
        last_weight = weight


@pytest.mark.parametrize("seed", range(50))
def test_budget_zero_defers_everything_that_needs_a_paid_run(seed: int) -> None:
    pr = random_problem(seed)
    paid = tuple(c for c in pr.candidates if c.cost > 0)
    gone = {c.id for c in pr.candidates if c.cost == 0}
    no_reuse = pr.model_copy(
        update={
            "candidates": paid,
            "incompatible": tuple(t for t in pr.incompatible if not {t[0], t[2]} & gone),
        }
    )
    out = plan(no_reuse, objective="max_restored", budget=0)
    full = plan(no_reuse)
    assert out.chosen_clauses == {} and out.runs == ()
    assert set(out.deferred) == set(full.chosen_clauses)
    assert out.unrestorable == full.unrestorable


def test_max_restored_requires_a_nonnegative_budget() -> None:
    pr = random_problem(1)
    with pytest.raises(ValueError):
        plan(pr, objective="max_restored")
    with pytest.raises(ValueError):
        plan(pr, objective="max_restored", budget=-1)
