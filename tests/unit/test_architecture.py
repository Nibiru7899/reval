"""Enforces ADR 0001: the core engines stay pure (no I/O, clock, randomness, network or LLM imports)."""

import ast
from pathlib import Path

import reval.core

FORBIDDEN_TOP_LEVEL = {
    "os", "pathlib", "shutil", "subprocess", "socket", "io", "tempfile",
    "time", "datetime", "random", "uuid",
    "requests", "httpx", "urllib", "aiohttp",
    "sqlalchemy", "sqlite3", "fastapi",
    "anthropic", "openai",
    "reval.store", "reval.api", "reval.cli", "reval.gitio", "reval.services",
}  # fmt: skip


def _imported_modules(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def _is_forbidden(module: str) -> bool:
    return any(module == f or module.startswith(f + ".") for f in FORBIDDEN_TOP_LEVEL)


def test_core_has_no_impure_imports() -> None:
    core_dir = Path(reval.core.__file__).parent
    offenders = {
        f"{py.relative_to(core_dir)}: {mod}"
        for py in core_dir.rglob("*.py")
        for mod in _imported_modules(ast.parse(py.read_text(encoding="utf-8")))
        if _is_forbidden(mod)
    }
    assert not offenders, f"impure imports in reval.core: {sorted(offenders)}"
