"""P6-04: report build and the three formats."""

from fastapi.testclient import TestClient

from reval.report import DISCLAIMER

BASE = "/api/v1/projects/default"


def test_report_formats(evidenced_client: TestClient) -> None:
    c = evidenced_client
    r = c.post(f"{BASE}/reports", json={})
    assert r.status_code == 201
    rep = r.json()
    rid = rep["report_id"]

    j = c.get(f"{BASE}/reports/{rid}")
    assert j.status_code == 200 and j.json()["report_hash"] == rep["report_hash"]
    html = c.get(f"{BASE}/reports/{rid}", params={"format": "html"})
    assert html.headers["content-type"].startswith("text/html") and DISCLAIMER in html.text
    md = c.get(f"{BASE}/reports/{rid}", params={"format": "md"})
    assert md.headers["content-type"].startswith("text/markdown") and DISCLAIMER in md.text


def test_same_state_same_report_id(evidenced_client: TestClient) -> None:
    c = evidenced_client
    a = c.post(f"{BASE}/reports", json={}).json()
    b = c.post(f"{BASE}/reports", json={}).json()
    assert a["report_id"] == b["report_id"]


def test_report_errors(evidenced_client: TestClient) -> None:
    c = evidenced_client
    assert c.get(f"{BASE}/reports/nope").status_code == 404
    assert c.get(f"{BASE}/reports/nope", params={"format": "pdf"}).status_code == 422
    assert c.post(f"{BASE}/reports", json={"snapshot": "nope"}).status_code == 404
