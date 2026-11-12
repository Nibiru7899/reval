"""Evidence graph (E1): who depends on whom, for cones and influence queries. Pure (docs/10 §4.1, §1.5)."""

from collections.abc import Sequence
from typing import Any

import networkx as nx  # type: ignore[import-untyped]

from reval.domain.evidence import Evidence
from reval.domain.selectors import Selector
from reval.domain.snapshot import Snapshot


def _node(kind: str, ident: str) -> str:
    return f"{kind}:{ident}"


class EvidenceGraph:
    """Directed graph with edges pointing from a dependency to its dependent."""

    def __init__(self, graph: "nx.DiGraph[str]", evidence: dict[str, Evidence]) -> None:
        self._g = graph
        self._evidence = evidence

    @classmethod
    def build(cls, snapshot: Snapshot, evidence: Sequence[Evidence]) -> "EvidenceGraph":
        g: nx.DiGraph[str] = nx.DiGraph()

        def add_node(kind: str, ident: str) -> str:
            n = _node(kind, ident)
            if n not in g:
                g.add_node(n, type=kind, label=ident)
            return n

        def add_edge(src: str, dst: str, kind: str) -> None:
            if not g.has_edge(src, dst):
                g.add_edge(src, dst, type=kind)

        for aid in sorted(snapshot.artifacts):
            add_node("artifact", aid)
        for aid, art in sorted(snapshot.artifacts.items()):
            for up in art.derived_from:
                add_edge(add_node("artifact", up), add_node("artifact", aid), "derived_from")
        for kind, items in (
            ("assumption", snapshot.assumptions),
            ("requirement", snapshot.requirements),
            ("subject", snapshot.subjects),
            ("producer", snapshot.producers),
        ):
            for ident in sorted(items):
                add_node(kind, ident)

        by_id: dict[str, Evidence] = {}
        for e in sorted(evidence, key=lambda x: x.id):
            if e.id in by_id:
                continue
            by_id[e.id] = e
            en = add_node("evidence", e.id)
            add_edge(add_node("producer", e.producer_id), en, "produces")
            for dep in e.deps:
                sel = Selector.parse(dep.selector)
                fn = add_node("field", sel.render())
                add_edge(add_node("artifact", sel.artifact_id), fn, "selects")
                add_edge(fn, en, "reads")
            assumption_ids = set(e.scope.assumption_ids) | {t.assumption_id for t in e.tolerances}
            for a in sorted(assumption_ids):
                add_edge(add_node("assumption", a), en, "assumes")

        for cid, claim in sorted(snapshot.claims.items()):
            cn = add_node("claim", cid)
            req = snapshot.requirements[claim.requirement_id]
            add_edge(add_node("requirement", req.id), cn, "requires")
            add_edge(add_node("subject", claim.subject_id), cn, "about")
            for e in by_id.values():
                if e.subject_id != claim.subject_id or e.result.quantity != req.quantity:
                    continue
                # A waiver speaks for exactly one claim (D10).
                if e.waiver is not None and e.waiver.claim_id != cid:
                    continue
                add_edge(_node("evidence", e.id), cn, "supports")
        return cls(g, by_id)

    def _require(self, node_id: str) -> None:
        if node_id not in self._g:
            raise KeyError(f"unknown graph node {node_id!r}")

    def claim_cone(self, claim_id: str) -> frozenset[str]:
        """Node ids of every ancestor of the claim (the claim itself excluded)."""
        n = claim_id if claim_id.startswith("claim:") else _node("claim", claim_id)
        self._require(n)
        return frozenset(nx.ancestors(self._g, n))

    def influence(self, node_id: str) -> frozenset[str]:
        """Node ids of every descendant of ``node_id`` (the node itself excluded)."""
        self._require(node_id)
        return frozenset(nx.descendants(self._g, node_id))

    def evidence_for_claim(self, claim_id: str) -> tuple[Evidence, ...]:
        n = claim_id if claim_id.startswith("claim:") else _node("claim", claim_id)
        self._require(n)
        ids = sorted(
            p.removeprefix("evidence:") for p in self._g.predecessors(n) if p.startswith("evidence:")
        )
        return tuple(self._evidence[i] for i in ids)

    def to_json(self, focus: str | None = None) -> dict[str, Any]:
        """``{"nodes": [{id,type,label}], "edges": [{source,target,type}]}``, sorted.

        With ``focus``, only that node, its ancestors and its descendants are kept.
        """
        if focus is None:
            keep = set(self._g.nodes)
        else:
            self._require(focus)
            keep = {focus} | nx.ancestors(self._g, focus) | nx.descendants(self._g, focus)
        nodes = [
            {"id": n, "type": self._g.nodes[n]["type"], "label": self._g.nodes[n]["label"]}
            for n in sorted(keep)
        ]
        edges = sorted(
            (
                {"source": u, "target": v, "type": d["type"]}
                for u, v, d in self._g.edges(data=True)
                if u in keep and v in keep
            ),
            key=lambda e: (e["source"], e["target"], e["type"]),
        )
        return {"nodes": nodes, "edges": edges}
