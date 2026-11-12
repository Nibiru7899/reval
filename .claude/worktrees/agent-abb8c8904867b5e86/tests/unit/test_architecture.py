"""Enforces ADR 0001: the core engines stay pure (no I/O, clock, randomness, network or LLM imports)."""

import ast
from pathlib import Path

import reval
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


def _offending_bench_imports(root: Path) -> set[str]:
    return {
        f"{py.relative_to(root)}: {mod}"
        for py in root.rglob("*.py")
        for mod in _imported_modules(ast.parse(py.read_text(encoding="utf-8")))
        if mod == "bench" or mod.startswith("bench.")
    }


def test_reval_and_motor_never_import_bench() -> None:
    """Benchmark code may import the product, never the reverse (docs/tasks/phase-5-bench.md)."""
    import motor

    for pkg_file in (reval.__file__, motor.__file__):
        assert pkg_file is not None
        offenders = _offending_bench_imports(Path(pkg_file).parent)
        assert not offenders, f"product code imports bench: {sorted(offenders)}"


def test_bench_import_detector_flags_offenders(tmp_path: Path) -> None:
    (tmp_path / "bad.py").write_text("from bench.world import World\nimport bench\n", encoding="utf-8")
    (tmp_path / "ok.py").write_text("import benchmark_helpers\n", encoding="utf-8")
    assert len(_offending_bench_imports(tmp_path)) == 2
