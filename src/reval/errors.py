"""Error hierarchy (docs/10 §13). The CLI maps every RevalError to exit code 3; anything else is a bug."""

from os import PathLike


class RevalError(Exception):
    """Base class for expected, user-facing ReVal errors."""


class ManifestError(RevalError):
    """Invalid reval.yaml content: message plus optional file ``path`` and ``location``."""

    def __init__(
        self, message: str, *, path: "str | PathLike[str] | None" = None, location: str | None = None
    ) -> None:
        self.message = message
        self.path = None if path is None else str(path)
        self.location = location
        prefix = ""
        if self.path:
            prefix += f"{self.path}: "
        if location:
            prefix += f"{location}: "
        super().__init__(prefix + message)


class UndeclaredDependencyError(RevalError):
    """A producer read an artifact or field it did not declare."""


class ProducerError(RevalError):
    """A producer failed or returned an invalid result."""


class MissingExtraError(RevalError):
    """An optional dependency group is not installed."""

    def __init__(self, extra: str) -> None:
        self.extra = extra
        super().__init__(f'missing optional dependencies; install them with: pip install "reval[{extra}]"')


class GitError(RevalError):
    """A git operation failed."""


class LockNotFoundError(GitError):
    """No reval.lock.json exists at the requested revision or path."""


class StoreError(RevalError):
    """The evidence store is inconsistent or unavailable."""


class SchemaError(RevalError):
    """Motor data does not match the expected schema."""
