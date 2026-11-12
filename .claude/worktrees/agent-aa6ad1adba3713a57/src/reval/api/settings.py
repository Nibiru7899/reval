"""API settings. D27: one project, whose root comes from ``REVAL_PROJECT_ROOT`` (default: cwd)."""

import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_ID = "default"


@dataclass(frozen=True)
class ApiSettings:
    project_root: Path

    @classmethod
    def from_env(cls) -> "ApiSettings":
        return cls(project_root=Path(os.environ.get("REVAL_PROJECT_ROOT") or ".").resolve())
