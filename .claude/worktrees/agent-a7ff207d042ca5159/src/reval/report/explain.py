"""`reval explain CLAIM`: a deterministic ASCII justification tree (docs/09). No colour, icons or clock."""

from collections.abc import Mapping
from dataclasses import dataclass, field

from reval.domain import Assessment, Evidence, EvidenceRequirement, Snapshot


@dataclass
class _Node:
    text: str
    children: list["_Node"] = field(default_factory=list)


def _num(x: float | None) -> str:
    return "-" if x is None else f"{x:g}"


def _requirement_text(r: EvidenceRequirement) -> str:
    parts = [r.kind.value]
    if r.min_fidelity:
        parts.append(f"fidelity>={r.min_fidelity}")
    if r.in_domain:
        parts.append("in domain")
    if r.independent_of:
        parts.append("independent of " + "/".join(k.value for k in r.independent_of))
    return " ".join(parts[:1]) + (" (" + ", ".join(parts[1:]) + ")" if len(parts) > 1 else "")


def _render(node: _Node, prefix: str, last: bool, root: bool, out: list[str]) -> None:
    if root:
        out.append(node.text)
        child_prefix = ""
    else:
        out.append(prefix + ("`-- " if last else "|-- ") + node.text)
        child_prefix = prefix + ("    " if last else "|   ")
    for i, child in enumerate(node.children):
        _render(child, child_prefix, i == len(node.children) - 1, False, out)


def explain_claim(
    snap: Snapshot, assessment: Assessment, evidence: Mapping[str, Evidence], claim_id: str
) -> str:
    """Claim, status, reasons, satisfied or failed clauses, evidence and its dependencies, as text."""
    claim = snap.claims[claim_id]
    req = snap.requirements[claim.requirement_id]
    policy = snap.policy_for(claim_id)
    root = _Node(
        f"{claim_id}: {assessment.status.value.upper()}  "
        f"[{req.id}: {req.quantity} {req.op.value} {_num(req.limit)} {req.unit}; "
        f"criticality {req.criticality.value}; subject {claim.subject_id}]"
    )

    reasons = _Node("reasons")
    for r in assessment.reasons:
        node = _Node(f"{r.code.value}: {r.message}")
        if r.evidence_ids:
            node.children.append(_Node("evidence: " + ", ".join(e[:12] for e in r.evidence_ids)))
        reasons.children.append(node)
    if not reasons.children:
        reasons.children.append(_Node("(none)"))
    root.children.append(reasons)

    clauses = _Node(f"clauses (policy {policy.id})")
    for i, alt in enumerate(policy.alternatives):
        state = "satisfied" if assessment.satisfied_clause == i else "not satisfied"
        clauses.children.append(
            _Node(f"clause {i} [{state}]: " + " AND ".join(_requirement_text(r) for r in alt))
        )
    root.children.append(clauses)

    ev_node = _Node("evidence")
    for use in sorted(assessment.evidence, key=lambda u: u.evidence_id):
        ev = evidence.get(use.evidence_id) or evidence.get(use.derived_from_evidence or "")
        producer = f"{ev.producer_id} ({ev.producer_kind.value})" if ev is not None else "unknown producer"
        interval = (
            f"[{_num(use.interval_used.lo)}, {_num(use.interval_used.hi)}] {use.interval_used.unit}"
            if use.interval_used is not None
            else "-"
        )
        recorded = use.recorded_verdict.value if use.recorded_verdict is not None else "-"
        item = _Node(
            f"{use.evidence_id[:12]} {producer}: verdict {use.verdict.value}, recorded {recorded}, "
            f"freshness {use.freshness.value}, interval {interval}"
            + (", used in satisfied clause" if use.used_in_clause else "")
        )
        if use.derived_from_evidence:
            item.children.append(_Node(f"carried forward from {use.derived_from_evidence[:12]}"))
        if ev is not None:
            deps = _Node("dependencies")
            deps.children = [
                _Node(f"{d.selector}@{d.version_hash[:8]}") for d in sorted(ev.deps, key=lambda d: d.selector)
            ] or [_Node("(none)")]
            item.children.append(deps)
        ev_node.children.append(item)
    if not ev_node.children:
        ev_node.children.append(_Node("(none recorded for this claim)"))
    root.children.append(ev_node)

    out: list[str] = []
    _render(root, "", True, True, out)
    return "\n".join(out) + "\n"
