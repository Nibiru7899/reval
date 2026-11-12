"""P6-01: app skeleton, health, OpenAPI."""

from fastapi.testclient import TestClient

from reval import __version__


def test_health(client: TestClient) -> None:
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "version": __version__}


def test_openapi_is_v3_with_clean_operation_ids(client: TestClient) -> None:
    spec = client.get("/api/v1/openapi.json").json()
    assert spec["openapi"].startswith("3.")
    ops = {op["operationId"] for path in spec["paths"].values() for op in path.values()}
    assert {"health", "list_claims", "create_plan", "execute_plan", "stream_job_events", "get_report"} <= ops
    assert not any("_api_v1_" in o for o in ops)


def test_unknown_project_is_404(client: TestClient) -> None:
    assert client.get("/api/v1/projects/other/claims").status_code == 404
