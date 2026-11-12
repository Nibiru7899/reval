"""P6-03: plans, background execution, polling and SSE."""

import json
import time

from fastapi.testclient import TestClient

BASE = "/api/v1/projects/default"


def _wait(c: TestClient, job_id: str, timeout: float = 30.0) -> dict:  # type: ignore[type-arg]
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        job = c.get(f"/api/v1/jobs/{job_id}").json()
        if job["state"] in ("succeeded", "failed"):
            return job  # type: ignore[no-any-return]
        time.sleep(0.05)
    raise AssertionError("job did not finish")


def test_plan_execute_and_poll(stale_client: TestClient) -> None:
    c = stale_client
    r = c.post(f"{BASE}/plans", json={"planner": "ilp"})
    assert r.status_code == 201
    plan = r.json()
    assert plan["runs"], "the data edit makes claims stale"
    assert c.get(f"{BASE}/plans/{plan['id']}").json()["id"] == plan["id"]

    ex = c.post(f"{BASE}/plans/{plan['id']}/execute")
    assert ex.status_code == 202
    job = _wait(c, ex.json()["job_id"])
    assert job["state"] == "succeeded", job
    assert job["result"]["failed_runs"] == 0 and job["result"]["evidence_ids"]
    # executing restored support: nothing is stale any more
    statuses = {a["claim_id"]: a["status"] for a in c.get(f"{BASE}/claims").json()}
    assert "stale" not in statuses.values()


def test_budget_plan_and_errors(stale_client: TestClient) -> None:
    c = stale_client
    assert c.post(f"{BASE}/plans", json={"budget": 0}).status_code == 201
    assert c.post(f"{BASE}/plans", json={"planner": "bogus"}).status_code == 422
    assert c.get(f"{BASE}/plans/nope").status_code == 404
    assert c.post(f"{BASE}/plans/nope/execute").status_code == 404
    assert c.get("/api/v1/jobs/nope").status_code == 404
    assert c.get("/api/v1/jobs/nope/events").status_code == 404


def test_execute_rejects_plan_for_another_snapshot(stale_client: TestClient, evidenced_root) -> None:  # type: ignore[no-untyped-def]
    c = stale_client
    plan = c.post(f"{BASE}/plans", json={}).json()
    data = evidenced_root / "data" / "data.csv"
    data.write_text(data.read_text(encoding="utf-8").replace("g1,0.1,", "g1,0.1,9", 1), encoding="utf-8")
    assert c.post(f"{BASE}/plans/{plan['id']}/execute").status_code == 409


def test_sse_stream_ends_with_done(stale_client: TestClient) -> None:
    c = stale_client
    plan = c.post(f"{BASE}/plans", json={}).json()
    job_id = c.post(f"{BASE}/plans/{plan['id']}/execute").json()["job_id"]
    events: list[tuple[str, dict]] = []  # type: ignore[type-arg]
    with c.stream("GET", f"/api/v1/jobs/{job_id}/events") as resp:
        assert resp.headers["content-type"].startswith("text/event-stream")
        name = ""
        for line in resp.iter_lines():
            if line.startswith("event: "):
                name = line.removeprefix("event: ")
            elif line.startswith("data: "):
                events.append((name, json.loads(line.removeprefix("data: "))))
    names = [n for n, _ in events]
    assert names[0] == "state" and names[-1] == "done"
    assert events[-1][1]["state"] == "succeeded"
