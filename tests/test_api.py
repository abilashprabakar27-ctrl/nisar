import time

import pytest
from fastapi.testclient import TestClient

from api import cache
from api.app import app

SMALL = [-91.2, 29.1, -91.0, 29.25]          # ~19 x 17 km
BIG = [-91.5, 29.0, -90.5, 30.0]             # ~85 x 111 km
ANALYZE = {
    "bbox": SMALL,
    "before_start": "2026-03-01", "before_end": "2026-03-31",
    "after_start": "2026-09-01", "after_end": "2026-09-30",
    "question": "Where did water appear?",
}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("NISAR_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("NISAR_CATALOG_DIR", str(tmp_path / "catalog"))
    return TestClient(app)


def _wait_done(client, job_id, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        body = client.get(f"/jobs/{job_id}").json()
        if body["status"] in ("done", "error"):
            return body
        time.sleep(0.05)
    raise AssertionError("job did not finish")


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_analyze_poll_result_is_sample(client):
    r = client.post("/analyze", json=ANALYZE)
    assert r.status_code == 200
    job = _wait_done(client, r.json()["job_id"])
    assert job["status"] == "done"
    result = client.get(f"/results/{job['job_id']}").json()
    assert result["source"] == "sample"
    assert result["status"] == "ok"
    assert "Sample data - not live" in result["limits"]


def test_repeated_request_is_cached(client, tmp_path):
    first = _wait_done(client, client.post("/analyze", json=ANALYZE).json()["job_id"])
    assert first["status"] == "done"
    second = client.post("/analyze", json=ANALYZE).json()["job_id"]
    job = client.get(f"/jobs/{second}").json()
    assert job["status"] == "done" and job["step"] == "saved"
    result = client.get(f"/results/{second}").json()
    assert result["source"] == "sample"
    key = cache.make_key(SMALL, ["2026-03-01", "2026-03-31"], ["2026-09-01", "2026-09-30"],
                         ANALYZE["question"])
    assert (tmp_path / "cache" / f"{key}.json").exists()


def test_oversized_area_is_422(client):
    r = client.post("/analyze", json={**ANALYZE, "bbox": BIG})
    assert r.status_code == 422
    assert "25 x 25 km" in r.json()["detail"]


def test_unknown_job_is_404(client):
    assert client.get("/jobs/does-not-exist").status_code == 404
    assert client.get("/results/does-not-exist").status_code == 404
