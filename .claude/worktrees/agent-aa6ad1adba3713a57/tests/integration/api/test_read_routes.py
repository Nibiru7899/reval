"""P6-02: every read route on the mini project, including the 404 paths."""

from fastapi.testclient import TestClient

BASE = "/api/v1/projects/default"


def test_projects(client: TestClient) -> None:
    rows = client.get("/api/v1/projects").json()
    assert [r["id"] for r in rows] == ["default"]
    assert rows[0]["claims"] == 4


def test_snapshots_create_and_list(client: TestClient) -> None:
    created = client.post(f"{BASE}/snapshots")
    assert created.status_code == 201
    sid = created.json()["id"]
    rows = client.get(f"{BASE}/snapshots").json()
    assert rows[0]["id"] == sid and rows[0]["claims"] == 4
    assert client.post(f"{BASE}/snapshots").json()["id"] == sid  # idempotent
    assert client.get(f"{BASE}/snapshots", params={"limit": 1, "offset": 1}).json() == []
    assert client.get(f"{BASE}/snapshots", params={"limit": 0}).status_code == 422


def test_claims_filters_and_paging(client: TestClient) -> None:
    allc = client.get(f"{BASE}/claims").json()
    assert [a["claim_id"] for a in allc] == sorted(a["claim_id"] for a in allc) and len(allc) == 4
    assert {a["status"] for a in allc} == {"inconclusive"}  # no evidence yet: fail closed
    assert client.get(f"{BASE}/claims", params={"status": "violated"}).json() == []
    assert len(client.get(f"{BASE}/claims", params={"limit": 2, "offset": 3}).json()) == 1
    assert client.get(f"{BASE}/claims", params={"status": "bogus"}).status_code == 422
    assert client.get(f"{BASE}/claims", params={"snapshot": "nope"}).status_code == 404


def test_claims_with_evidence(evidenced_client: TestClient) -> None:
    c = evidenced_client
    by_id = {a["claim_id"]: a for a in c.get(f"{BASE}/claims").json()}
    assert by_id["C-S1-TEMP"]["status"] == "supported"
    assert by_id["C-S2-TEMP"]["status"] == "violated"
    viol = c.get(f"{BASE}/claims", params={"status": "violated"}).json()
    assert [a["claim_id"] for a in viol] == ["C-S2-TEMP"]
    one = c.get(f"{BASE}/claims/C-S1-TEMP/assessment").json()
    assert one["status"] == "supported"
    j = c.get(f"{BASE}/claims/C-S1-TEMP/justification").json()
    assert j["claim_id"] == "C-S1-TEMP" and "C-S1-TEMP" in j["text"]
    eid = one["evidence"][0]["evidence_id"]
    ev = c.get(f"{BASE}/evidence/{eid}")
    assert ev.status_code == 200 and ev.json()["id"] == eid


def test_unknown_ids_are_404(evidenced_client: TestClient) -> None:
    c = evidenced_client
    assert c.get(f"{BASE}/claims/NOPE/assessment").status_code == 404
    assert c.get(f"{BASE}/claims/NOPE/justification").status_code == 404
    assert c.get(f"{BASE}/evidence/NOPE").status_code == 404
    assert c.get(f"{BASE}/graph", params={"focus": "claim:NOPE"}).status_code == 404
    assert c.get(f"{BASE}/diff", params={"from": "nope"}).status_code == 404


def test_other_project_is_404_on_every_route(client: TestClient) -> None:
    for path in ("snapshots", "claims", "claims/C/assessment", "evidence/x", "graph", "plans/x", "reports/x"):
        assert client.get(f"/api/v1/projects/other/{path}").status_code == 404, path
    assert client.post("/api/v1/projects/other/snapshots").status_code == 404
    assert client.post("/api/v1/projects/other/plans", json={}).status_code == 404


def test_graph_has_claim_statuses_and_focus(evidenced_client: TestClient) -> None:
    c = evidenced_client
    c.get(f"{BASE}/claims")
    g = c.get(f"{BASE}/graph").json()
    claims = {n["id"]: n for n in g["nodes"] if n["type"] == "claim"}
    assert claims["claim:C-SHAFT"]["status"] == "supported"
    assert all(n["status"] is None for n in g["nodes"] if n["type"] != "claim")
    focused = c.get(f"{BASE}/graph", params={"focus": "claim:C-SHAFT"}).json()
    assert 0 < len(focused["nodes"]) < len(g["nodes"])


def test_diff_between_snapshots(evidenced_client: TestClient, evidenced_root) -> None:  # type: ignore[no-untyped-def]
    c = evidenced_client
    a = c.post(f"{BASE}/snapshots").json()["id"]
    data = evidenced_root / "data" / "data.csv"
    data.write_text(data.read_text(encoding="utf-8").replace("g1,0.0,19.5", "g1,0.0,19.6"), encoding="utf-8")
    same = c.get(f"{BASE}/diff", params={"from": a, "to": a}).json()
    assert same["affected_claims"] == []
    d = c.get(f"{BASE}/diff", params={"from": a}).json()
    assert d["from_snapshot"] == a and d["to_snapshot"] != a
    assert d["changes"]["changes"], "the data edit must show up"
    assert d["affected_claims"]
    assert set(d["after"]) == set(d["before"])
