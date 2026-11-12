"""Evidence policies (docs/03 §3, docs/10-interfaces.md §2)."""

from reval.domain.base import Frozen
from reval.domain.evidence import ProducerKind


class EvidenceRequirement(Frozen):
    kind: ProducerKind
    min_fidelity: int = 0
    in_domain: bool = False
    independent_of: tuple[ProducerKind, ...] = ()


class Policy(Frozen):
    """OR of ANDs: any one clause (1..3 conjuncts) of fresh passing evidence supports the claim."""

    id: str
    alternatives: tuple[tuple[EvidenceRequirement, ...], ...]


_K = ProducerKind

DEFAULT_POLICIES: dict[str, Policy] = {
    "low": Policy(
        id="low",
        alternatives=(
            (EvidenceRequirement(kind=_K.ML_PREDICTION, in_domain=True),),
            (EvidenceRequirement(kind=_K.PHYSICS_SIM),),
            (EvidenceRequirement(kind=_K.MEASUREMENT),),
            (EvidenceRequirement(kind=_K.ANALYTIC),),
        ),
    ),
    "medium": Policy(
        id="medium",
        alternatives=(
            (
                EvidenceRequirement(kind=_K.ML_PREDICTION, in_domain=True),
                EvidenceRequirement(kind=_K.PHYSICS_SIM, independent_of=(_K.ML_PREDICTION,)),
            ),
            (EvidenceRequirement(kind=_K.MEASUREMENT),),
            (EvidenceRequirement(kind=_K.ANALYTIC, min_fidelity=3),),
        ),
    ),
    "high": Policy(
        id="high",
        alternatives=(
            (EvidenceRequirement(kind=_K.MEASUREMENT),),
            (
                EvidenceRequirement(kind=_K.PHYSICS_SIM, min_fidelity=2),
                EvidenceRequirement(kind=_K.ML_PREDICTION, in_domain=True, independent_of=(_K.PHYSICS_SIM,)),
            ),
            (EvidenceRequirement(kind=_K.ANALYTIC, min_fidelity=3),),
        ),
    ),
}
