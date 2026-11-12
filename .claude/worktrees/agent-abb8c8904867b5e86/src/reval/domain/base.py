"""Base class for every domain object (docs/10-interfaces.md §1.1)."""

from pydantic import BaseModel, ConfigDict


class Frozen(BaseModel):
    """Immutable, strict model. Unknown fields are rejected so typos fail loudly (fail closed)."""

    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=False)
