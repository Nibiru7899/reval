"""Producer SDK: decorator, registry, context, output helpers."""

from reval.domain.engineering import Subject
from reval.domain.evidence import ProducerKind
from reval.sdk.context import Context
from reval.sdk.output import ProducerOutput, exact_result, interval_result
from reval.sdk.producer import ProducerFn, producer
from reval.sdk.registry import DEFAULT_REGISTRY, ProducerRegistry, RegisteredProducer, code_hash

__all__ = [
    "DEFAULT_REGISTRY",
    "Context",
    "ProducerFn",
    "ProducerKind",
    "ProducerOutput",
    "ProducerRegistry",
    "RegisteredProducer",
    "Subject",
    "code_hash",
    "exact_result",
    "interval_result",
    "producer",
]
