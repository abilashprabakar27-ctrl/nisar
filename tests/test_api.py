import json
import time

import pytest
from fastapi.testclient import TestClient

from api import app as app_mod, cache, jobs
from api.app import app
from api.schemas import validate_result

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
    app_mod._places.clear()
    return TestClient(app)


def _wait_done(client, job_id, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = client.get(f"/analyses/{job_id}")
        if r.status_code == 200 or r.json().get("status") == "error":
            return r
        time.sleep(0.05)
    raise AssertionError("job did not finish")


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_cors(client):
    r = client.get("/health", headers={"Origin": "http://x.test"})
    assert r.headers["access-control-allow-origin"] == "*"


def test_places_cached_and_user_agent(client, monkeypatch):
    calls = []

    def fake(q):
        calls.append(q)
        return [{"display_name": "Baton Rouge", "lat": "30.4", "lon": "-91.1",
                 "boundingbox": ["30.3", "30.5", "-91.2", "-91.0"]}]
    monkeypatch.setattr(app_mod, "_nominatim", fake)
    a = client.get("/places", params={"q": "Baton Rouge"}).json()
    b = client.get("/places", params={"q": "baton rouge"}).json()
    assert a == b and a[0]["bbox"] == [-91.2, 30.3, -91.0, 30.5]
    assert len(calls) == 1
    assert app_mod.USER_AGENT == "nisar-change-explorer"


def test_places_network_failure_502(client, monkeypatch):
    import httpx

    def boom(q):
        raise httpx.ConnectError("no network")
    monkeypatch.setattr(app_mod, "_nominatim", boom)
    r = client.get("/places", params={"q": "Nowhere"})
    assert r.status_code == 502 and "unavailable" in r.json()["detail"]


def test_availability_no_catalog_sample(client):
    body = client.post("/availability", json={"bbox": SMALL}).json()
    assert body["source"] == "sample"


def test_availability_catalog(client, tmp_path):
    d = tmp_path / "catalog"
    d.mkdir()
    rows = ["area,scene,date,time_utc,track,direction,frame,quality"]
    for i, dt in enumerate(["2026-06-18", "2026-06-30", "2026-09-10", "2026-09-22"]):
        rows.append(f"a,S{i},{dt},00:00:00,69,ASCENDING,14,x")
    (d / "pass_counts.csv").write_text("\n".join(rows))
    body = client.post("/availability", json={"bbox": SMALL}).json()
    assert body["source"] == "catalog" and body["questions"]["water_change"] is True
    body = client.post("/availability", json={"bbox": SMALL, "start": "2026-09-01"}).json()
    assert body["questions"]["water_change"] is False


def test_area_limit(client):
    r = client.post("/analyses", json={**ANALYZE, "bbox": BIG})
    assert r.status_code == 422 and "25" in r.json()["detail"]
    assert client.post("/availability", json={"bbox": BIG}).status_code == 422


def test_bad_bbox_422(client):
    assert client.post("/availability", json={"bbox": [1, 2, 3]}).status_code == 422


def test_analysis_flow_and_cache(client):
    job_id = client.post("/analyses", json=ANALYZE).json()["job_id"]
    r = _wait_done(client, job_id)
    assert r.status_code == 200
    res = r.json()
    validate_result(res)
    assert res["source"] == "sample" and res["limits"][0] == "Sample data - not live"
    assert res["method_version"] == cache.METHOD_VERSION == "floods-0.2.0"
    again = client.post("/analyses", json=ANALYZE).json()["job_id"]
    assert client.get(f"/analyses/{again}").status_code == 200


def test_running_409_with_step(client, monkeypatch):
    import threading
    gate = threading.Event()
    monkeypatch.setattr(jobs, "run_analysis", lambda req: (gate.wait(5), jobs.sample_result(req["bbox"]))[1])
    job_id = client.post("/analyses", json=ANALYZE).json()["job_id"]
    time.sleep(0.2)
    r = client.get(f"/analyses/{job_id}")
    assert r.status_code == 409 and r.json()["step"] == "detecting"
    gate.set()
    assert _wait_done(client, job_id).status_code == 200


def test_events_stream(client):
    job_id = client.post("/analyses", json=ANALYZE).json()["job_id"]
    with client.stream("GET", f"/analyses/{job_id}/events") as r:
        assert r.headers["content-type"].startswith("text/event-stream")
        evs = [json.loads(line[6:]) for line in r.iter_lines() if line.startswith("data: ")]
    assert [e["step"] for e in evs][:6] == jobs.STEPS and evs[-1]["step"] == "done"


def test_invalid_result_is_error(client, monkeypatch):
    monkeypatch.setattr(jobs, "run_analysis", lambda req: {"status": "ok", "bbox": req["bbox"]})
    job_id = client.post("/analyses", json=ANALYZE).json()["job_id"]
    r = _wait_done(client, job_id)
    assert r.status_code == 409 and "provenance" in r.json()["detail"]


def test_agreement(client, monkeypatch):
    job_id = client.post("/analyses", json=ANALYZE).json()["job_id"]
    _wait_done(client, job_id)
    a = client.get(f"/analyses/{job_id}/agreement").json()
    assert a["available"] is False and a["reason"]
    monkeypatch.setattr(jobs, "run_analysis",
                        lambda req: {**jobs.sample_result(req["bbox"]), "_verify": {"opera": {"overlap": 0.4}}})
    j2 = client.post("/analyses", json={**ANALYZE, "question": "other"}).json()["job_id"]
    _wait_done(client, j2)
    a = client.get(f"/analyses/{j2}/agreement").json()
    assert a["available"] is True and a["sources"]["opera"]["overlap"] == 0.4


def test_unknown_id_404(client):
    for p in ("", "/events", "/agreement"):
        assert client.get(f"/analyses/nope{p}").status_code == 404
