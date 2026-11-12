"""Read-only git access (docs/10 §9). Always an argument list, never a shell."""

import subprocess
from pathlib import Path

from reval.domain.snapshot import Snapshot
from reval.errors import GitError, LockNotFoundError
from reval.gitio.lockfile import LOCK_FILE, parse_lock


def _git(repo_root: Path, *args: str) -> bytes:
    try:
        proc = subprocess.run(["git", "-C", str(repo_root), *args], capture_output=True, check=False)
    except OSError as exc:
        raise GitError(f"cannot run git: {exc}") from exc
    if proc.returncode != 0:
        stderr = proc.stderr.decode("utf-8", errors="replace").strip()
        raise GitError(f"git {' '.join(args)} failed: {stderr}")
    return proc.stdout


def resolve_rev(repo_root: Path, rev: str) -> str:
    """Full commit sha of ``rev`` (``git rev-parse``)."""
    if rev.startswith("-"):  # never let a revision be parsed as an option
        raise GitError(f"invalid revision {rev!r}")
    out = _git(repo_root, "rev-parse", "--verify", "--end-of-options", f"{rev}^{{commit}}")
    return out.decode("utf-8").strip()


def read_file_at_rev(repo_root: Path, rev: str, rel_path: str) -> bytes:
    """Bytes of ``rel_path`` at ``rev`` (``git show rev:path``); a nonzero exit raises GitError."""
    if rev.startswith("-"):
        raise GitError(f"invalid revision {rev!r}")
    return _git(repo_root, "show", f"{rev}:{rel_path.replace(chr(92), '/')}")


def snapshot_at_rev(repo_root: Path, rev: str, project_subdir: str = ".") -> Snapshot:
    """The committed lock at ``rev``, with ``git_rev`` set to the resolved sha (the id is unchanged)."""
    sha = resolve_rev(repo_root, rev)
    sub = project_subdir.replace("\\", "/").strip("/")
    rel = LOCK_FILE if sub in ("", ".") else f"{sub}/{LOCK_FILE}"
    try:
        data = read_file_at_rev(repo_root, sha, rel)
    except GitError as exc:
        raise LockNotFoundError(f"no {LOCK_FILE} at revision {rev}: {exc}") from exc
    return parse_lock(data, f"{rev}:{rel}").model_copy(update={"git_rev": sha})


def repo_subdir(project_root: Path) -> tuple[Path, str]:
    """(repository top level, project path relative to it with forward slashes; ``.`` at the top)."""
    top = Path(_git(project_root, "rev-parse", "--show-toplevel").decode("utf-8").strip())
    try:
        rel = project_root.resolve().relative_to(top.resolve())
    except ValueError as exc:
        raise GitError(f"{project_root} is not inside the repository at {top}") from exc
    return top, rel.as_posix()
