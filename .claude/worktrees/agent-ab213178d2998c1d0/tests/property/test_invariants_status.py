"""Invariants I1, I2, I4 of docs/03 section 5 on random small projects (no diff engine needed yet)."""

import json
import os
import subprocess
import sys
from pathlib import Path

from hypothesis import find, given
from hypothesis import strategies as st

from reval.core.canonical import canonical_json
from reval.core.status import AssessInput, assess_all, assess_claim
from reval.domain import ACCEPTED_STATUSES, Assessment, Evidence, FreshnessClass
from tests.property.strategies import (
    FX,
    INV,
    OOS,
    Case,
    cases,
    irrelevant_items,
    make_evidence,
    single_claim_snapshot,
)

CF = FreshnessClass.CARRY_FORWARD
_ROOT = Path(__file__).resolve().parents[2]

_CHILD = """
import json, sys
from reval.core.canonical import canonical_json
from reval.core.status import AssessInput, assess_all
from reval.domain import Evidence, FreshnessClass, Snapshot
raw = json.load(sys.stdin)
snap = Snapshot.model_validate(raw["snapshot"])
items = [
    AssessInput(Evidence.model_validate(i["evidence"]), FreshnessClass(i["freshness"]))
    for i in raw["items"]
]
sys.stdout.write(canonical_json(assess_all(snap, items)).decode())
"""


def _hashes(assessments: dict[str, Assessment]) -> dict[str, str]:
    return {cid: a.input_hash for cid, a in assessments.items()}


# ----------------------------------------------------------------------------------------------- I1


@given(cases())
def test_i1_determinism(case: Case) -> None:
    first = assess_all(case.snapshot, case.items)
    # A reversed input order must not matter either: status depends on the set of items.
    second = assess_all(case.snapshot, tuple(reversed(case.items)))
    assert first == second
    assert _hashes(first) == _hashes(second)
    assert canonical_json(first) == canonical_json(second)


def test_i1_identical_in_a_fresh_process() -> None:
    """One concrete example is re-assessed in a separate interpreter (different hash seed)."""
    ex = find(cases(), lambda c: len(c.items) >= 4 and len(c.snapshot.claims) >= 3)
    payload = json.dumps(
        {
            "snapshot": json.loads(canonical_json(ex.snapshot)),
            "items": [
                {"evidence": json.loads(canonical_json(i.evidence)), "freshness": i.freshness.value}
                for i in ex.items
            ],
        }
    )
    env = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join([str(_ROOT / "src"), str(_ROOT)]),
        "PYTHONHASHSEED": "random",
    }
    out = subprocess.run(
        [sys.executable, "-c", _CHILD], input=payload, capture_output=True, text=True, env=env, check=True
    ).stdout
    assert out.encode() == canonical_json(assess_all(ex.snapshot, ex.items))


# ----------------------------------------------------------------------------------------------- I2


@given(st.data())
def test_i2_unrelated_evidence_never_changes_a_claim(data: st.DataObject) -> None:
    case = data.draw(cases())
    extras = data.draw(irrelevant_items(tuple(case.snapshot.claims)))
    fresh = data.draw(st.lists(st.sampled_from([FX, OOS, INV]), min_size=len(extras), max_size=len(extras)))
    known = {i.evidence.id for i in case.items}
    added = [AssessInput(e, f) for e, f in zip(extras, fresh, strict=True) if e.id not in known]
    before = assess_all(case.snapshot, case.items)
    after = assess_all(case.snapshot, [*case.items, *added])
    assert before == after


@given(cases())
def test_i2_claim_depends_only_on_its_own_subject_and_quantity(case: Case) -> None:
    for cid, claim in case.snapshot.claims.items():
        quantity = case.snapshot.requirements[claim.requirement_id].quantity
        own = [
            i
            for i in case.items
            if i.evidence.subject_id == claim.subject_id
            and i.evidence.result.quantity == quantity
            and (i.evidence.waiver is None or i.evidence.waiver.claim_id == cid)
        ]
        assert assess_claim(claim, case.snapshot, case.items) == assess_claim(claim, case.snapshot, own)


# ----------------------------------------------------------------------------------------------- I4


def _carry_forward(e: Evidence, widen: float) -> AssessInput:
    assert e.result.interval is not None
    derived = Evidence.create(
        **{
            **{name: getattr(e, name) for name in Evidence.model_fields if name != "id"},
            "result": e.result.model_copy(update={"interval": e.result.interval.widen(widen)}),
            "derived_from_evidence": e.id,
        }
    )
    return AssessInput(evidence=derived, freshness=CF, original=e)


def _degrade(case: Case, actions: list[tuple[str, int]]) -> list[AssessInput]:
    """Invalidate or widen random fresh items, adding no evidence.

    Supersede exception (docs/03 I4): an item is only invalidated when no other fresh item of the same
    producer exists for the same subject and quantity: that sibling counts as new evidence for it.
    """
    out: list[AssessInput] = []
    fresh_siblings: dict[tuple[str, str, str], int] = {}
    for i in case.items:
        if i.freshness is not INV:
            e = i.evidence
            key = (e.producer_id, e.subject_id, e.result.quantity)
            fresh_siblings[key] = fresh_siblings.get(key, 0) + 1
    for k, item in enumerate(case.items):
        action, amount = actions[k % len(actions)] if actions else ("keep", 0)
        e = item.evidence
        key = (e.producer_id, e.subject_id, e.result.quantity)
        if item.freshness is INV or action == "keep":
            out.append(item)
        elif action == "invalidate":
            out.append(item if fresh_siblings[key] > 1 else AssessInput(e, INV))
        else:
            out.append(_carry_forward(e, float(amount)))
    return out


@given(
    cases(),
    st.lists(st.tuples(st.sampled_from(["keep", "invalidate", "widen"]), st.integers(0, 60)), max_size=12),
)
def test_i4_no_free_support(case: Case, actions: list[tuple[str, int]]) -> None:
    before = assess_all(case.snapshot, case.items)
    after = assess_all(case.snapshot, _degrade(case, actions))
    for cid, b in before.items():
        if b.status not in ACCEPTED_STATUSES:
            assert after[cid].status not in ACCEPTED_STATUSES, (cid, b.status, after[cid].status)


def test_i4_supersede_exception_is_real() -> None:
    """Without the exception I4 is false: invalidating a fresh FAIL next to a fresh PASS of the same
    producer is legitimate new support (the PASS supersedes it), so `_degrade` must avoid that move."""
    snap = single_claim_snapshot()
    claim = snap.claims["C0"]
    fail = make_evidence("meas", "S1", "q", 110.0, 120.0, in_domain=None, fidelity=3, seed=1)
    ok = make_evidence("meas", "S1", "q", 80.0, 90.0, in_domain=None, fidelity=3, seed=2)
    before = assess_claim(claim, snap, [AssessInput(fail, FX), AssessInput(ok, FX)])
    after = assess_claim(claim, snap, [AssessInput(fail, INV), AssessInput(ok, FX)])
    assert before.status not in ACCEPTED_STATUSES
    assert after.status in ACCEPTED_STATUSES


def test_i4_waiver_cannot_hide_a_lost_fail() -> None:
    """Ruling 2026-10-28: lost-fail STALE precedes WAIVED, so invalidating a FAIL never yields WAIVED."""
    snap = single_claim_snapshot()
    claim = snap.claims["C0"]
    fail = make_evidence("meas", "S1", "q", 110.0, 120.0, in_domain=None, fidelity=3, seed=1)
    waiver = make_evidence("waive", "S1", "q", 80.0, 90.0, in_domain=None, fidelity=0, seed=None)
    before = assess_claim(claim, snap, [AssessInput(fail, FX), AssessInput(waiver, FX)])
    after = assess_claim(claim, snap, [AssessInput(fail, INV), AssessInput(waiver, FX)])
    assert before.status not in ACCEPTED_STATUSES
    assert after.status not in ACCEPTED_STATUSES
