"""P6-01/06: `reval api-schema` and `reval serve` wiring."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from reval.cli.main import app

runner = CliRunner()


def test_api_schema_writes_openapi(tmp_path: Path) -> None:
    out = tmp_path / "sub" / "openapi.json"
    r = runner.invoke(app, ["api-schema", "--out", str(out)])
    assert r.exit_code == 0, r.output
    spec = json.loads(out.read_text(encoding="utf-8"))
    assert spec["openapi"].startswith("3.") and "/api/v1/health" in spec["paths"]
    # deterministic: a second run gives byte-identical output
    first = out.read_bytes()
    runner.invoke(app, ["api-schema", "--out", str(out)])
    assert out.read_bytes() == first


def test_serve_passes_host_port_and_root(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import uvicorn

    seen: dict[str, object] = {}
    monkeypatch.setattr(uvicorn, "run", lambda a, **kw: seen.update(app=a, **kw))
    r = runner.invoke(app, ["serve", "--project", str(root), "--port", "9123"])
    assert r.exit_code == 0, r.output
    assert seen["host"] == "127.0.0.1" and seen["port"] == 9123
