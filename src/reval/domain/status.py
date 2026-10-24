"""Status vocabulary. Mirrors docs/03-domain-model.md sections 2-4; change both together."""

from enum import StrEnum


class Verdict(StrEnum):
    """Three-valued outcome of one fresh evidence item against one requirement."""

    PASS = "pass"
    FAIL = "fail"
    INCONCLUSIVE = "inconclusive"


class Status(StrEnum):
    """Claim status. Evaluation order (first match wins) is the declaration order below."""

    VIOLATED = "violated"
    WAIVED = "waived"
    SUPPORTED = "supported"
    STALE = "stale"
    INCONCLUSIVE = "inconclusive"


# Only these count as "accepted" in benchmark metrics (UAR).
ACCEPTED_STATUSES: frozenset[Status] = frozenset({Status.SUPPORTED, Status.WAIVED})


class FreshnessClass(StrEnum):
    """How an evidence item recorded at snapshot S relates to snapshot S'."""

    FRESH_EXACT = "fresh_exact"
    FRESH_OUT_OF_SCOPE = "fresh_out_of_scope"
    CARRY_FORWARD = "carry_forward"
    INVALIDATED = "invalidated"


class ReasonCode(StrEnum):
    CONFLICTING_EVIDENCE = "conflicting_evidence"
    NO_EVIDENCE = "no_evidence"
    OUT_OF_DOMAIN = "out_of_domain"
    MARGIN_BELOW_UNCERTAINTY = "margin_below_uncertainty"
    POLICY_UNMET = "policy_unmet"
    EVIDENCE_INVALIDATED = "evidence_invalidated"
    UNKNOWN_CHANGE = "unknown_change"
    MISSING_TOLERANCE = "missing_tolerance"
    REQUIREMENT_CHANGED = "requirement_changed"
