"""ReVal: continuous validation engine for engineering decisions."""

from reval.domain.engineering import Subject
from reval.domain.evidence import ProducerKind
from reval.sdk import Context, ProducerOutput, exact_result, interval_result, producer

__version__ = "0.0.1"

__all__ = [
    "Context",
    "ProducerKind",
    "ProducerOutput",
    "Subject",
    "__version__",
    "exact_result",
    "interval_result",
    "producer",
]
