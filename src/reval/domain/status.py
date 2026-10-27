"""Status vocabulary.

Meaning: docs/03-domain-model.md §2-§6; shapes: docs/10-interfaces.md §2. Change all three together.
"""

from enum import StrEnum


class Verdict(StrEnum):
    """Three-valued outcome of one evidence item against one requirement."""

    PASS = "pass"
    FAIL = "fail"
    INCONCLUSIVE = "inconclusive"


class Status(StrEnum):
    """Claim status.

    Declaration order is NOT the evaluation order; the rules (VIOLATED → WAIVED → STALE (lost fail)
    → SUPPORTED → STALE → INCONCLUSIVE) are in docs/03-domain-model.md §3.
    """

    VIOLATED = "violated"
    WAIVED = "waived"
    SUPPORTED = "supported"
    STALE = "stale"
    INCONCLUSIVE = "inconclusive"


# Only these count as "accepted" (UAR in benchmark metrics; benchmarks contain no waivers).
ACCEPTED_STATUSES: frozenset[Status] = frozenset({Status.SUPPORTED, Status.WAIVED})


class FreshnessClass(StrEnum):
    """How an evidence item recorded at snapshot S relates to snapshot S'."""

    FRESH_EXACT = "fresh_exact"
    FRESH_OUT_OF_SCOPE = "fresh_out_of_scope"
    CARRY_FORWARD = "carry_forward"
    INVALIDATED = "invalidated"


class ReasonCode(StrEnum):
    """Machine-readable reasons; table with meanings in docs/03-domain-model.md §6."""

    POLICY_SATISFIED = "policy_satisfied"
    WAIVER_APPLIED = "waiver_applied"
    REQUIREMENT_VIOLATED = "requirement_violated"
    CONFLICTING_EVIDENCE = "conflicting_evidence"
    NO_EVIDENCE = "no_evidence"
    OUT_OF_DOMAIN = "out_of_domain"
    MARGIN_BELOW_UNCERTAINTY = "margin_below_uncertainty"
    POLICY_UNMET = "policy_unmet"
    EVIDENCE_INVALIDATED = "evidence_invalidated"
    UNKNOWN_CHANGE = "unknown_change"
    MISSING_TOLERANCE = "missing_tolerance"
    REQUIREMENT_CHANGED = "requirement_changed"
