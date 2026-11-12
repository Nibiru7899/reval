"""Throwaway git clones of a project in which a scenario's change is committed (docs/06 section 2).

The user's repository is only ever read (``git clone --local``); every edit happens in the clone.
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

# Fixed identity and dates make commit hashes a pure function of (tree, parent, message).
GIT_ENV = {
    "GIT_AUTHOR_NAME": "ReValBench",
    "GIT_AUTHOR_EMAIL": "bench@reval.invalid",
    "GIT_COMMITTER_NAME": "ReValBench",
    "GIT_COMMITTER_EMAIL": "bench@reval.invalid",
    "GIT_AUTHOR_DATE": "2000-01-01T00:00:00+00:00",
    "GIT_COMMITTER_DATE": "2000-01-01T00:00:00+00:00",
}
# reval.cli.main has no __main__ guard, so `python -m reval.cli.main` would exit silently.
_CLI = "from reval.cli.main import app; app()"
_UNTRACKED_DIRS = ("data", "models")


def _git(cwd: Path, *args: str) -> str:
    env = {**os.environ, **GIT_ENV}
    proc = subprocess.run(
        ["git", "-c", "core.autocrlf=false", "-c", "commit.gpgsign=false", *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed in {cwd}: {proc.stderr.strip()}")
    return proc.stdout.strip()


def _link_or_copy(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(src, dst)
    except OSError:  # different volume or no hardlink support
        shutil.copy2(src, dst)


def _copy_tree(src: Path, dst: Path) -> None:
    for f in sorted(src.rglob("*")):
        if f.is_file():
            target = dst / f.relative_to(src)
            if not target.exists():  # tracked files already came with the clone
                _link_or_copy(f, target)


@dataclass
class Workspace:
    """A clone of ``base_repo`` under ``tmp_root/<scenario_id>``; ``root`` is the project dir inside it."""

    clone: Path
    root: Path

    @classmethod
    def create(
        cls,
        base_repo: Path,
        tmp_root: Path,
        data_cache: Path | None = None,
        *,
        scenario_id: str = "ws",
        project_subdir: str = ".",
    ) -> Workspace:
        """Clone ``base_repo`` and hardlink the git-ignored ``data/`` and ``models/`` in.

        ``data_cache`` is a directory holding ``data/`` and ``models/`` (default: the project directory of
        ``base_repo``). Hardlinked files share storage with the cache, so an applier must call
        :meth:`detach` before rewriting one in place.
        """
        base_repo = Path(base_repo).resolve()
        clone = Path(tmp_root).resolve() / scenario_id
        if clone.exists():
            raise FileExistsError(f"workspace {clone} already exists")
        clone.parent.mkdir(parents=True, exist_ok=True)
        _git(clone.parent, "clone", "--local", "--quiet", str(base_repo), str(clone))
        root = (clone / project_subdir).resolve()
        cache = Path(data_cache) if data_cache is not None else base_repo / project_subdir
        for name in _UNTRACKED_DIRS:
            if (cache / name).is_dir():
                _copy_tree(cache / name, root / name)
        return cls(clone, root)

    def detach(self, relpath: str | Path) -> None:
        """Replace a (possibly hardlinked) file by a private copy so it can be modified in place."""
        path = self.root / relpath
        tmp = path.with_name(path.name + ".detach")
        shutil.copy2(path, tmp)
        path.chmod(path.stat().st_mode | stat.S_IWRITE)
        os.replace(tmp, path)

    def commit(self, message: str, *, lock: bool = True) -> str:
        """Write ``reval.lock.json`` (``reval diff`` needs a lock per revision), commit, return the revision.

        Everything not git-ignored is staged; empty commits are allowed (a T9 scenario changes no file).
        """
        if lock:
            self.run_reval(["snapshot", "--write"], check=True)
        _git(self.clone, "add", "-A")
        _git(self.clone, "commit", "--quiet", "--allow-empty", "-m", message)
        return self.head()

    def head(self) -> str:
        return _git(self.clone, "rev-parse", "HEAD")

    def run_reval(self, args: list[str], *, check: bool = False) -> subprocess.CompletedProcess[str]:
        """Run the reval CLI in the project directory of this workspace."""
        proc = subprocess.run(
            [sys.executable, "-c", _CLI, *args],
            cwd=self.root,
            capture_output=True,
            text=True,
            check=False,
        )
        if check and proc.returncode != 0:
            raise RuntimeError(f"reval {' '.join(args)} failed: {proc.stderr.strip() or proc.stdout.strip()}")
        return proc

    def cleanup(self) -> None:
        """Delete the clone (read-only git objects included)."""

        def _writable(func, path, _exc):  # type: ignore[no-untyped-def]
            os.chmod(path, stat.S_IWRITE)
            func(path)

        shutil.rmtree(self.clone, onexc=_writable)
