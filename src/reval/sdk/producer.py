"""The ``@producer`` decorator (docs/10 §7)."""

from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING

from reval.domain.engineering import Subject
from reval.domain.evidence import DEFAULT_FIDELITY, Producer, ProducerKind
from reval.domain.selectors import Selector
from reval.sdk.registry import DEFAULT_REGISTRY, PLACEHOLDER_CODE_HASH, ProducerRegistry, RegisteredProducer

if TYPE_CHECKING:
    from reval.sdk.context import Context
    from reval.sdk.output import ProducerOutput

ProducerFn = Callable[[Subject, "Context"], "ProducerOutput"]


def producer(
    *,
    kind: ProducerKind | str,
    quantity: str | Sequence[str],
    cost: float,
    fidelity: int | None = None,
    depends_on: Sequence[str] = (),
    assumes: Sequence[str] = (),
    predictors: Sequence[str] = (),
    available_for: Callable[[Subject], bool] | None = None,
    id: str | None = None,
    registry: ProducerRegistry | None = None,
) -> Callable[[ProducerFn], ProducerFn]:
    """Register ``fn(subject, ctx) -> ProducerOutput`` as an evidence producer.

    Raises ValueError at decoration time for bad metadata (e.g. a predictor that is not a dependency).
    """
    pkind = ProducerKind(kind)
    quantities = (quantity,) if isinstance(quantity, str) else tuple(quantity)
    target = DEFAULT_REGISTRY if registry is None else registry

    def decorate(fn: ProducerFn) -> ProducerFn:
        rendered = tuple(sorted({Selector.parse(s).render() for s in depends_on}))
        meta = Producer(
            id=id if id is not None else f"{fn.__module__}:{fn.__name__}",
            kind=pkind,
            quantities=quantities,
            fidelity=DEFAULT_FIDELITY[pkind] if fidelity is None else fidelity,
            cost=cost,
            code_hash=PLACEHOLDER_CODE_HASH,
            depends_on=rendered,
            assumes=tuple(sorted(set(assumes))),
            predictors=tuple(sorted(set(predictors))),
        )
        target.register(RegisteredProducer(meta=meta, fn=fn, available_for=available_for))
        return fn

    return decorate
