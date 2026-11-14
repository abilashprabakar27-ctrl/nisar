import os
import tempfile

os.environ["NCE_DATA_DIR"] = tempfile.mkdtemp()
os.environ["NCE_WATCH_CHECKER"] = "0"

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app import catalog, config, sample, watch
from app.catalog import NotEnoughData
from app.main import app
from app.models import Pass
from app.science import change


def _p(date, track="98", d="A"):
    return Pass(date=date, track=track, direction=d, quality="Provisional", url=f"x://{date}")


def test_parse_product_name():
    p = catalog.parse_product({"sceneName": "NISAR_L2_PR_GCOV_035_098_A_010_0005_NASV_M_20261111T233557_x",
                               "startTime": "2026-11-11T23:35:57Z",
                               "url": "https://x/NISAR_L2_GCOV_VALIDATED_V1/a.h5"})
    assert (p.track, p.direction, p.frame, p.quality, p.date) == ("98", "A", "10", "Validated", "2026-11-11")


def test_choose_groups_needs_two_each_side():
    ps = [_p("2026-08-12"), _p("2026-08-24"), _p("2026-09-05")]
    with pytest.raises(NotEnoughData):
        catalog.choose_groups(ps, event_date="2026-09-01")
    ps.append(_p("2026-09-17"))
    key, b, a, _ = catalog.choose_groups(ps, event_date="2026-09-01")
    assert key == ("98", "A") and [x.date for x in b] == ["2026-08-12", "2026-08-24"]
    assert [x.date for x in a] == ["2026-09-05", "2026-09-17"]


def test_choose_groups_keeps_one_track():
    ps = [_p("2026-08-12"), _p("2026-08-24"), _p("2026-09-05"), _p("2026-09-17"),
          _p("2026-08-20", "40", "D"), _p("2026-09-10", "40", "D")]
    key, b, a, _ = catalog.choose_groups(ps, event_date="2026-09-01")
    assert key == ("98", "A")


def test_detect_water_change_finds_new_water():
    rng = np.random.default_rng(0)
    land = 10 ** (-8 / 10) * rng.gamma(4, 0.25, (200, 200))
    flooded = land.copy()
    flooded[50:150, 50:150] = 10 ** (-22 / 10) * rng.gamma(4, 0.25, (100, 100))
    r = change.detect_water_change([land, land * 1.01], [flooded, flooded * 0.99], pixel_ha=0.04)
    got = r.areas_ha["became_water"]
    assert 330 < got < 420           # 100 x 100 px x 0.04 ha = 400 ha (edges smoothed)
    assert r.persistence > 0.9


def test_confidence_rules():
    assert change.confidence(2, 2, 1.0, 87, 0.05, ["Provisional"])[0] == "High"
    assert change.confidence(2, 2, 1.0, 40, 0.05, ["Provisional"])[0] == "Lower"
    assert change.confidence(2, 2, 1.0, 87, 0.05, ["Beta"])[0] == "Lower"


def test_sample_endpoint_and_files():
    c = TestClient(app)
    r = c.get("/sample").json()
    assert r["source"] == "sample" and r["headline"]["label"] == "Likely flooding"
    assert r["confidence"]["level"] in ("High", "Medium", "Lower")
    for k in ("result", "hh", "hv", "mix"):
        path = r["images"][k].split("/files/")[1]
        assert c.get(f"/files/{path}").status_code == 200


def test_analysis_job_with_sample_data(monkeypatch):
    monkeypatch.setattr(catalog, "search_passes", lambda bbox, *a, **k: sample.sample_passes())
    from app import pipeline
    real = pipeline.run_analysis
    monkeypatch.setattr(pipeline, "run_analysis",
                        lambda req, job_id=None, **kw: real(req, job_id, reader=sample.sample_reader, online=False))
    c = TestClient(app)
    body = dict(sample.SAMPLE_REQUEST, name="Test area", bbox=[85.0, 25.35, 85.24, 25.59])
    job = c.post("/analyses", json=body).json()
    import time
    for _ in range(120):
        st = c.get(f"/analyses/{job['id']}").json()
        if st["status"] in ("done", "failed", "not_enough_data"):
            break
        time.sleep(0.5)
    assert st["status"] == "done", st
    assert c.get(f"/analyses/{job['id']}/drivers").json()["label"].startswith("Interpretation")


def test_not_enough_data_job(monkeypatch):
    monkeypatch.setattr(catalog, "search_passes", lambda bbox, *a, **k: sample.sample_passes()[:3])
    c = TestClient(app)
    job = c.post("/analyses", json=dict(sample.SAMPLE_REQUEST, name="Thin area", bbox=[85.0, 25.35, 85.2, 25.55])).json()
    import time
    for _ in range(40):
        st = c.get(f"/analyses/{job['id']}").json()
        if st["status"] != "queued" and st["status"] != "running":
            break
        time.sleep(0.25)
    assert st["status"] == "not_enough_data"
    assert "won't guess" in st["error"]


def test_bad_bbox_rejected():
    c = TestClient(app)
    assert c.post("/analyses", json={"bbox": [10, 10, 5, 20]}).status_code == 422


def test_watch_flow():
    c = TestClient(app)
    item = c.post("/watch", json={"bbox": [85, 25.3, 85.2, 25.5], "name": "Patna", "last_result_date": "2026-09-17"}).json()
    assert any(i["id"] == item["id"] for i in c.get("/watch").json())
    items = watch.check_all(newest_fn=lambda b: "2026-09-29")
    assert next(i for i in items if i["id"] == item["id"])["new_pass_available"] is True
    assert c.delete(f"/watch/{item['id']}").status_code == 204


def test_learn_lists_all_challenge_resources():
    c = TestClient(app)
    ids = {r["id"] for r in c.get("/learn").json()["resources"]}
    for need in ("earthdata-search", "asf-vertex", "nisar-guide", "intro-rs", "intro-sar", "arset", "storymaps",
                 "white-papers", "uavsar", "rcm", "csa-sar-tutorial", "radarsat1", "saocom", "saocom-registration"):
        assert need in ids


def test_partners_endpoint_never_crashes(monkeypatch):
    from app import partners
    monkeypatch.setattr(partners, "search_eodms", lambda key, *a, **k: {"status": "not reachable"})
    c = TestClient(app)
    out = c.post("/partners", json={"bbox": [85, 25.35, 85.25, 25.6], "start": "2026-08-01", "end": "2026-10-01"}).json()
    assert out["rcm"]["status"] == "not reachable" and out["saocom"]["status"] == "not checked"


def test_result_has_credits():
    c = TestClient(app)
    r = c.get("/sample?rebuild=true").json()
    titles = [s["title"] for s in r["credits"]["sources"]]
    assert "ASF Data Search Vertex" in titles
