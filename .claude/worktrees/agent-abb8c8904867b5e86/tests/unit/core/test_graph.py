"""EvidenceGraph on the mini project."""

from typing import Any

from reval.core.graph import EvidenceGraph
from reval.sdk.runner import run_producer


def _all_evidence(mini: Any, snap: Any) -> list[Any]:
    out = []
    for rp in mini.registry.all():
        for sid in sorted(snap.subjects):
            sub = snap.subjects[sid]
            if rp.available_for is None or rp.available_for(sub):
                out.extend(run_producer(mini.registry, rp.meta.id, sub, snap, mini.root))
    return out


def test_cone_influence_and_order(mini: Any) -> None:
    snap = mini.snapshot()
    ev = _all_evidence(mini, snap)
    g = EvidenceGraph.build(snap, ev)

    cone = g.claim_cone("C-SHAFT")
    assert "field:params#/shaft/d_mm" in cone and "artifact:params" in cone
    assert "field:params#/load/scale" not in cone and "artifact:data" not in cone

    infl = g.influence("artifact:data")
    assert "artifact:surrogate" in infl and "claim:C-S1-TEMP" in infl
    pred = next(e for e in ev if e.producer_id.endswith("predict_temp") and e.subject_id == "S1")
    assert f"evidence:{pred.id}" in infl
    assert "claim:C-SHAFT" not in infl

    ids = [e.id for e in g.evidence_for_claim("C-S1-TEMP")]
    assert ids == sorted(ids) and len(ids) == 3  # ml, physics, measurement on S1
    assert len(g.evidence_for_claim("C-S2-TEMP")) == 2
    assert len(g.evidence_for_claim("C-SHAFT")) == 1

    j1 = g.to_json()
    j2 = EvidenceGraph.build(snap, list(reversed(ev))).to_json()
    assert j1 == j2
    assert [n["id"] for n in j1["nodes"]] == sorted(n["id"] for n in j1["nodes"])
    focus = g.to_json("claim:C-SHAFT")
    assert {n["id"] for n in focus["nodes"]} == {"claim:C-SHAFT"} | cone
