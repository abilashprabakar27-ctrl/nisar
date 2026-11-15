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


# ---- bbox-aware /availability ----
def _aoi_catalog(tmp_path):
    d = tmp_path / "catalog"
    d.mkdir()
    (d / "aoi_centres.csv").write_text("area,lat,lon\nlake,10.0,20.0\nriver,10.0,20.2\n")
    hdr = "area,scene,date,time_utc,track,direction,frame,quality,url,size_bytes,aoi_cover,polarization,in_gap"
    rows = [hdr]
    for i, dt in enumerate(["2026-06-18", "2026-06-30", "2026-07-12", "2026-08-17", "2026-09-10", "2026-09-22"]):
        rows.append(f"lake,S{i},{dt},00:00:00,5,ASCENDING,7,cfg=PR;crid=P05023,u,1,1.0,HH+HV,False")
    rows.append("lake,SG,2026-08-01,00:00:00,5,ASCENDING,7,cfg=PR,u,1,1.0,HH+HV,True")
    rows.append("river,R0,2026-06-18,00:00:00,9,ASCENDING,7,cfg=PR,u,1,1.0,HH+HV,False")
    (d / "pass_counts.csv").write_text("\n".join(rows))


def test_availability_inside_aoi(client, tmp_path):
    _aoi_catalog(tmp_path)
    body = client.post("/availability", json={"bbox": [19.9, 9.9, 20.05, 10.1]}).json()
    assert body["coverage"] == "catalogue" and [a["area"] for a in body["areas"]] == ["lake"]
    a = body["areas"][0]
    assert a["passes"] == 6 and a["newest_pass_date"] == "2026-09-22" and a["quality"] == "PROVISIONAL"
    assert a["gap_flag"] is True and a["gap_dates"] == ["2026-08-01"] and "2026-08-01" not in a["dates"]
    assert a["straddles_gap"] is True and a["answerable"] and body["questions"]["water_change"] is True


def test_availability_outside_aoi_is_honest(client, tmp_path):
    _aoi_catalog(tmp_path)
    body = client.post("/availability", json={"bbox": [-30.0, 0.0, -29.9, 0.1]}).json()
    assert body["coverage"] == "none" and body["areas"] == [] and body["passes"] == 0
    assert body["questions"]["water_change"] is False and body["answerable"] == []
    assert "No NISAR catalogue coverage checked here" in body["message"]


def test_availability_straddles_two_aois(client, tmp_path):
    _aoi_catalog(tmp_path)
    body = client.post("/availability", json={"bbox": [20.05, 9.95, 20.15, 10.05]}).json()
    assert {a["area"] for a in body["areas"]} == {"lake", "river"}
    river = next(a for a in body["areas"] if a["area"] == "river")
    assert river["status"] == "insufficient_data" and river["answerable"] == []
    assert body["questions"]["water_change"] is True  # lake can answer, river cannot


def test_availability_big_bbox_still_422(client, tmp_path):
    _aoi_catalog(tmp_path)
    assert client.post("/availability", json={"bbox": [19.0, 9.0, 21.0, 11.0]}).status_code == 422
    assert client.post("/analyses", json={**ANALYZE, "bbox": [19.0, 9.0, 21.0, 11.0]}).status_code == 422


def test_availability_real_catalog_demo_areas(tmp_path, monkeypatch):
    monkeypatch.delenv("NISAR_CATALOG_DIR", raising=False)
    c = TestClient(app)
    b = c.post("/availability", json={"bbox": [104.0, 12.8, 104.2, 13.0]}).json()
    assert [a["area"] for a in b["areas"]] == ["mekong_tonlesap"] and b["areas"][0]["passes"] == 11
    assert c.post("/availability", json={"bbox": [-30, 0, -29.9, 0.1]}).json()["coverage"] == "none"


def test_agreement_survives_cache_hit(client, monkeypatch):
    monkeypatch.setattr(jobs, "run_analysis",
                        lambda req: {**jobs.sample_result(req["bbox"]), "source": "saved", "_verify": {"opera": {"overlap": 0.7}}})
    j1 = client.post("/analyses", json={**ANALYZE, "question": "persist"}).json()["job_id"]
    _wait_done(client, j1)
    j2 = client.post("/analyses", json={**ANALYZE, "question": "persist"}).json()["job_id"]  # cache hit
    a = client.get(f"/analyses/{j2}/agreement").json()
    assert a["available"] is True and a["sources"]["opera"]["overlap"] == 0.7
