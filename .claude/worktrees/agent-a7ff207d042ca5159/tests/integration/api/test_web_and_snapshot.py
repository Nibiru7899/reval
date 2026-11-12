"""P6-06/07: the snapshot detail route the claim board needs, and serving the built SPA."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from reval.api import ApiSettings, create_app

BASE = "/api/v1/projects/default"


def test_snapshot_detail_by_id_and_prefix(client: TestClient) -> None:
    sid = client.post(f"{BASE}/snapshots").json()["id"]
    full = client.get(f"{BASE}/snapshots/{sid}")
    assert full.status_code == 200
    body = full.json()
    assert body["id"] == sid and len(body["claims"]) == 4
    claim = next(iter(body["claims"].values()))
    assert claim["requirement_id"] in body["requirements"]
    assert "criticality" in body["requirements"][claim["requirement_id"]]
    assert client.get(f"{BASE}/snapshots/{sid[:10]}").json()["id"] == sid
    assert client.get(f"{BASE}/snapshots/nope-not-a-rev").status_code == 404


def test_spa_served_when_dist_exists(root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>ReVal</title>", encoding="utf-8")
    (dist / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    monkeypatch.setenv("REVAL_WEB_DIST", str(dist))
    with TestClient(create_app(ApiSettings(project_root=root))) as c:
        assert "ReVal" in c.get("/").text
        assert c.get("/assets/app.js").text == "console.log(1)"
        assert "ReVal" in c.get("/claims/C-S1-TEMP").text  # client-side route falls back to index.html
        assert c.get("/api/v1/health").json()["status"] == "ok"
        assert c.get("/api/v1/nope").status_code == 404  # API 404s are not swallowed by the SPA


def test_no_spa_without_dist(root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REVAL_WEB_DIST", str(tmp_path / "missing"))
    with TestClient(create_app(ApiSettings(project_root=root))) as c:
        assert c.get("/").status_code == 404
