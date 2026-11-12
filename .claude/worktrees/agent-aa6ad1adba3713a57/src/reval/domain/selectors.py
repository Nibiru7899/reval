"""Dependency selectors (docs/10-interfaces.md §1.4).

Grammar: ``art`` | ``art#/json/pointer`` | ``art[col1,col2]``. ``selector_hash`` lives in core.
"""

import re
from typing import Self

from pydantic import field_validator, model_validator

from reval.domain.base import Frozen
from reval.errors import ManifestError

_ID = r"[A-Za-z0-9_][A-Za-z0-9_.\-]*"
_WHOLE = re.compile(rf"^({_ID})$")
_POINTER = re.compile(rf"^({_ID})#(/.*)$")
_COLUMNS = re.compile(rf"^({_ID})\[([^\[\]]*)\]$")


def _segments(pointer: str) -> list[str]:
    return pointer.split("/")[1:]


class Selector(Frozen):
    """A reference to a whole artifact, a params subtree, or dataset columns."""

    artifact_id: str
    pointer: str | None = None
    columns: tuple[str, ...] = ()

    @field_validator("columns")
    @classmethod
    def _canonical_columns(cls, v: tuple[str, ...]) -> tuple[str, ...]:
        if any(not c.strip() or "," in c or c != c.strip() for c in v):
            raise ValueError("column names must be non-empty, trimmed and comma-free")
        return tuple(sorted(set(v)))

    @model_validator(mode="after")
    def _check_form(self) -> Self:
        if not self.artifact_id:
            raise ValueError("artifact_id must be non-empty")
        if self.pointer is not None and self.columns:
            raise ValueError("a selector has a pointer or columns, not both")
        if self.pointer is not None and not self.pointer.startswith("/"):
            raise ValueError("pointer must start with '/'")
        return self

    @classmethod
    def parse(cls, text: str) -> "Selector":
        """Parse ``art``, ``art#/ptr`` or ``art[c1,c2]``; raises ManifestError on bad syntax."""
        if (m := _WHOLE.match(text)) is not None:
            return cls(artifact_id=m.group(1))
        if (m := _POINTER.match(text)) is not None:
            ptr = m.group(2)
            if ptr.endswith("/") or "//" in ptr:
                raise ManifestError(f"invalid selector {text!r}: empty pointer segment")
            return cls(artifact_id=m.group(1), pointer=ptr)
        if (m := _COLUMNS.match(text)) is not None:
            cols = tuple(c.strip() for c in m.group(2).split(","))
            if not m.group(2).strip() or any(not c for c in cols):
                raise ManifestError(f"invalid selector {text!r}: empty column name")
            try:
                return cls(artifact_id=m.group(1), columns=cols)
            except ValueError as exc:
                raise ManifestError(f"invalid selector {text!r}: {exc}") from exc
        raise ManifestError(f"invalid selector syntax: {text!r}")

    def render(self) -> str:
        """Canonical text form (columns sorted); inverse of ``parse``."""
        if self.pointer is not None:
            return f"{self.artifact_id}#{self.pointer}"
        if self.columns:
            return f"{self.artifact_id}[{','.join(self.columns)}]"
        return self.artifact_id

    @property
    def is_whole(self) -> bool:
        """True when neither a pointer nor columns narrow the artifact."""
        return self.pointer is None and not self.columns

    def covers(self, other: "Selector") -> bool:
        """Symmetric overlap test; pointer prefixes are compared segment-wise."""
        if self.artifact_id != other.artifact_id:
            return False
        if self.is_whole or other.is_whole:
            return True
        if self.pointer is not None and other.pointer is not None:
            a, b = _segments(self.pointer), _segments(other.pointer)
            n = min(len(a), len(b))
            return a[:n] == b[:n]
        if self.columns and other.columns:
            return bool(set(self.columns) & set(other.columns))
        return False
