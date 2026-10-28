# Python API reference

Generated from the source docstrings with mkdocstrings. The binding signatures are specified in [10 Interfaces](../10-interfaces.md); the
contract for the entities is [03 Domain model](../03-domain-model.md).

!!! note "Stability"
    ReVal is at version 0.0.x. The producer SDK (`reval.sdk`, re-exported from `reval`) is the surface intended for users; `reval.domain` and `reval.core`
    are documented because they define the vocabulary and the engines, and may still change.

## Producer SDK: `reval.sdk`

```python
import reval
from reval import producer, Context, ProducerKind, ProducerOutput, Subject, interval_result, exact_result
```

::: reval.sdk.producer
    options:
      members: [producer]

::: reval.sdk.context
    options:
      members: [Context]

::: reval.sdk.output

## Domain model: `reval.domain`

Frozen Pydantic models. Names follow the domain model exactly.

::: reval.domain.engineering

::: reval.domain.evidence

::: reval.domain.status

::: reval.domain.assessment

::: reval.domain.policies

::: reval.domain.changes

::: reval.domain.plan

::: reval.domain.snapshot

::: reval.domain.artifacts

::: reval.domain.quantities

::: reval.domain.selectors

## Pure engines: `reval.core`

No I/O, no clocks, no unseeded randomness.

::: reval.core.graph

::: reval.core.diff

::: reval.core.freshness

::: reval.core.verdicts

::: reval.core.status

::: reval.core.planner
