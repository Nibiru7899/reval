"""Mini project end to end: snapshot -> producers -> assess_all matches EXPECTED.md."""

from typing import Any

from reval.core.status import AssessInput, assess_all
from reval.domain.status import FreshnessClass, Status
from reval.sdk.runner import run_producer


def test_expected_statuses(mini: Any) -> None:
    snap = mini.snapshot()
    items = []
    for rp in mini.registry.all():
        for sid in sorted(snap.subjects):
            sub = snap.subjects[sid]
            if rp.available_for is None or rp.available_for(sub):
                items += [
                    AssessInput(e, FreshnessClass.FRESH_EXACT)
                    for e in run_producer(mini.registry, rp.meta.id, sub, snap, mini.root)
                ]
    res = assess_all(snap, items)
    assert {k: v.status for k, v in res.items()} == {
        "C-S1-TEMP": Status.SUPPORTED,
        "C-S2-TEMP": Status.VIOLATED,
        "C-S1-HI": Status.SUPPORTED,
        "C-SHAFT": Status.SUPPORTED,
    }
    assert res["C-S1-TEMP"].satisfied_clause == 0
    assert res["C-S1-HI"].satisfied_clause == 0
    assert res["C-SHAFT"].satisfied_clause == 3
    none = assess_all(snap, [])
    assert {a.status for a in none.values()} == {Status.INCONCLUSIVE}
